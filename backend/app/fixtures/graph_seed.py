"""Synthetic graph fixtures — synthetic AgentCraft-style sample, NOT scraped.

Apps A/B/C, tools T1.., skills S1.., dependency cycle example and
disconnected components. Explicit nodes/edges and precomputed expected
results committed to fixture; checksum/version.

Concrete datasets for E01–E10 are wired in G02/G05; this module exposes
the shape and a single tiny starter fixture (`starter-five-v1`) so T04
can verify the schema round-trips.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class FixtureNode:
    ref: str
    kind: str
    label: str
    attributes: dict = field(default_factory=dict)


@dataclass(frozen=True)
class FixtureEdge:
    source_ref: str
    target_ref: str
    relation: str
    attributes: dict = field(default_factory=dict)


@dataclass(frozen=True)
class GraphFixture:
    """A complete deterministic dataset. Fixtures are immutable; reruns are
    reproducible because the seed is versioned (no implicit random graph)."""

    dataset_key: str
    version: str
    nodes: tuple[FixtureNode, ...]
    edges: tuple[FixtureEdge, ...]
    expected: dict = field(default_factory=dict)

    @property
    def checksum_inputs(self) -> Iterable[str]:
        """Strings that contribute to a content hash; ordered for stability."""
        for n in self.nodes:
            yield f"n|{n.ref}|{n.kind}|{n.label}"
        for e in self.edges:
            yield f"e|{e.source_ref}|{e.target_ref}|{e.relation}"


# Starter fixture: 5 tools, 4 directed edges. Used by E01 in G05.
STARTER_FIVE_V1 = GraphFixture(
    dataset_key="starter-five-v1",
    version="1.0.0",
    nodes=(
        FixtureNode("T1", "tool", "NetworkX"),
        FixtureNode("T2", "tool", "Cytoscape.js"),
        FixtureNode("T3", "tool", "PostgreSQL"),
        FixtureNode("T4", "tool", "FastAPI"),
        FixtureNode("T5", "tool", "OpenTelemetry"),
    ),
    edges=(
        FixtureEdge("T4", "T3", "APP_USES_TOOL"),  # FastAPI -> PostgreSQL
        FixtureEdge("T4", "T1", "APP_USES_TOOL"),  # FastAPI -> NetworkX
        FixtureEdge("T4", "T5", "APP_USES_TOOL"),  # FastAPI -> OpenTelemetry
        FixtureEdge("T2", "T1", "TOOL_DEPENDS_ON_TOOL"),  # Cytoscape -> NetworkX
    ),
    expected={
        "node_count": 5,
        "edge_count": 4,
        "dangling_edges": False,
        # Per G02 reviewer note #3: the E01 validator now checks endpoint
        # integrity, so the fixture declares its full node_refs set and
        # edge triplets. The validator asserts both presence and that no
        # seeded edge has a dangling endpoint.
        "node_refs": ["T1", "T2", "T3", "T4", "T5"],
        "edges": [
            ("T4", "T3", "APP_USES_TOOL"),
            ("T4", "T1", "APP_USES_TOOL"),
            ("T4", "T5", "APP_USES_TOOL"),
            ("T2", "T1", "TOOL_DEPENDS_ON_TOOL"),
        ],
    },
)


# E02 fixture: directed dependency path A -> T3 with a known shortest path
# plus a disconnected pair to verify unreachable handling.
DIRECTED_PATH_V1 = GraphFixture(
    dataset_key="directed-path-v1",
    version="1.0.0",
    nodes=(
        FixtureNode("A", "app", "App A"),
        FixtureNode("B", "app", "App B"),
        FixtureNode("T1", "tool", "Tool T1"),
        FixtureNode("T2", "tool", "Tool T2"),
        FixtureNode("T3", "tool", "Tool T3 (target)"),
        FixtureNode("ISO", "tool", "Isolated"),  # disconnected component
    ),
    edges=(
        FixtureEdge("A", "T1", "APP_USES_TOOL"),
        FixtureEdge("T1", "T2", "TOOL_DEPENDS_ON_TOOL"),
        FixtureEdge("T2", "T3", "TOOL_DEPENDS_ON_TOOL"),
        FixtureEdge("B", "T1", "APP_USES_TOOL"),
    ),
    expected={
        "node_count": 6,
        "edge_count": 4,
        # A -> T1 -> T2 -> T3 (length 3 = 4 nodes)
        "path_A_to_T3": ["A", "T1", "T2", "T3"],
        "path_A_to_T3_length": 3,
        # ISO is unreachable from A
        "path_A_to_ISO": None,
    },
)


# E03 fixture: mixed-kind graph for layout/filter/select exercises.
MIXED_KIND_V1 = GraphFixture(
    dataset_key="mixed-kind-v1",
    version="1.0.0",
    nodes=(
        FixtureNode("APP1", "app", "App One"),
        FixtureNode("APP2", "app", "App Two"),
        FixtureNode("TOOL1", "tool", "Tool One"),
        FixtureNode("TOOL2", "tool", "Tool Two"),
        FixtureNode("SKILL1", "skill", "Skill Alpha"),
        FixtureNode("SKILL2", "skill", "Skill Beta"),
    ),
    edges=(
        FixtureEdge("APP1", "TOOL1", "APP_USES_TOOL"),
        FixtureEdge("APP1", "SKILL1", "APP_NEEDS_SKILL"),
        FixtureEdge("APP2", "TOOL2", "APP_USES_TOOL"),
        FixtureEdge("APP2", "SKILL2", "APP_NEEDS_SKILL"),
        FixtureEdge("TOOL1", "TOOL2", "TOOL_DEPENDS_ON_TOOL"),
    ),
    expected={
        "node_count": 6,
        "edge_count": 5,
        "kinds": ("app", "tool", "skill"),
        "app_nodes": ["APP1", "APP2"],
        "skill_nodes": ["SKILL1", "SKILL2"],
        "tool_nodes": ["TOOL1", "TOOL2"],
    },
)


# E04 fixture: SQL vs Cypher parity. Two apps use the same two tools.
PARITY_V1 = GraphFixture(
    dataset_key="parity-v1",
    version="1.0.0",
    nodes=(
        FixtureNode("APP_A", "app", "App A"),
        FixtureNode("APP_B", "app", "App B"),
        FixtureNode("TOOL_X", "tool", "Tool X"),
        FixtureNode("TOOL_Y", "tool", "Tool Y"),
    ),
    edges=(
        FixtureEdge("APP_A", "TOOL_X", "APP_USES_TOOL"),
        FixtureEdge("APP_A", "TOOL_Y", "APP_USES_TOOL"),
        FixtureEdge("APP_B", "TOOL_X", "APP_USES_TOOL"),
        FixtureEdge("APP_B", "TOOL_Y", "APP_USES_TOOL"),
    ),
    expected={
        "node_count": 4,
        "edge_count": 4,
        "app_uses_tool_direct_pairs": [
            ("App A", "Tool X"),
            ("App A", "Tool Y"),
            ("App B", "Tool X"),
            ("App B", "Tool Y"),
        ],
    },
)


# E05 fixture: directed impact analysis.
# Topology: A -> T1 -> T3 (T1 is critical for T3 from A); A -> T2 -> T3 (alternative).
# Removing T1 still leaves T3 reachable from A via T2.
# Removing T2 still leaves T3 reachable from A via T1.
# Removing T1 from B: B -> T1 -> T3 is the only path → T3 becomes unreachable.
DEPENDENCY_IMPACT_V1 = GraphFixture(
    dataset_key="dependency-impact-v1",
    version="1.0.0",
    nodes=(
        FixtureNode("A", "app", "App A"),
        FixtureNode("B", "app", "App B"),
        FixtureNode("T1", "tool", "Tool T1"),
        FixtureNode("T2", "tool", "Tool T2"),
        FixtureNode("T3", "tool", "Tool T3"),
    ),
    edges=(
        FixtureEdge("A", "T1", "APP_USES_TOOL"),
        FixtureEdge("A", "T2", "APP_USES_TOOL"),
        FixtureEdge("B", "T1", "APP_USES_TOOL"),
        FixtureEdge("T1", "T3", "TOOL_DEPENDS_ON_TOOL"),
        FixtureEdge("T2", "T3", "TOOL_DEPENDS_ON_TOOL"),
    ),
    expected={
        "node_count": 5,
        "edge_count": 5,
        # Removing T1: from A, T3 still reachable via T2 → lost = [].
        # From B, T3 unreachable (B -> T1 -> T3 was the only path) → lost = ["T3"].
        "removal_T1_impact_set": ["T3"],
        "removal_T1_loses_for_B": ["T3"],
        "removal_T1_loses_for_A": [],
        # Removing T2: symmetric — from A, T3 still reachable via T1; lost = [].
        # No other source depends on T2, so impact_set = [] (removing T2 only
        # affects paths FROM T2 itself, but T2 has no descendants except T3
        # which is also reachable via T1).
        "removal_T2_impact_set": [],
    },
)


# E06 fixture: 3 obvious clusters for community detection.
# Cluster 1: A1, A2, A3 (densely connected)
# Cluster 2: B1, B2, B3 (densely connected)
# Cluster 3: C1, C2, C3 (densely connected)
# Single inter-cluster edge: A1 -> B1 (keeps WCC = 1 but communities = 3).
COMMUNITIES_V1 = GraphFixture(
    dataset_key="communities-v1",
    version="1.0.0",
    nodes=(
        FixtureNode("A1", "app", "A1"), FixtureNode("A2", "app", "A2"), FixtureNode("A3", "app", "A3"),
        FixtureNode("B1", "tool", "B1"), FixtureNode("B2", "tool", "B2"), FixtureNode("B3", "tool", "B3"),
        FixtureNode("C1", "skill", "C1"), FixtureNode("C2", "skill", "C2"), FixtureNode("C3", "skill", "C3"),
    ),
    edges=(
        # Cluster A
        FixtureEdge("A1", "A2", "APP_USES_TOOL"),
        FixtureEdge("A2", "A3", "APP_USES_TOOL"),
        FixtureEdge("A3", "A1", "APP_USES_TOOL"),
        # Cluster B
        FixtureEdge("B1", "B2", "TOOL_DEPENDS_ON_TOOL"),
        FixtureEdge("B2", "B3", "TOOL_DEPENDS_ON_TOOL"),
        FixtureEdge("B3", "B1", "TOOL_DEPENDS_ON_TOOL"),
        # Cluster C
        FixtureEdge("C1", "C2", "APP_NEEDS_SKILL"),
        FixtureEdge("C2", "C3", "APP_NEEDS_SKILL"),
        FixtureEdge("C3", "C1", "APP_NEEDS_SKILL"),
        # Inter-cluster bridge: A1 -> B1
        FixtureEdge("A1", "B1", "APP_USES_TOOL"),
    ),
    expected={
        "node_count": 9,
        "edge_count": 10,
        "expected_communities_count": 3,
        "community_members": [
            ["A1", "A2", "A3"],
            ["B1", "B2", "B3"],
            ["C1", "C2", "C3"],
        ],
    },
)


_FIXTURES: dict[str, GraphFixture] = {
    STARTER_FIVE_V1.dataset_key: STARTER_FIVE_V1,
    DIRECTED_PATH_V1.dataset_key: DIRECTED_PATH_V1,
    MIXED_KIND_V1.dataset_key: MIXED_KIND_V1,
    PARITY_V1.dataset_key: PARITY_V1,
    DEPENDENCY_IMPACT_V1.dataset_key: DEPENDENCY_IMPACT_V1,
    COMMUNITIES_V1.dataset_key: COMMUNITIES_V1,
}


def get_fixture(dataset_key: str) -> GraphFixture | None:
    """Lookup by dataset key. Returns None for unknown — fail-closed."""
    return _FIXTURES.get(dataset_key)
