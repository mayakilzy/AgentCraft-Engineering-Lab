"""NetworkX adapter + algorithms.

Per the architecture contract §6: build a directed NetworkX DiGraph from
the relational (session-scoped) graph; provide shortest path, degree
centrality, reachability (descendants), and component analysis with
explicit directed semantics. SQL and Cypher parity is built in G03.

Outputs are deterministic given deterministic fixtures. No random graph
is ever generated.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import networkx as nx
from sqlalchemy.orm import Session

from app.models.guest_session import GuestSession
from app.models.graph import GraphEdge, GraphNode
from app.services.graph_service import list_nodes, list_edges


# ---- Adapter: relational -> NetworkX ----

@dataclass(frozen=True)
class RelationalNode:
    """Snapshot of a graph node row for algorithm input."""
    node_ref: str
    kind: str
    label: str


def build_digraph(
    db: Session, session: GuestSession, dataset_id: str
) -> nx.DiGraph:
    """Build a directed NetworkX DiGraph from the session-scoped relational
    graph. Node ids are the stable `node_ref` values (not DB UUIDs) so
    algorithm outputs are stable across reruns.

    Edge direction matches the storage convention:
        APP_USES_TOOL          : app -> tool
        TOOL_DEPENDS_ON_TOOL    : consumer -> provider
        APP_NEEDS_SKILL         : app -> skill
    """
    nodes = list_nodes(db, session, dataset_id)
    edges = list_edges(db, session, dataset_id)

    g = nx.DiGraph()
    for n in nodes:
        g.add_node(
            n.node_ref,
            kind=n.kind,
            label=n.label,
        )
    for e, src_ref, tgt_ref in edges:
        g.add_edge(
            src_ref,
            tgt_ref,
            relation=e.relation,
            edge_id=str(e.id),
        )
    return g


def build_digraph_from_fixture(fixture) -> nx.DiGraph:
    """Build a DiGraph directly from a `GraphFixture` (no DB roundtrip).

    Used by tests and by validators that need to reason about expected
    outputs without persisting to a session-scoped dataset first.
    """
    g = nx.DiGraph()
    for n in fixture.nodes:
        g.add_node(n.ref, kind=n.kind, label=n.label)
    for e in fixture.edges:
        g.add_edge(e.source_ref, e.target_ref, relation=e.relation)
    return g


# ---- Algorithms ----

def shortest_path(
    g: nx.DiGraph, source: str, target: str
) -> Optional[List[str]]:
    """Return the shortest directed path source -> target, or None if no
    path exists (NetworkX raises `NetworkXNoPath` for disconnected pairs).
    """
    if source not in g or target not in g:
        raise ValueError(f"node not in graph: {source if source not in g else target}")
    try:
        return nx.shortest_path(g, source=source, target=target)
    except nx.NetworkXNoPath:
        return None
    except nx.NodeNotFound as exc:
        # Should not happen because we checked above, but be defensive.
        raise ValueError(str(exc)) from exc


def degree_centrality(g: nx.DiGraph) -> Dict[str, float]:
    """NetworkX degree centrality: in-degree + out-degree normalized."""
    return nx.degree_centrality(g)


def in_out_degrees(g: nx.DiGraph) -> Dict[str, Tuple[int, int]]:
    """Return `(in_degree, out_degree)` per node. Useful for "most connected"
    labels — but the contract warns: 'Do not confuse most central with
    operational criticality.'
    """
    return {n: (g.in_degree(n), g.out_degree(n)) for n in g.nodes}


def reachable_descendants(g: nx.DiGraph, source: str) -> List[str]:
    """All nodes reachable from `source` following directed edges
    (excluding the source itself unless a cycle returns to it)."""
    if source not in g:
        raise ValueError(f"node not in graph: {source}")
    return list(nx.descendants(g, source))


def reachable_ancestors(g: nx.DiGraph, target: str) -> List[str]:
    """All nodes that can reach `target` following directed edges."""
    if target not in g:
        raise ValueError(f"node not in graph: {target}")
    return list(nx.ancestors(g, target))


def components(g: nx.DiGraph) -> Dict[str, List[List[str]]]:
    """Component analysis. Returns both weakly and strongly connected
    components. Disconnected pairs are explicitly reported via
    `weakly_connected_components` so the UI can highlight isolates.
    """
    return {
        "weakly_connected": [list(c) for c in nx.weakly_connected_components(g)],
        "strongly_connected": [list(c) for c in nx.strongly_connected_components(g)],
    }


def graph_metrics(g: nx.DiGraph) -> Dict[str, object]:
    """Stable summary metrics used by validators and the UI status panel."""
    return {
        "node_count": g.number_of_nodes(),
        "edge_count": g.number_of_edges(),
        "is_directed": g.is_directed(),
        "is_dag": nx.is_directed_acyclic_graph(g),
        "weakly_connected_components": nx.number_weakly_connected_components(g),
        "strongly_connected_components": nx.number_strongly_connected_components(g),
        "density": nx.density(g),
        "selfloops": list(nx.nodes_with_selfloops(g)),
    }


# ---- Removal simulation (used by E05 in G03+, exposed early as a stable op) ----

def simulate_node_removal_reachability(
    g: nx.DiGraph, target: str
) -> Dict[str, List[str]]:
    """For each predecessor of `target`, compute which other nodes would
    lose their path to `target` if `target` were removed. Used by critical-
    dependency analysis; we do NOT mutate the original graph.
    """
    if target not in g:
        raise ValueError(f"node not in graph: {target}")
    out: Dict[str, List[str]] = {}
    # The nodes that currently can reach `target`:
    current_reachers = reachable_ancestors(g, target)
    # Simulate removal by copying the graph.
    g2 = g.copy()
    g2.remove_node(target)
    for node in current_reachers:
        # After removing `target`, find which of the other current-reachers
        # still can reach `node` (i.e., did they lose a path that went
        # through `target`?).
        # This is a simplistic reachability delta; E05 in G05 will refine.
        reachers_after = reachable_ancestors(g2, node)
        lost = sorted(set(current_reachers) - set(reachers_after) - {target, node})
        out[node] = lost
    return out
