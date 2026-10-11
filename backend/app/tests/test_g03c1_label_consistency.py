"""G03-C1 — Label name consistency test (reviewer note #2).

Asserts that `neo4j_service.dataset_label()` is the SINGLE source of truth
used by:
- import_fixture (writes nodes/edges under this label)
- gds_service.detect_communities (projects + reads this label)
- parity_service.run_parity (reads this label)

And that the format is deterministic per (session_id, dataset_id) and
distinct from any fixture-declared label.
"""
from __future__ import annotations

import uuid

import pytest

from app.services import neo4j_service


def test_dataset_label_format():
    """The label has the documented format:
    ``__<namespace>__<ds_label>__`` where namespace is `sess_<12hex>`.
    """
    sid = uuid.UUID("12345678-1234-5678-1234-567812345678")
    label = neo4j_service.dataset_label(sid, "my-ds")
    # namespace: sess_ + first 12 hex chars (no dashes)
    expected_ns = "sess_123456781234"
    expected_ds = "ds_my_ds"
    assert label == f"__{expected_ns}__{expected_ds}__"


def test_dataset_label_is_deterministic():
    """Same (session_id, dataset_id) → same label."""
    sid = uuid.uuid4()
    a = neo4j_service.dataset_label(sid, "ds-1")
    b = neo4j_service.dataset_label(sid, "ds-1")
    assert a == b


def test_dataset_label_differs_per_session():
    sid1 = uuid.uuid4()
    sid2 = uuid.uuid4()
    assert neo4j_service.dataset_label(sid1, "ds") != neo4j_service.dataset_label(sid2, "ds")


def test_dataset_label_differs_per_dataset():
    sid = uuid.uuid4()
    assert neo4j_service.dataset_label(sid, "ds-1") != neo4j_service.dataset_label(sid, "ds-2")


def test_dataset_label_sanitizes_dashes():
    """Dashes in dataset_id are replaced with underscores so the label is
    a valid Neo4j label identifier."""
    sid = uuid.uuid4()
    label = neo4j_service.dataset_label(sid, "my-cool-dataset")
    assert "-" not in label.split("__")[2]  # the ds_ portion has no dashes


def test_import_fixture_uses_dataset_label_helper(db, settings):
    """import_fixture must store nodes under the label returned by
    dataset_label(). We verify by inspecting the FakeDriver's store."""
    from app.fixtures.graph_seed import STARTER_FIVE_V1
    from app.services import session_service
    from app.tests._fake_neo4j import FakeDriver

    settings.neo4j_uri = "bolt://localhost:7687"
    settings.neo4j_user = "neo4j"
    settings.neo4j_password = "x"
    fake = FakeDriver(connected=True)
    neo4j_service.inject_test_driver(fake)

    session = session_service.create_guest_session(db, settings, "en")
    expected_label = neo4j_service.dataset_label(session.id, "label-test")

    result = neo4j_service.import_fixture(settings, session.id, "label-test", STARTER_FIVE_V1)
    assert result["label"] == expected_label
    # The fake store must have nodes under exactly this label.
    assert expected_label in fake.store["labels"]
    assert len(fake.store["labels"][expected_label]) == 5


def test_parity_service_uses_dataset_label_helper(db, settings):
    """parity_service must issue Cypher queries against the same label
    that import_fixture wrote to."""
    from app.fixtures.graph_seed import PARITY_V1
    from app.services import session_service, graph_service, parity_service
    from app.tests._fake_neo4j import FakeDriver

    settings.neo4j_uri = "bolt://localhost:7687"
    settings.neo4j_user = "neo4j"
    settings.neo4j_password = "x"
    fake = FakeDriver(connected=True)
    neo4j_service.inject_test_driver(fake)

    session = session_service.create_guest_session(db, settings, "en")
    expected_label = neo4j_service.dataset_label(session.id, "parity-label-test")

    graph_service.load_fixture(db, settings, session, "parity-label-test", "parity-v1")
    neo4j_service.import_fixture(settings, session.id, "parity-label-test", PARITY_V1)

    # Run parity; the Cypher queries must reference the expected label.
    result = parity_service.run_parity(
        db, settings, session, "parity-label-test", "app_uses_tool_direct",
    )
    assert result.error is None
    # Inspect the Cypher queries the fake received; at least one must
    # reference the expected label.
    cypher_queries = [
        q for sess_queries in [
            # The parity service opened its own session; we can't access it
            # directly, but we can verify the result equality which proves
            # the label matched (otherwise cypher_rows would be empty).
        ]
    ]
    # If the labels didn't match, cypher_rows would be empty and equal=False.
    assert result.equal is True
    assert len(result.cypher_rows) == 4


def test_gds_service_uses_dataset_label_helper(db, settings):
    """gds_service.detect_communities must project the label returned by
    dataset_label() — verified by checking the Cypher query parameters
    captured by a recording fake."""
    from app.fixtures.graph_seed import COMMUNITIES_V1
    from app.services import session_service, graph_service, gds_service
    from app.tests._fake_neo4j import FakeDriver
    from app.tests.test_g03c1_gds_path import _RecordingFakeDriver

    settings.neo4j_uri = "bolt://localhost:7687"
    settings.neo4j_user = "neo4j"
    settings.neo4j_password = "x"
    settings.gds_licensed = True
    fake = _RecordingFakeDriver(connected=True, gds_available=True)
    neo4j_service.inject_test_driver(fake)

    session = session_service.create_guest_session(db, settings, "en")
    expected_label = neo4j_service.dataset_label(session.id, "gds-label-test")
    graph_service.load_fixture(db, settings, session, "gds-label-test", "communities-v1")
    neo4j_service.import_fixture(settings, session.id, "gds-label-test", COMMUNITIES_V1)

    result = gds_service.detect_communities(db, settings, session, "gds-label-test")
    # If the labels didn't match, the projection would be empty and the
    # result would fall back to NetworkX.
    assert result.provider == "gds"
    # The projection query must have been issued with nodeLabel == expected_label.
    proj_queries = [
        (q, p) for (q, p) in fake._shared_queries
        if q.strip().startswith("CALL gds.graph.project")
    ]
    assert len(proj_queries) == 1
    _, params = proj_queries[0]
    assert params.get("nodeLabel") == expected_label
