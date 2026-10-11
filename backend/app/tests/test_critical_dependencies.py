"""T12 + G02 review note #1 — simulate_node_removal_reachability + critical_dependencies.

Tests cover:
- Alternative path preservation (a node stays reachable via the other path).
- Directed semantics (removing X only affects downstream, not upstream).
- No mutation of the original graph.
- Critical dependencies comparison (impact vs naive centrality).
"""
from __future__ import annotations

import pytest
import networkx as nx

from app.fixtures.graph_seed import (
    DIRECTED_PATH_V1,
    STARTER_FIVE_V1,
    get_fixture,
)
from app.services.graph_algorithms import (
    build_digraph_from_fixture,
    critical_dependencies,
    simulate_node_removal_reachability,
)


# ---- Linear chain: removing middle node cuts off the tail ----

def test_removal_linear_chain_cuts_downstream():
    """A -> T1 -> T2 -> T3 (directed). Removing T1:
      - From A, the lost set is {T2, T3} (downstream, unreachable now).
      - From B (B -> T1 -> T2 -> T3), lost is also {T2, T3}.
      - From T1's own row, not present (T1 was removed).
      - From T2, lost is {T3} (T2 still cannot reach T1 anymore because
        direction is reversed; but T2 couldn't reach T1 before either, so
        no change there; only downstream T3 was reachable from T2 via the
        edge T2 -> T3 which is still there, so T3 stays reachable from T2).
    Wait — let me trace exactly:
      T2's descendants in DIRECTED_PATH_V1: {T3}. After removing T1: T2's
      descendants are still {T3} (the edge T2 -> T3 is intact). So lost = [].
    """
    g = build_digraph_from_fixture(DIRECTED_PATH_V1)
    delta = simulate_node_removal_reachability(g, "T1")

    assert delta["A"] == ["T2", "T3"]   # T1 -> T2 -> T3 was the only path from A
    assert delta["B"] == ["T2", "T3"]   # same for B
    assert delta["T2"] == []            # T2 -> T3 still intact
    assert delta["T3"] == []            # T3 has no descendants
    assert delta["ISO"] == []           # isolated, no descendants


# ---- Alternative path: removing one of two parallel intermediates ----

def test_removal_alternative_path_preserves_reachability():
    """A -> T1 -> T3 and A -> T2 -> T3 (two parallel paths). Removing T1
    must NOT make T3 unreachable from A, because A -> T2 -> T3 is still
    intact.
    """
    g = nx.DiGraph()
    g.add_node("A", kind="app", label="A")
    g.add_node("T1", kind="tool", label="T1")
    g.add_node("T2", kind="tool", label="T2")
    g.add_node("T3", kind="tool", label="T3")
    g.add_edge("A", "T1", relation="R")
    g.add_edge("A", "T2", relation="R")
    g.add_edge("T1", "T3", relation="R")
    g.add_edge("T2", "T3", relation="R")

    delta = simulate_node_removal_reachability(g, "T1")
    # T3 still reachable from A via T2; only T1's own descendants that are
    # not reachable via the alternative path are lost. T3 was reachable from
    # A before (via T1 -> T3 OR T2 -> T3); after removing T1 it's reachable
    # via T2 -> T3, so not lost.
    assert delta["A"] == []
    # T2's descendants: {T3} before and after.
    assert delta["T2"] == []
    # T3 has no descendants.
    assert delta["T3"] == []


def test_removal_alternative_path_one_branch_lost():
    """A -> T1 -> T3 (path 1) and A -> T2 -> T4 (path 2). Removing T1:
      - From A, T3 becomes unreachable (its only path was via T1).
      - From A, T4 stays reachable via T2 (T2 -> T4 is intact).
      - From T2, T4 was reachable before AND after (T2 -> T4 is intact);
        removing T1 has no effect on T2's reachability.
    """
    g = nx.DiGraph()
    for n in ("A", "T1", "T2", "T3", "T4"):
        g.add_node(n, kind="tool", label=n)
    g.add_edge("A", "T1", relation="R")
    g.add_edge("A", "T2", relation="R")
    g.add_edge("T1", "T3", relation="R")
    g.add_edge("T2", "T4", relation="R")

    delta = simulate_node_removal_reachability(g, "T1")
    assert delta["A"] == ["T3"]   # only T3 lost
    assert delta["T2"] == []       # T2's reach unaffected by T1 removal
    assert delta["T3"] == []
    assert delta["T4"] == []


# ---- Direction semantics: removing a sink only ----

def test_removal_of_sink_has_no_downstream_impact():
    """Removing T3 (a sink in DIRECTED_PATH_V1) should produce empty lost
    sets for every source because T3 has no descendants.
    """
    g = build_digraph_from_fixture(DIRECTED_PATH_V1)
    delta = simulate_node_removal_reachability(g, "T3")
    for src, lost in delta.items():
        assert lost == [], f"{src}: expected no loss, got {lost}"


def test_removal_of_source_does_not_break_its_inbound():
    """Removing A (a pure source) does not make any node unreachable from
    the OTHER sources because A's only downstream contribution was itself
    a path origin, not a bridge.
    """
    g = build_digraph_from_fixture(DIRECTED_PATH_V1)
    delta = simulate_node_removal_reachability(g, "A")
    # No node downstream of A depended solely on A; B -> T1 -> T2 -> T3
    # still works after A is removed.
    for src, lost in delta.items():
        assert lost == [], f"{src}: expected no loss when removing source A"


# ---- No mutation ----

def test_removal_does_not_mutate_original():
    g = build_digraph_from_fixture(DIRECTED_PATH_V1)
    nodes_before = set(g.nodes)
    edges_before = set(g.edges)
    _ = simulate_node_removal_reachability(g, "T1")
    assert set(g.nodes) == nodes_before
    assert set(g.edges) == edges_before


# ---- Missing node ----

def test_removal_missing_node_raises():
    g = build_digraph_from_fixture(STARTER_FIVE_V1)
    with pytest.raises(ValueError):
        simulate_node_removal_reachability(g, "GHOST")


# ---- critical_dependencies: directed impact vs naive centrality ----

def test_critical_dependencies_reports_both_metrics():
    g = build_digraph_from_fixture(DIRECTED_PATH_V1)
    cd = critical_dependencies(g, "T1")
    assert cd["target"] == "T1"
    # T1 is on the path A -> T1 -> T2 -> T3, plus B -> T1 -> ...
    # Removing T1 should make T2 and T3 unreachable from A and B.
    assert cd["impact_set"] == ["T2", "T3"]
    assert cd["impact_size"] == 2
    # in-degree of T1: A and B point to it → 2
    assert cd["target_in_degree"] == 2
    # out-degree of T1: 1 (T1 -> T2)
    assert cd["target_out_degree"] == 1
    assert cd["target_degree_centrality"] == pytest.approx(3 / 5)  # (2+1)/(6-1)
    assert "note" in cd and "centrality" in cd["note"].lower()


def test_critical_dependencies_sink_has_zero_impact():
    """T3 is a sink; removing it impacts nothing downstream."""
    g = build_digraph_from_fixture(DIRECTED_PATH_V1)
    cd = critical_dependencies(g, "T3")
    assert cd["impact_set"] == []
    assert cd["impact_size"] == 0
    # T3 in-degree is 1 (T2 -> T3), out-degree is 0
    assert cd["target_in_degree"] == 1
    assert cd["target_out_degree"] == 0


def test_critical_dependencies_isolated_node_no_impact():
    """ISO has in-degree 0, out-degree 0; removing it changes nothing."""
    g = build_digraph_from_fixture(DIRECTED_PATH_V1)
    cd = critical_dependencies(g, "ISO")
    assert cd["impact_set"] == []
    assert cd["impact_size"] == 0
    assert cd["target_in_degree"] == 0
    assert cd["target_out_degree"] == 0


def test_high_centrality_does_not_imply_high_impact():
    """A node can be 'most central' by degree but have low removal impact
    when alternative paths exist. The contract calls this out explicitly.
    """
    # Topology: S -> T1, S -> T2, S -> T3 (T3 directly).
    # T1 -> T2 and T2 -> T3 (so S has alternative downstream reachability).
    g = nx.DiGraph()
    for n in ("S", "T1", "T2", "T3"):
        g.add_node(n, kind="tool", label=n)
    g.add_edge("S", "T1")
    g.add_edge("S", "T2")
    g.add_edge("S", "T3")
    g.add_edge("T1", "T2")
    g.add_edge("T2", "T3")

    cd_S = critical_dependencies(g, "S")
    cd_T1 = critical_dependencies(g, "T1")

    # Removing S: no other node depends on S (S has no inbound). The impact
    # set measures what becomes unreachable FROM OTHER SOURCES. None of the
    # other nodes (T1, T2, T3) was reachable from another non-S source
    # before, so removing S cannot make anything newly unreachable.
    assert cd_S["impact_set"] == []

    # Removing T1: T2 and T3 were reachable from S directly (S -> T2, S -> T3);
    # so they stay reachable after removing T1. impact_set is empty.
    assert cd_T1["impact_set"] == []

    # Yet S has the highest degree centrality (3 edges out + 0 in = 3 total).
    dc = nx.degree_centrality(g)
    max_dc = max(dc.values())
    assert dc["S"] == max_dc
    # And S has ZERO operational impact when removed — exactly the
    # contract's caution: 'most central' is NOT 'operationally critical'.
    assert cd_S["impact_size"] == 0

    # By contrast, removing T2 makes T3 unreachable from T1 (T1's only path
    # to T3 was T1 -> T2 -> T3). So T2 has non-zero impact even though S has
    # higher centrality. This is the directed semantics the contract requires.
    cd_T2 = critical_dependencies(g, "T2")
    assert "T3" in cd_T2["impact_set"]
    assert cd_T2["impact_size"] >= 1
