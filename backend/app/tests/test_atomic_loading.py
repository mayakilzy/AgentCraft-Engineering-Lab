"""G02 reviewer note #2 — atomic fixture loading + rollback test.

A failing fixture load must leave the (session, dataset) scope empty.
We force failures via a broken fixture (duplicate node_ref, dangling
edge endpoint, self-loop) and verify the DB row counts stay at 0.
"""
from __future__ import annotations

import pytest

from app.fixtures.graph_seed import (
    FixtureEdge,
    FixtureNode,
    GraphFixture,
)
from app.services import session_service, graph_service
from app.core.errors import InvalidStateError


def _make_fixture(
    nodes: list[tuple[str, str, str]],
    edges: list[tuple[str, str, str]],
    key: str = "broken-test-fixture",
) -> GraphFixture:
    """Build an in-memory fixture for testing; never registered globally."""
    return GraphFixture(
        dataset_key=key,
        version="0.0.0-test",
        nodes=tuple(FixtureNode(ref=r, kind=k, label=l) for r, k, l in nodes),
        edges=tuple(FixtureEdge(s, t, rel) for s, t, rel in edges),
        expected={},
    )


def _load_broken(db, settings, session, fixture: GraphFixture):
    """Directly invoke the loader body with a one-shot fixture.

    We monkey-patch `app.fixtures.graph_seed.get_fixture` to return our
    broken fixture for the requested key.
    """
    from app.fixtures import graph_seed as gs

    original = gs.get_fixture
    gs._FIXTURES = {**gs._FIXTURES, fixture.dataset_key: fixture}
    try:
        return graph_service.load_fixture(
            db, settings, session, "atomic-rollback-test", fixture.dataset_key,
        )
    finally:
        gs._FIXTURES.pop(fixture.dataset_key, None)


def test_rollback_on_duplicate_node_ref(db, settings):
    """A fixture with a duplicate node_ref must fail and leave zero rows."""
    session = session_service.create_guest_session(db, settings, "en")
    fixture = _make_fixture(
        nodes=[("A", "app", "App A"), ("A", "tool", "Dup")],
        edges=[],
        key="broken-dup-node",
    )
    with pytest.raises(InvalidStateError) as exc:
        _load_broken(db, settings, session, fixture)
    assert "duplicate node_ref" in str(exc.value)

    # No partial rows.
    summary = graph_service.get_dataset_summary(db, session, "atomic-rollback-test")
    assert summary == {
        "dataset_id": "atomic-rollback-test",
        "node_count": 0,
        "edge_count": 0,
    }


def test_rollback_on_unknown_edge_endpoint(db, settings):
    """A fixture whose edge references a non-existent node must fail and
    leave zero rows (no partial node inserts either)."""
    session = session_service.create_guest_session(db, settings, "en")
    fixture = _make_fixture(
        nodes=[("A", "app", "App A")],
        edges=[("A", "GHOST", "R")],  # GHOST not in nodes
        key="broken-unknown-edge",
    )
    with pytest.raises(InvalidStateError) as exc:
        _load_broken(db, settings, session, fixture)
    assert "unknown target node" in str(exc.value)

    summary = graph_service.get_dataset_summary(db, session, "atomic-rollback-test")
    assert summary["node_count"] == 0
    assert summary["edge_count"] == 0


def test_rollback_on_self_loop(db, settings):
    """A fixture with a self-loop edge must fail and leave zero rows."""
    session = session_service.create_guest_session(db, settings, "en")
    fixture = _make_fixture(
        nodes=[("L", "app", "Loop")],
        edges=[("L", "L", "SELF")],
        key="broken-self-loop",
    )
    with pytest.raises(InvalidStateError) as exc:
        _load_broken(db, settings, session, fixture)
    assert "self-loop" in str(exc.value)

    summary = graph_service.get_dataset_summary(db, session, "atomic-rollback-test")
    assert summary["node_count"] == 0
    assert summary["edge_count"] == 0


def test_rollback_on_duplicate_edge_triplet(db, settings):
    session = session_service.create_guest_session(db, settings, "en")
    fixture = _make_fixture(
        nodes=[("A", "app", "A"), ("B", "tool", "B")],
        edges=[("A", "B", "R"), ("A", "B", "R")],
        key="broken-dup-edge",
    )
    with pytest.raises(InvalidStateError) as exc:
        _load_broken(db, settings, session, fixture)
    assert "duplicate edge triplet" in str(exc.value)
    summary = graph_service.get_dataset_summary(db, session, "atomic-rollback-test")
    assert summary["node_count"] == 0


def test_rollback_on_cardinality_pre_flight(db, settings, monkeypatch):
    """A fixture whose node count exceeds the cap must fail before any
    insert, leaving zero rows."""
    monkeypatch.setattr(settings, "max_graph_nodes", 2)
    monkeypatch.setattr(settings, "max_graph_edges", 100)

    session = session_service.create_guest_session(db, settings, "en")
    fixture = _make_fixture(
        nodes=[("N1", "app", "1"), ("N2", "app", "2"), ("N3", "app", "3")],
        edges=[],
        key="broken-cap",
    )
    with pytest.raises(InvalidStateError) as exc:
        _load_broken(db, settings, session, fixture)
    assert "max_graph_nodes" in str(exc.value)
    summary = graph_service.get_dataset_summary(db, session, "atomic-rollback-test")
    assert summary["node_count"] == 0


def test_atomic_load_leaves_no_partial_after_db_error(db, settings, monkeypatch):
    """Force a DB-level failure mid-load (e.g., by inserting a node whose
    kind is None — the column is NOT NULL) and verify the rollback path.
    """
    session = session_service.create_guest_session(db, settings, "en")

    # Build a fixture whose first node is valid but second has an invalid
    # kind (None). The pre-flight checks pass because kind is just a str
    # in the dataclass; the failure happens at flush/commit.
    from app.fixtures.graph_seed import FixtureNode, FixtureEdge, GraphFixture
    fixture = GraphFixture(
        dataset_key="broken-db-mid",
        version="0.0.0-test",
        nodes=(
            FixtureNode("A", "app", "App A"),
            FixtureNode("B", None, "Bad Kind"),  # type: ignore[arg-type]
        ),
        edges=(),
        expected={},
    )
    # Manually insert via the loader with a small monkeypatch so get_fixture
    # returns our broken fixture.
    from app.fixtures import graph_seed as gs
    gs._FIXTURES["broken-db-mid"] = fixture
    try:
        with pytest.raises(Exception):
            graph_service.load_fixture(
                db, settings, session, "atomic-rollback-test", "broken-db-mid",
            )
    finally:
        gs._FIXTURES.pop("broken-db-mid", None)

    summary = graph_service.get_dataset_summary(db, session, "atomic-rollback-test")
    assert summary["node_count"] == 0
    assert summary["edge_count"] == 0


def test_successful_load_after_rollback_does_not_carry_state(db, settings):
    """After a failed load + rollback, a subsequent successful load must
    produce the expected counts (the rollback truly cleared the slate)."""
    session = session_service.create_guest_session(db, settings, "en")
    # First: a broken fixture that triggers rollback.
    broken = _make_fixture(
        nodes=[("A", "app", "A"), ("A", "tool", "Dup")],
        edges=[],
        key="broken-then-success",
    )
    with pytest.raises(InvalidStateError):
        _load_broken(db, settings, session, broken)

    # Second: a valid fixture into the SAME dataset scope.
    valid = _make_fixture(
        nodes=[("X", "app", "X"), ("Y", "tool", "Y")],
        edges=[("X", "Y", "R")],
        key="valid-then-success",
    )
    from app.fixtures import graph_seed as gs
    gs._FIXTURES["valid-then-success"] = valid
    try:
        summary = graph_service.load_fixture(
            db, settings, session, "atomic-rollback-test", "valid-then-success",
        )
    finally:
        gs._FIXTURES.pop("valid-then-success", None)

    assert summary["node_count"] == 2
    assert summary["edge_count"] == 1
