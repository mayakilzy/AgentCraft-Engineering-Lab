"""T06 — NetworkX adapter + algorithms tests.

Verifies the deterministic expected outputs declared in fixtures.
"""
from __future__ import annotations

import pytest

from app.fixtures.graph_seed import (
    DIRECTED_PATH_V1,
    MIXED_KIND_V1,
    STARTER_FIVE_V1,
    get_fixture,
)
from app.services.graph_algorithms import (
    build_digraph_from_fixture,
    components,
    degree_centrality,
    graph_metrics,
    in_out_degrees,
    reachable_ancestors,
    reachable_descendants,
    shortest_path,
    simulate_node_removal_reachability,
)


# ---- Adapter: fixture -> DiGraph ----

def test_build_digraph_from_fixture_has_expected_shape():
    g = build_digraph_from_fixture(STARTER_FIVE_V1)
    assert g.number_of_nodes() == 5
    assert g.number_of_edges() == 4
    # All edge endpoints exist
    for u, v in g.edges():
        assert u in g and v in g


def test_build_digraph_directed_not_conflated_with_undirected():
    """Directed edges: A -> B does NOT imply B -> A."""
    g = build_digraph_from_fixture(DIRECTED_PATH_V1)
    # A -> T1 exists; T1 -> A must NOT.
    assert g.has_edge("A", "T1")
    assert not g.has_edge("T1", "A")


# ---- Shortest path ----

def test_shortest_path_known_directed_path():
    g = build_digraph_from_fixture(DIRECTED_PATH_V1)
    path = shortest_path(g, "A", "T3")
    assert path == DIRECTED_PATH_V1.expected["path_A_to_T3"]
    # Length is number of edges, so len(path) - 1.
    assert len(path) - 1 == DIRECTED_PATH_V1.expected["path_A_to_T3_length"]


def test_shortest_path_disconnected_returns_none():
    g = build_digraph_from_fixture(DIRECTED_PATH_V1)
    # ISO is isolated — no path from A to ISO.
    path = shortest_path(g, "A", "ISO")
    assert path is None


def test_shortest_path_self_unreachable_for_directed_only():
    g = build_digraph_from_fixture(DIRECTED_PATH_V1)
    # B -> T1 exists; T1 -> T2 -> T3 reachable.
    path = shortest_path(g, "B", "T3")
    # B -> T1 -> T2 -> T3
    assert path == ["B", "T1", "T2", "T3"]


def test_shortest_path_missing_node_raises():
    g = build_digraph_from_fixture(STARTER_FIVE_V1)
    with pytest.raises(ValueError):
        shortest_path(g, "GHOST", "T1")


# ---- Centrality ----

def test_degree_centrality_returns_dict_with_all_nodes():
    g = build_digraph_from_fixture(STARTER_FIVE_V1)
    dc = degree_centrality(g)
    assert set(dc.keys()) == set(g.nodes)
    # T4 (FastAPI) has out-degree 3 (uses 3 tools) and in-degree 0;
    # NetworkX degree_centrality = (in+out)/(n-1) = 3/(5-1) = 0.75.
    assert dc["T4"] == pytest.approx(0.75)
    assert dc["T3"] == pytest.approx(0.25)  # in-degree 1


def test_in_out_degrees_split_direction():
    g = build_digraph_from_fixture(STARTER_FIVE_V1)
    deg = in_out_degrees(g)
    assert deg["T4"] == (0, 3)  # in=0, out=3
    assert deg["T3"] == (1, 0)  # in=1, out=0


# ---- Reachability ----

def test_reachable_descendants_directed():
    g = build_digraph_from_fixture(DIRECTED_PATH_V1)
    desc = reachable_descendants(g, "A")
    assert set(desc) == {"T1", "T2", "T3"}
    # ISO is NOT a descendant of A (no path)
    assert "ISO" not in desc


def test_reachable_ancestors_directed():
    g = build_digraph_from_fixture(DIRECTED_PATH_V1)
    anc = reachable_ancestors(g, "T3")
    assert set(anc) == {"A", "B", "T1", "T2"}


def test_reachability_isolated_node():
    g = build_digraph_from_fixture(DIRECTED_PATH_V1)
    assert reachable_descendants(g, "ISO") == []
    assert reachable_ancestors(g, "ISO") == []


# ---- Components ----

def test_components_weakly_connected_includes_iso():
    g = build_digraph_from_fixture(DIRECTED_PATH_V1)
    comp = components(g)
    # ISO forms its own weakly connected component.
    wcc = comp["weakly_connected"]
    iso_comp = [c for c in wcc if "ISO" in c]
    assert len(iso_comp) == 1
    assert iso_comp[0] == ["ISO"]


def test_strongly_connected_components_simple_chain():
    """A simple chain A -> T1 -> T2 -> T3 has no cycles; each node is its
    own SCC.
    """
    g = build_digraph_from_fixture(DIRECTED_PATH_V1)
    comp = components(g)
    scc = comp["strongly_connected"]
    # 6 nodes, no cycles → 6 SCCs
    assert len(scc) == 6


# ---- Graph metrics ----

def test_graph_metrics_keys_and_values():
    g = build_digraph_from_fixture(MIXED_KIND_V1)
    m = graph_metrics(g)
    assert m["node_count"] == 6
    assert m["edge_count"] == 5
    assert m["is_directed"] is True
    assert m["is_dag"] is True  # no cycles
    assert m["weakly_connected_components"] == 1  # all connected
    assert m["strongly_connected_components"] == 6  # no cycles
    assert m["density"] == pytest.approx(5 / (6 * 5))  # 5/(n*(n-1))
    assert m["selfloops"] == []


# ---- Removal simulation ----

def test_simulate_node_removal_does_not_mutate_original():
    g = build_digraph_from_fixture(DIRECTED_PATH_V1)
    n_before = g.number_of_nodes()
    _ = simulate_node_removal_reachability(g, "T1")
    assert g.number_of_nodes() == n_before  # original untouched


# ---- DB-backed adapter (needs the migrated DB) ----

def test_build_digraph_from_db(client):
    """Seed the starter fixture via the API then build a DiGraph from DB
    rows through the adapter."""
    r = client.post("/api/v1/sessions/guest", json={"locale": "en"})
    assert r.status_code == 201
    # Extract the cookie value set by the Set-Cookie header.
    cookie = client.cookies.get("ac_guest")
    assert cookie, "ac_guest cookie not set"

    r = client.post(
        "/api/v1/graph/db-ds/seed",
        json={"dataset_key": "starter-five-v1"},
    )
    assert r.status_code == 200

    # Open a session directly and resolve the GuestSession row.
    from app.db.session import SessionLocal
    from app.services.graph_algorithms import build_digraph
    from sqlalchemy import select
    from app.models.guest_session import GuestSession

    db = SessionLocal()
    try:
        session = db.execute(
            select(GuestSession).where(GuestSession.cookie_token == cookie)
        ).scalar_one()
        g = build_digraph(db, session, "db-ds")
        assert g.number_of_nodes() == 5
        assert g.number_of_edges() == 4
    finally:
        db.close()


# ---- Fixture registry ----

def test_all_three_fixtures_registered():
    assert get_fixture("starter-five-v1") is not None
    assert get_fixture("directed-path-v1") is not None
    assert get_fixture("mixed-kind-v1") is not None
    assert get_fixture("does-not-exist") is None
