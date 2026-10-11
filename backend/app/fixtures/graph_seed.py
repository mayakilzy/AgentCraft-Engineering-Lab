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


_FIXTURES: dict[str, GraphFixture] = {
    STARTER_FIVE_V1.dataset_key: STARTER_FIVE_V1,
    DIRECTED_PATH_V1.dataset_key: DIRECTED_PATH_V1,
    MIXED_KIND_V1.dataset_key: MIXED_KIND_V1,
}


def get_fixture(dataset_key: str) -> GraphFixture | None:
    """Lookup by dataset key. Returns None for unknown — fail-closed."""
    return _FIXTURES.get(dataset_key)
