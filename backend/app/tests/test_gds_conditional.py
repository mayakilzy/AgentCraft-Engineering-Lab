"""T11 — GDS conditional tests.

Per A05: 'if GDS licensing unavailable, it may be explicitly marked
NOT_AVAILABLE with NetworkX lesson alternative; do not certify native GDS
behavior.'

Tests:
- When Neo4j is not connected → NetworkX fallback, provider='networkx_fallback'
- When Neo4j connected but GDS missing/unlicensed → NetworkX fallback, labelled
- When GDS available + licensed → GDS Louvain path attempted
- The NetworkX fallback runs greedy_modularity_communities and labels itself
  honestly (provider='networkx_fallback', never 'gds')
- COMMUNITIES_V1 fixture yields 3 communities in the fallback path
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


def test_gds_not_connected_uses_networkx_fallback(db, settings):
    """When NEO4J_URI is not configured, the result must be labelled
    networkx_fallback — never gds."""
    settings.neo4j_uri = None
    session = session_service.create_guest_session(db, settings, "en")
    graph_service.load_fixture(db, settings, session, "comm-ds", "communities-v1")

    result = gds_service.detect_communities(db, settings, session, "comm-ds")
    assert result.provider == "networkx_fallback"
    assert result.algorithm == "greedy_modularity"
    assert "NOT GDS" in result.note
    assert "neo4j_not_connected" in result.note
    # The fixture has 3 obvious clusters.
    assert len(result.communities) == 3


def test_gds_connected_no_gds_uses_networkx_fallback(db, settings):
    settings.neo4j_uri = "bolt://localhost:7687"
    settings.neo4j_user = "neo4j"
    settings.neo4j_password = "x"
    settings.gds_licensed = False
    fake = FakeDriver(connected=True, gds_available=False)
    neo4j_service.inject_test_driver(fake)

    session = session_service.create_guest_session(db, settings, "en")
    graph_service.load_fixture(db, settings, session, "comm-ds", "communities-v1")
    from app.fixtures.graph_seed import COMMUNITIES_V1
    neo4j_service.import_fixture(settings, session.id, "comm-ds", COMMUNITIES_V1)

    result = gds_service.detect_communities(db, settings, session, "comm-ds")
    assert result.provider == "networkx_fallback"
    assert "NOT GDS" in result.note
    assert "gds_available=False" in result.note
    assert "gds_licensed=False" in result.note


def test_gds_connected_gds_available_unlicensed_uses_fallback(db, settings):
    settings.neo4j_uri = "bolt://localhost:7687"
    settings.neo4j_user = "neo4j"
    settings.neo4j_password = "x"
    settings.gds_licensed = False  # unlicensed
    fake = FakeDriver(connected=True, gds_available=True)
    neo4j_service.inject_test_driver(fake)

    session = session_service.create_guest_session(db, settings, "en")
    graph_service.load_fixture(db, settings, session, "comm-ds", "communities-v1")
    from app.fixtures.graph_seed import COMMUNITIES_V1
    neo4j_service.import_fixture(settings, session.id, "comm-ds", COMMUNITIES_V1)

    result = gds_service.detect_communities(db, settings, session, "comm-ds")
    assert result.provider == "networkx_fallback"
    assert "NOT GDS" in result.note
    assert "gds_licensed=False" in result.note


def test_gds_licensed_attempts_gds_path(db, settings):
    """When GDS is available AND licensed, the code attempts the GDS Louvain
    path. With our fake, the gds.louvain.stream call may fail (the fake
    returns a sparse result), in which case the code falls back to NetworkX
    and labels it honestly as a fallback. Either outcome is acceptable
    provided the provenance is correct.

    We assert: provider is either 'gds' (if the fake Louvain succeeded) or
    'networkx_fallback' (if the fake call failed). Never a silent PASS.
    """
    settings.neo4j_uri = "bolt://localhost:7687"
    settings.neo4j_user = "neo4j"
    settings.neo4j_password = "x"
    settings.gds_licensed = True
    fake = FakeDriver(connected=True, gds_available=True)
    neo4j_service.inject_test_driver(fake)

    session = session_service.create_guest_session(db, settings, "en")
    graph_service.load_fixture(db, settings, session, "comm-ds", "communities-v1")
    from app.fixtures.graph_seed import COMMUNITIES_V1
    neo4j_service.import_fixture(settings, session.id, "comm-ds", COMMUNITIES_V1)

    result = gds_service.detect_communities(db, settings, session, "comm-ds")
    # Either GDS provider (real success) or honest NetworkX fallback.
    assert result.provider in ("gds", "networkx_fallback")
    if result.provider == "networkx_fallback":
        assert "NOT GDS" in result.note
        assert "gds_call_failed" in result.note
    # Communities returned either way.
    assert isinstance(result.communities, list)


def test_communities_v1_networkx_fallback_yields_expected_clusters(db, settings):
    """Sanity: the NetworkX fallback on COMMUNITIES_V1 should partition
    into the 3 declared clusters (order-independent)."""
    settings.neo4j_uri = None
    session = session_service.create_guest_session(db, settings, "en")
    graph_service.load_fixture(db, settings, session, "comm-ds", "communities-v1")

    result = gds_service.detect_communities(db, settings, session, "comm-ds")
    assert result.provider == "networkx_fallback"
    # Each of A1/A2/A3 should be in the same community; same for B and C.
    by_node = {n: c for c in result.communities for n in c}
    assert by_node["A1"] == by_node["A2"] == by_node["A3"]
    assert by_node["B1"] == by_node["B2"] == by_node["B3"]
    assert by_node["C1"] == by_node["C2"] == by_node["C3"]
    # And the three clusters are distinct.
    assert by_node["A1"] != by_node["B1"]
    assert by_node["A1"] != by_node["C1"]
    assert by_node["B1"] != by_node["C1"]
    # 3 communities total.
    assert len(result.communities) == 3


def test_gds_provider_never_mislabels_fallback_as_gds(db, settings):
    """Hard invariant: when GDS is unavailable, the result.provider must
    NEVER be 'gds'. This catches any future regression that would
    mislabel a NetworkX fallback as GDS execution."""
    settings.neo4j_uri = None
    session = session_service.create_guest_session(db, settings, "en")
    graph_service.load_fixture(db, settings, session, "comm-ds", "communities-v1")
    result = gds_service.detect_communities(db, settings, session, "comm-ds")
    assert result.provider != "gds"
    assert result.provider == "networkx_fallback"
