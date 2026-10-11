"""T12 — E05 critical dependencies golden tests.

Per the contract §6: directed impact vs naive centrality; dependency
removal simulation on a copy only, never mutate user graph.

The DEPENDENCY_IMPACT_V1 fixture declares expected impact sets:
- removing T1 → impact_set = ['T3'] (B loses path to T3)
- removing T2 → impact_set = [] (T3 still reachable from A via T1)
"""
from __future__ import annotations

import pytest

from app.fixtures.graph_seed import DEPENDENCY_IMPACT_V1
from app.services import graph_service, session_service
from app.services.graph_algorithms import (
    build_digraph,
    critical_dependencies,
)


def _seed(db, settings, dataset_id="impact-ds"):
    session = session_service.create_guest_session(db, settings, "en")
    graph_service.load_fixture(db, settings, session, dataset_id, "dependency-impact-v1")
    return session, dataset_id


def test_dependency_impact_fixture_shape(db, settings):
    """Sanity: the fixture has the expected counts."""
    session, ds = _seed(db, settings)
    g = build_digraph(db, session, ds)
    assert g.number_of_nodes() == DEPENDENCY_IMPACT_V1.expected["node_count"]
    assert g.number_of_edges() == DEPENDENCY_IMPACT_V1.expected["edge_count"]


def test_removal_T1_impact_set_matches_golden(db, settings):
    """Removing T1: from B, T3 becomes unreachable (B → T1 → T3 was the
    only path). From A, T3 stays reachable via T2. impact_set = ['T3'].
    """
    session, ds = _seed(db, settings)
    g = build_digraph(db, session, ds)
    cd = critical_dependencies(g, "T1")
    assert cd["impact_set"] == DEPENDENCY_IMPACT_V1.expected["removal_T1_impact_set"]
    assert cd["impact_size"] == 1


def test_removal_T2_impact_set_matches_golden(db, settings):
    """Removing T2: T3 stays reachable from A (via T1) and from B (via T1).
    impact_set = []. This is the contract's caution: removing a node that
    has alternative paths is operationally low-impact even if its
    centrality is high.
    """
    session, ds = _seed(db, settings)
    g = build_digraph(db, session, ds)
    cd = critical_dependencies(g, "T2")
    assert cd["impact_set"] == DEPENDENCY_IMPACT_V1.expected["removal_T2_impact_set"]
    assert cd["impact_size"] == 0


def test_removal_does_not_mutate_user_graph(db, settings):
    """Hard contract requirement: removal simulation never mutates the
    user's stored graph. We assert via DB row counts before/after."""
    session, ds = _seed(db, settings)
    summary_before = graph_service.get_dataset_summary(db, session, ds)

    g = build_digraph(db, session, ds)
    _ = critical_dependencies(g, "T1")

    summary_after = graph_service.get_dataset_summary(db, session, ds)
    assert summary_before == summary_after


def test_centrality_reported_separately_from_impact(db, settings):
    """The function surfaces BOTH degree centrality AND impact_size so
    callers cannot conflate them. T1 has higher in-degree than T2 (B and
    A both point to T1; only A points to T2), but T1 also has higher
    removal impact than T2. This is the only case where they happen to
    align — the test asserts the function reports them as distinct signals.
    """
    session, ds = _seed(db, settings)
    g = build_digraph(db, session, ds)
    cd_T1 = critical_dependencies(g, "T1")
    cd_T2 = critical_dependencies(g, "T2")

    # T1 in-degree = 2 (A, B); T2 in-degree = 1 (A only).
    assert cd_T1["target_in_degree"] == 2
    assert cd_T2["target_in_degree"] == 1
    # Impact: T1 → 1, T2 → 0.
    assert cd_T1["impact_size"] == 1
    assert cd_T2["impact_size"] == 0
    # The note explicitly calls out the distinction.
    assert "centrality" in cd_T1["note"].lower()
    assert "criticality" in cd_T1["note"].lower()


def test_critical_deps_endpoint(client, db, settings):
    """End-to-end: the /api/v1/lab/critical/{dataset_id}/{node_ref}
    endpoint returns the same impact_set as the direct call."""
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    client.post("/api/v1/graph/impact-e2e/seed", json={"dataset_key": "dependency-impact-v1"})

    r = client.get("/api/v1/lab/critical/impact-e2e/T1")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["target"] == "T1"
    assert body["impact_set"] == ["T3"]
    assert body["impact_size"] == 1
    assert body["target_in_degree"] == 2
    assert body["target_out_degree"] == 1


def test_critical_deps_endpoint_missing_node_404(client, db, settings):
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    client.post("/api/v1/graph/impact-404/seed", json={"dataset_key": "dependency-impact-v1"})

    r = client.get("/api/v1/lab/critical/impact-404/GHOST")
    assert r.status_code == 404
    body = r.json()
    assert body["code"] == "not_found"
