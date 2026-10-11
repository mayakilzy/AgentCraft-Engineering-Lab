"""T10 — Relational vs graph parity tests.

Verifies:
- Allowlisted SQL and Cypher return the same canonical result set for
  the parity-v1 fixture.
- Unknown query_key rejected on both sides.
- Timing context (cold/warm/sample/iterations) is reported honestly.
- BLOCKED label when Neo4j is not configured (no fake PASS).
"""
from __future__ import annotations

import pytest

from app.config import Settings
from app.core.errors import InvalidStateError
from app.services import neo4j_service, parity_service
from app.services.cypher_queries import allowlisted_keys, get_query
from app.tests._fake_neo4j import FakeDriver


@pytest.fixture(autouse=True)
def _reset_driver():
    neo4j_service.reset_driver_for_tests()
    yield
    neo4j_service.reset_driver_for_tests()


def test_allowlisted_keys_match_sql_and_cypher():
    sql_keys = set(parity_service.ALLOWLISTED_SQL.keys())
    cypher_keys = set(allowlisted_keys())
    # Every key on the SQL side must also have a Cypher counterpart.
    assert sql_keys.issubset(cypher_keys), (
        f"SQL keys without Cypher counterpart: {sql_keys - cypher_keys}"
    )


def test_unknown_sql_key_rejected():
    with pytest.raises(InvalidStateError):
        parity_service.get_sql("does-not-exist")


def test_unknown_cypher_key_rejected():
    with pytest.raises(InvalidStateError):
        get_query("does-not-exist", "label")


def test_parity_app_uses_tool_direct(db, settings):
    """Seed parity-v1, then run the parity query — SQL and Cypher must
    return the same canonical set of (app, tool) pairs.
    """
    from app.fixtures.graph_seed import PARITY_V1
    from app.services import session_service, graph_service
    settings.neo4j_uri = "bolt://localhost:7687"
    settings.neo4j_user = "neo4j"
    settings.neo4j_password = "x"
    fake = FakeDriver(connected=True, gds_available=False)
    neo4j_service.inject_test_driver(fake)

    session = session_service.create_guest_session(db, settings, "en")
    graph_service.load_fixture(db, settings, session, "parity-ds", "parity-v1")
    # Also import into Neo4j (the fake store).
    neo4j_service.import_fixture(settings, session.id, "parity-ds", PARITY_V1)

    result = parity_service.run_parity(
        db, settings, session, "parity-ds", "app_uses_tool_direct",
        iterations=1, warmup=0,
    )
    assert result.error is None
    assert result.equal is True
    # The canonical set has 4 (app, tool) pairs.
    assert len(result.sql_rows) == 4
    assert len(result.cypher_rows) == 4
    # Timing context reports cold=True (iterations=1, warmup=0).
    assert result.timing_context["cold"] is True
    assert result.timing_context["iterations"] == 1
    assert result.timing_context["sample_size"] == 4
    # Both latencies are non-negative.
    assert result.sql_latency_ms is not None and result.sql_latency_ms >= 0
    assert result.cypher_latency_ms is not None and result.cypher_latency_ms >= 0


def test_parity_blocked_when_neo4j_not_configured(db, settings):
    """When NEO4J_URI is not set, parity must report a BLOCKED error and
    return only the SQL side — never fake PASS."""
    from app.services import session_service, graph_service
    settings.neo4j_uri = None
    session = session_service.create_guest_session(db, settings, "en")
    graph_service.load_fixture(db, settings, session, "parity-ds", "parity-v1")

    result = parity_service.run_parity(
        db, settings, session, "parity-ds", "app_uses_tool_direct",
    )
    assert result.error is not None
    assert "NEO4J_URI not configured" in result.error
    # equal must be False — never fake PASS.
    assert result.equal is False
    # SQL rows are still returned (one side is real).
    assert len(result.sql_rows) == 4


def test_parity_tool_depends_on_tool(db, settings):
    from app.fixtures.graph_seed import MIXED_KIND_V1
    from app.services import session_service, graph_service
    settings.neo4j_uri = "bolt://localhost:7687"
    settings.neo4j_user = "neo4j"
    settings.neo4j_password = "x"
    fake = FakeDriver(connected=True)
    neo4j_service.inject_test_driver(fake)

    session = session_service.create_guest_session(db, settings, "en")
    graph_service.load_fixture(db, settings, session, "mixed-ds", "mixed-kind-v1")
    neo4j_service.import_fixture(settings, session.id, "mixed-ds", MIXED_KIND_V1)

    result = parity_service.run_parity(
        db, settings, session, "mixed-ds", "tool_depends_on_tool",
    )
    assert result.error is None
    assert result.equal is True
    # MIXED_KIND_V1 has 1 TOOL_DEPENDS_ON_TOOL edge (TOOL1 -> TOOL2).
    assert len(result.sql_rows) == 1


def test_parity_kind_counts(db, settings):
    from app.fixtures.graph_seed import MIXED_KIND_V1
    from app.services import session_service, graph_service
    settings.neo4j_uri = "bolt://localhost:7687"
    settings.neo4j_user = "neo4j"
    settings.neo4j_password = "x"
    fake = FakeDriver(connected=True)
    neo4j_service.inject_test_driver(fake)

    session = session_service.create_guest_session(db, settings, "en")
    graph_service.load_fixture(db, settings, session, "mixed-ds", "mixed-kind-v1")
    neo4j_service.import_fixture(settings, session.id, "mixed-ds", MIXED_KIND_V1)

    result = parity_service.run_parity(
        db, settings, session, "mixed-ds", "kind_counts",
    )
    assert result.error is None
    assert result.equal is True
    # 3 kinds: app, tool, skill.
    assert len(result.sql_rows) == 3


def test_parity_warmup_affects_timing_context(db, settings):
    """When warmup > 0, the timing context must report cold=False."""
    from app.fixtures.graph_seed import PARITY_V1
    from app.services import session_service, graph_service
    settings.neo4j_uri = "bolt://localhost:7687"
    settings.neo4j_user = "neo4j"
    settings.neo4j_password = "x"
    fake = FakeDriver(connected=True)
    neo4j_service.inject_test_driver(fake)

    session = session_service.create_guest_session(db, settings, "en")
    graph_service.load_fixture(db, settings, session, "parity-warmup", "parity-v1")
    neo4j_service.import_fixture(settings, session.id, "parity-warmup", PARITY_V1)

    result = parity_service.run_parity(
        db, settings, session, "parity-warmup", "app_uses_tool_direct",
        iterations=3, warmup=2,
    )
    assert result.error is None
    assert result.timing_context["cold"] is False
    assert result.timing_context["iterations"] == 3
    assert result.timing_context["warmup"] == 2


def test_parity_unknown_query_key_rejected(db, settings):
    from app.services import session_service
    settings.neo4j_uri = "bolt://localhost:7687"
    settings.neo4j_user = "neo4j"
    settings.neo4j_password = "x"
    fake = FakeDriver(connected=True)
    neo4j_service.inject_test_driver(fake)

    session = session_service.create_guest_session(db, settings, "en")
    result = parity_service.run_parity(
        db, settings, session, "any-ds", "does-not-exist",
    )
    # The result reports a non-equal verdict with an honest error.
    assert result.error is not None
    assert "not allowlisted" in result.error
    assert result.equal is False
