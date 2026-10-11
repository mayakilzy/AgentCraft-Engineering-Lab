"""T09 — Neo4j provisioning tests.

Production Neo4j requires Docker (not available in dev env). We exercise
the service code path against an in-process fake driver that mirrors the
real `GraphDatabase` API shape used by `neo4j_service`. The fake is in
`app/tests/_fake_neo4j.py`.

The actual runtime smoke (Docker Compose `--profile neo4j up`) is
mandatory for G07 lockdown; here we verify:
- Capability probe returns connected=False when no URI is configured.
- Capability probe returns connected=False when verify_connectivity() fails.
- Capability probe returns gds_available correctly when connected.
- Session-scoped import is idempotent.
- Cleanup by namespace deletes only the session's nodes.
"""
from __future__ import annotations

import pytest

from app.config import Settings
from app.services import neo4j_service
from app.services.neo4j_service import (
    Neo4jCapability,
    session_namespace,
)
from app.tests._fake_neo4j import FakeDriver


@pytest.fixture(autouse=True)
def _reset_driver():
    neo4j_service.reset_driver_for_tests()
    yield
    neo4j_service.reset_driver_for_tests()


def test_capability_probe_no_uri_returns_disconnected():
    settings = Settings()  # NEO4J_URI defaults to None
    cap = neo4j_service.probe_capability(settings)
    assert cap.connected is False
    assert "NEO4J_URI not configured" in (cap.error or "")


def test_capability_probe_with_uri_but_unreachable():
    settings = Settings()
    settings.neo4j_uri = "bolt://localhost:7687"
    settings.neo4j_user = "neo4j"
    settings.neo4j_password = "x"
    # Inject a fake driver that reports disconnected.
    fake = FakeDriver(connected=False)
    neo4j_service.inject_test_driver(fake)
    cap = neo4j_service.probe_capability(settings)
    assert cap.connected is False
    assert "ConnectionError" in (cap.error or "")


def test_capability_probe_connected_no_gds():
    settings = Settings()
    settings.neo4j_uri = "bolt://localhost:7687"
    settings.neo4j_user = "neo4j"
    settings.neo4j_password = "x"
    settings.gds_licensed = False
    fake = FakeDriver(connected=True, gds_available=False)
    neo4j_service.inject_test_driver(fake)
    cap = neo4j_service.probe_capability(settings)
    assert cap.connected is True
    assert cap.gds_available is False
    assert cap.gds_licensed is False
    # Server info has components
    assert "components" in cap.server_info


def test_capability_probe_connected_with_gds():
    settings = Settings()
    settings.neo4j_uri = "bolt://localhost:7687"
    settings.neo4j_user = "neo4j"
    settings.neo4j_password = "x"
    settings.gds_licensed = True
    fake = FakeDriver(connected=True, gds_available=True)
    neo4j_service.inject_test_driver(fake)
    cap = neo4j_service.probe_capability(settings)
    assert cap.connected is True
    assert cap.gds_available is True
    assert cap.gds_licensed is True


def test_session_namespace_is_deterministic_and_prefix_safe():
    """Same session_id → same namespace; different session_id → different;
    namespace always starts with `sess_`."""
    import uuid
    sid1 = uuid.uuid4()
    sid2 = uuid.uuid4()
    ns1 = session_namespace(sid1)
    ns2 = session_namespace(sid2)
    assert ns1 != ns2
    assert ns1.startswith("sess_")
    assert ns2.startswith("sess_")
    # Same id → same namespace.
    assert session_namespace(sid1) == ns1


def test_import_fixture_idempotent_on_repeated_load(db, settings):
    """Re-importing the same fixture into the same (session, dataset) is
    a no-op (deterministic)."""
    from app.fixtures.graph_seed import STARTER_FIVE_V1
    from app.services import session_service
    settings.neo4j_uri = "bolt://localhost:7687"
    settings.neo4j_user = "neo4j"
    settings.neo4j_password = "x"
    fake = FakeDriver(connected=True, gds_available=False)
    neo4j_service.inject_test_driver(fake)

    session = session_service.create_guest_session(db, settings, "en")
    r1 = neo4j_service.import_fixture(settings, session.id, "ds1", STARTER_FIVE_V1)
    assert r1["node_count"] == 5
    assert r1["edge_count"] == 4

    # Second import: should be detected as already-loaded (count matches)
    # and return the same summary without adding more rows.
    r2 = neo4j_service.import_fixture(settings, session.id, "ds1", STARTER_FIVE_V1)
    assert r2["node_count"] == 5  # no duplicates added
    assert r2["edge_count"] == 4


def test_import_fixture_raises_when_neo4j_not_configured(db, settings):
    from app.fixtures.graph_seed import STARTER_FIVE_V1
    from app.services import session_service
    from app.core.errors import ServiceUnavailableError
    settings.neo4j_uri = None  # not configured
    session = session_service.create_guest_session(db, settings, "en")
    with pytest.raises(ServiceUnavailableError):
        neo4j_service.import_fixture(settings, session.id, "ds1", STARTER_FIVE_V1)


def test_cleanup_session_drops_only_session_namespace(db, settings):
    """Cleanup must delete only nodes labelled with the session's namespace,
    not other sessions' data."""
    from app.fixtures.graph_seed import STARTER_FIVE_V1
    from app.services import session_service
    import uuid
    settings.neo4j_uri = "bolt://localhost:7687"
    settings.neo4j_user = "neo4j"
    settings.neo4j_password = "x"
    fake = FakeDriver(connected=True)
    neo4j_service.inject_test_driver(fake)

    s1 = session_service.create_guest_session(db, settings, "en")
    s2 = session_service.create_guest_session(db, settings, "en")
    neo4j_service.import_fixture(settings, s1.id, "ds1", STARTER_FIVE_V1)
    neo4j_service.import_fixture(settings, s2.id, "ds1", STARTER_FIVE_V1)

    # Cleanup session 1.
    deleted = neo4j_service.cleanup_session(settings, s1.id)
    assert isinstance(deleted, int)
    # Session 2's data is untouched (still in the fake store).
    ns2 = session_namespace(s2.id)
    label2 = f"__{ns2}__ds_ds1__"
    assert label2 in fake.store.get("labels", {})
