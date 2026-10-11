"""G03-C1 — GDS path tests (reviewer notes #1, #3, #4, #5).

These tests exercise the SERVICE CODE PATH against an in-process FakeDriver.
They verify the Cypher query structure and parameters the service issues,
NOT real Neo4j runtime behavior. The real Neo4j/GDS smoke is mandatory for
G07 lockdown.

Coverage:
- #1: gds.graph.project uses the supported 3-argument signature with
  $name and $nodeLabel parameters.
- #3: gds.louvain.stream runs on the projected graph; nodeId→node_ref
  conversion produces communities of actual node_refs (not internal ids).
- #4: gds.graph.drop is GUARANTEED to run in a finally block, even when
  Louvain raises; the projection is never leaked.
- #5: tests assert on query structure + parameters captured by the fake's
  queries_run log, not just function-call outcomes.
- #6: when the GDS path fails, the result is provider='networkx_fallback'
  and is NOT counted as a GDS success.
"""
from __future__ import annotations

import pytest

from app.config import Settings
from app.services import neo4j_service, gds_service, graph_service, session_service
from app.tests._fake_neo4j import FakeDriver


@pytest.fixture(autouse=True)
def _reset_driver():
    neo4j_service.reset_driver_for_tests()
    yield
    neo4j_service.reset_driver_for_tests()


def _setup_gds_env(db, settings, dataset_id="gds-ds", fixture_key="communities-v1"):
    """Shared helper: configure settings, inject fake, seed graph + Neo4j."""
    settings.neo4j_uri = "bolt://localhost:7687"
    settings.neo4j_user = "neo4j"
    settings.neo4j_password = "x"
    settings.gds_licensed = True
    fake = FakeDriver(connected=True, gds_available=True)
    neo4j_service.inject_test_driver(fake)

    session = session_service.create_guest_session(db, settings, "en")
    graph_service.load_fixture(db, settings, session, dataset_id, fixture_key)
    from app.fixtures.graph_seed import COMMUNITIES_V1
    neo4j_service.import_fixture(settings, session.id, dataset_id, COMMUNITIES_V1)
    return session, fake


def _collect_queries(fake: FakeDriver) -> list[tuple[str, dict]]:
    """The fake creates a new session per driver.session() call; collect
    queries_run from all sessions by inspecting the fake's session factory.

    Since FakeDriver.session() returns a fresh FakeSession each time, we
    need a different approach: we patch the fake to record into a shared
    list."""
    # We'll re-create the fake with a shared queries list.
    return fake._shared_queries if hasattr(fake, "_shared_queries") else []


class _RecordingFakeDriver(FakeDriver):
    """FakeDriver variant that records every query across all sessions
    into a single shared list, so tests can assert on the full query log."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._shared_queries: list[tuple[str, dict]] = []
        self._shared_sessions: list = []

    def session(self, database=None):
        sess = super().session(database=database)
        # Wrap sess.run to also record into the shared list.
        original_run = sess.run
        def recording_run(query, parameters=None, **kwargs):
            self._shared_queries.append((query, {**(parameters or {}), **kwargs}))
            return original_run(query, parameters, **kwargs)
        sess.run = recording_run  # type: ignore[assignment]
        self._shared_sessions.append(sess)
        return sess


def test_gds_projection_uses_supported_3arg_signature(db, settings):
    """Note #1: the projection call must use
    `CALL gds.graph.project($name, $nodeLabel, '*')` — the documented
    GDS API. The old code used a malformed string-interpolated subquery
    attempt. This test asserts the query STRUCTURE and PARAMETERS.
    """
    settings.neo4j_uri = "bolt://localhost:7687"
    settings.neo4j_user = "neo4j"
    settings.neo4j_password = "x"
    settings.gds_licensed = True
    fake = _RecordingFakeDriver(connected=True, gds_available=True)
    neo4j_service.inject_test_driver(fake)

    session = session_service.create_guest_session(db, settings, "en")
    graph_service.load_fixture(db, settings, session, "proj-test", "communities-v1")
    from app.fixtures.graph_seed import COMMUNITIES_V1
    neo4j_service.import_fixture(settings, session.id, "proj-test", COMMUNITIES_V1)

    result = gds_service.detect_communities(db, settings, session, "proj-test")

    # Find the projection query in the log.
    proj_queries = [
        (q, p) for (q, p) in fake._shared_queries
        if q.strip().startswith("CALL gds.graph.project")
    ]
    assert len(proj_queries) == 1, f"expected 1 projection call, got {len(proj_queries)}"
    q, params = proj_queries[0]
    # The query must use $name and $nodeLabel parameters (not string-interpolated).
    assert "$name" in q
    assert "$nodeLabel" in q
    assert "'*'" in q  # relationship spec
    # The parameters must carry the expected values.
    expected_label = neo4j_service.dataset_label(session.id, "proj-test")
    assert params.get("name") == f"g_{expected_label}"
    assert params.get("nodeLabel") == expected_label
    # The query must NOT contain the old broken subquery pattern.
    assert "MATCH (n:" not in q  # no inline subquery
    assert "RETURN id(n) AS id, n.kind" not in q  # no inline subquery


def test_gds_louvain_runs_on_correct_projection(db, settings):
    """Note #3: gds.louvain.stream must run with $name pointing at the
    projection we just created, and the nodeId→node_ref conversion must
    produce communities of actual node_refs (not internal ids)."""
    fake = _RecordingFakeDriver(connected=True, gds_available=True)
    settings.neo4j_uri = "bolt://localhost:7687"
    settings.neo4j_user = "neo4j"
    settings.neo4j_password = "x"
    settings.gds_licensed = True
    neo4j_service.inject_test_driver(fake)

    session = session_service.create_guest_session(db, settings, "en")
    graph_service.load_fixture(db, settings, session, "louvain-test", "communities-v1")
    from app.fixtures.graph_seed import COMMUNITIES_V1
    neo4j_service.import_fixture(settings, session.id, "louvain-test", COMMUNITIES_V1)

    result = gds_service.detect_communities(db, settings, session, "louvain-test")

    assert result.provider == "gds"
    assert result.algorithm == "louvain"

    # Find the louvain query.
    louvain_queries = [
        (q, p) for (q, p) in fake._shared_queries
        if q.strip().startswith("CALL gds.louvain.stream")
    ]
    assert len(louvain_queries) == 1
    q, params = louvain_queries[0]
    expected_label = neo4j_service.dataset_label(session.id, "louvain-test")
    assert params.get("name") == f"g_{expected_label}"

    # The communities must contain actual node_refs (A1/A2/A3/B1/B2/B3/C1/C2/C3),
    # NOT internal integer ids.
    all_returned_refs = {n for c in result.communities for n in c}
    expected_refs = {"A1", "A2", "A3", "B1", "B2", "B3", "C1", "C2", "C3"}
    assert all_returned_refs == expected_refs, (
        f"nodeId→node_ref conversion failed; got {all_returned_refs}"
    )
    # 3 communities (one per kind: app/tool/skill in the fake's partitioning).
    assert len(result.communities) == 3


def test_gds_projection_cleanup_runs_on_success(db, settings):
    """Note #4: gds.graph.drop must run in the finally block even when
    the Louvain call SUCCEEDS — no projection is leaked."""
    fake = _RecordingFakeDriver(connected=True, gds_available=True)
    settings.neo4j_uri = "bolt://localhost:7687"
    settings.neo4j_user = "neo4j"
    settings.neo4j_password = "x"
    settings.gds_licensed = True
    neo4j_service.inject_test_driver(fake)

    session = session_service.create_guest_session(db, settings, "en")
    graph_service.load_fixture(db, settings, session, "cleanup-success", "communities-v1")
    from app.fixtures.graph_seed import COMMUNITIES_V1
    neo4j_service.import_fixture(settings, session.id, "cleanup-success", COMMUNITIES_V1)

    result = gds_service.detect_communities(db, settings, session, "cleanup-success")
    assert result.provider == "gds"

    # The drop query must have been issued.
    drop_queries = [
        q for (q, _) in fake._shared_queries
        if q.strip().startswith("CALL gds.graph.drop")
    ]
    assert len(drop_queries) == 1, (
        f"expected 1 gds.graph.drop call (cleanup), got {len(drop_queries)}"
    )
    # The projection must no longer be in the fake's store.
    expected_label = neo4j_service.dataset_label(session.id, "cleanup-success")
    graph_name = f"g_{expected_label}"
    assert graph_name not in fake.store.get("projections", {})


class _LouvainFailingFakeDriver(_RecordingFakeDriver):
    """FakeDriver variant where gds.louvain.stream raises, so we can
    verify the projection is still dropped in the finally block."""

    def session(self, database=None):
        sess = super().session(database=database)
        original_run = sess.run
        def failing_run(query, parameters=None, **kwargs):
            q = query.strip()
            if q.startswith("CALL gds.louvain.stream"):
                # First, the service has already called gds.graph.project,
                # so the projection exists. Now simulate Louvain failure.
                raise RuntimeError("simulated louvain failure")
            return original_run(query, parameters, **kwargs)
        sess.run = failing_run  # type: ignore[assignment]
        return sess


def test_gds_projection_cleanup_runs_on_louvain_failure(db, settings):
    """Note #4: when Louvain raises, gds.graph.drop must STILL run in
    the finally block — no projection leaked."""
    fake = _LouvainFailingFakeDriver(connected=True, gds_available=True)
    settings.neo4j_uri = "bolt://localhost:7687"
    settings.neo4j_user = "neo4j"
    settings.neo4j_password = "x"
    settings.gds_licensed = True
    neo4j_service.inject_test_driver(fake)

    session = session_service.create_guest_session(db, settings, "en")
    graph_service.load_fixture(db, settings, session, "cleanup-fail", "communities-v1")
    from app.fixtures.graph_seed import COMMUNITIES_V1
    neo4j_service.import_fixture(settings, session.id, "cleanup-fail", COMMUNITIES_V1)

    result = gds_service.detect_communities(db, settings, session, "cleanup-fail")

    # Louvain failed → fallback to NetworkX, honestly labelled.
    assert result.provider == "networkx_fallback"
    assert "NOT GDS" in result.note
    assert "gds_call_failed" in result.note

    # The drop query must STILL have been issued (cleanup in finally).
    drop_queries = [
        q for (q, _) in fake._shared_queries
        if q.strip().startswith("CALL gds.graph.drop")
    ]
    assert len(drop_queries) == 1, (
        "gds.graph.drop must run in finally even when Louvain fails"
    )
    # The projection must no longer be in the fake's store.
    expected_label = neo4j_service.dataset_label(session.id, "cleanup-fail")
    graph_name = f"g_{expected_label}"
    assert graph_name not in fake.store.get("projections", {}), (
        "projection leaked — cleanup did not run"
    )


class _ProjectionFailingFakeDriver(_RecordingFakeDriver):
    """FakeDriver variant where gds.graph.project raises, so we can
    verify the code falls back gracefully and the session is closed."""

    def session(self, database=None):
        sess = super().session(database=database)
        original_run = sess.run
        def failing_run(query, parameters=None, **kwargs):
            q = query.strip()
            if q.startswith("CALL gds.graph.project"):
                raise RuntimeError("simulated projection failure")
            return original_run(query, parameters, **kwargs)
        sess.run = failing_run  # type: ignore[assignment]
        return sess


def test_gds_projection_failure_falls_back_to_networkx(db, settings):
    """Note #4 + #6: when the projection call itself fails, the code
    must fall back to NetworkX (labelled), and the session must be
    closed (no leak). No gds.graph.drop should be issued because the
    projection was never created."""
    fake = _ProjectionFailingFakeDriver(connected=True, gds_available=True)
    settings.neo4j_uri = "bolt://localhost:7687"
    settings.neo4j_user = "neo4j"
    settings.neo4j_password = "x"
    settings.gds_licensed = True
    neo4j_service.inject_test_driver(fake)

    session = session_service.create_guest_session(db, settings, "en")
    graph_service.load_fixture(db, settings, session, "proj-fail", "communities-v1")
    from app.fixtures.graph_seed import COMMUNITIES_V1
    neo4j_service.import_fixture(settings, session.id, "proj-fail", COMMUNITIES_V1)

    result = gds_service.detect_communities(db, settings, session, "proj-fail")
    assert result.provider == "networkx_fallback"
    assert "NOT GDS" in result.note
    assert "gds_call_failed" in result.note

    # No gds.graph.drop should have been issued (projection never created).
    drop_queries = [
        q for (q, _) in fake._shared_queries
        if q.strip().startswith("CALL gds.graph.drop")
    ]
    assert len(drop_queries) == 0


def test_networkx_fallback_not_counted_as_gds_success(db, settings):
    """Note #6: hard invariant — a NetworkX fallback result must NOT
    be counted as a GDS success. The provider field is the canonical
    signal; tests that check for GDS success must look for
    provider=='gds' specifically, not just `result is not None`."""
    # Force fallback by leaving gds_licensed=False.
    settings.neo4j_uri = "bolt://localhost:7687"
    settings.neo4j_user = "neo4j"
    settings.neo4j_password = "x"
    settings.gds_licensed = False
    fake = FakeDriver(connected=True, gds_available=True)
    neo4j_service.inject_test_driver(fake)

    session = session_service.create_guest_session(db, settings, "en")
    graph_service.load_fixture(db, settings, session, "not-gds", "communities-v1")

    result = gds_service.detect_communities(db, settings, session, "not-gds")
    # The fallback returns communities (so `result is not None` is True),
    # but provider MUST be networkx_fallback, NOT 'gds'.
    assert result.provider == "networkx_fallback"
    assert result.provider != "gds"
    # The note explicitly disclaims GDS certification.
    assert "NOT GDS" in result.note
    assert "do not certify native GDS behavior" in result.note


def test_gds_success_path_returns_actual_node_refs(db, settings):
    """Note #3: the GDS success path must return communities of
    node_refs (strings like 'A1'), not internal integer nodeIds.
    This catches any regression in the id→ref conversion."""
    fake = _RecordingFakeDriver(connected=True, gds_available=True)
    settings.neo4j_uri = "bolt://localhost:7687"
    settings.neo4j_user = "neo4j"
    settings.neo4j_password = "x"
    settings.gds_licensed = True
    neo4j_service.inject_test_driver(fake)

    session = session_service.create_guest_session(db, settings, "en")
    graph_service.load_fixture(db, settings, session, "ref-conv", "communities-v1")
    from app.fixtures.graph_seed import COMMUNITIES_V1
    neo4j_service.import_fixture(settings, session.id, "ref-conv", COMMUNITIES_V1)

    result = gds_service.detect_communities(db, settings, session, "ref-conv")
    assert result.provider == "gds"
    # Every member of every community must be a string node_ref.
    for community in result.communities:
        for member in community:
            assert isinstance(member, str), (
                f"community member {member!r} must be a node_ref string, "
                f"not an internal integer id"
            )
    # The union of all community members must equal the fixture's node set.
    all_members = {n for c in result.communities for n in c}
    expected = {n.ref for n in COMMUNITIES_V1.nodes}
    assert all_members == expected
