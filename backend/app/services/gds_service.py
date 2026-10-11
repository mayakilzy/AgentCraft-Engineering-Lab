"""GDS conditional — community detection.

Per the architecture contract §6 + the acceptance gate A05: 'GDS requires
supported edition/plugins and provisioning, detection by capability
probe; fallback separate NetworkX computation labelled. ... if GDS
licensing unavailable, it may be explicitly marked NOT_AVAILABLE with
NetworkX lesson alternative; do not certify native GDS behavior.'

This module exposes `detect_communities(settings, session, dataset_id)`
which:
1. Probes Neo4j connectivity + GDS availability.
2. If GDS is available AND licensed: project the session-scoped graph
   into GDS and run `gds.louvain.stream` (or the compatible alternative).
3. If GDS is NOT available OR not licensed: run the equivalent NetworkX
   community-detection algorithm and return results labelled
   `provider='networkx_fallback'`. The result is never labelled GDS.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List

from sqlalchemy.orm import Session

from app.config import Settings
from app.core.errors import ServiceUnavailableError
from app.core.logging import get_logger
from app.models.guest_session import GuestSession
from app.services import graph_algorithms, neo4j_service

log = get_logger(__name__)


@dataclass(frozen=True)
class CommunityResult:
    """Outcome of community detection. Provenance is mandatory per A05."""
    provider: str  # "gds" | "networkx_fallback" | "blocked"
    algorithm: str  # e.g. "louvain", "greedy_modularity"
    communities: List[List[str]]  # list of node_refs per community
    modularity: float | None = None
    note: str = ""


def detect_communities(
    db: Session,
    settings: Settings,
    session: GuestSession,
    dataset_id: str,
) -> CommunityResult:
    """Detect communities in the session-scoped graph.

    Provenance is reported on every result; we never label a NetworkX
    fallback as GDS execution.
    """
    capability = neo4j_service.probe_capability(settings)

    if not capability.connected:
        # Neo4j not available — labelled fallback, honestly.
        return _networkx_fallback(db, session, dataset_id, note="neo4j_not_connected")

    if not capability.gds_available or not settings.gds_licensed:
        # Neo4j connected but GDS missing/unlicensed — labelled fallback.
        return _networkx_fallback(
            db, session, dataset_id,
            note=(
                f"gds_available={capability.gds_available}; "
                f"gds_licensed={settings.gds_licensed}"
            ),
        )

    # GDS available + licensed: project and run Louvain.
    driver = neo4j_service.get_driver(settings)
    if driver is None:
        # Should not happen (we just verified connectivity), but be defensive.
        return _networkx_fallback(db, session, dataset_id, note="driver_disposed")

    label = neo4j_service.session_namespace(session.id) + "_" + dataset_id.replace("-", "_")
    try:
        with driver.session(database=settings.neo4j_database) as s:
            # Project the session-scoped subgraph into a GDS graph.
            graph_name = f"g_{label}"
            s.run(
                "CALL gds.graph.project("
                "$name, "
                "MATCH (n:`__{label}__`) RETURN id(n) AS id, n.kind AS kind, "
                "MATCH (n:`__{label}__`)-[r]->(m:`__{label}__`) "
                "RETURN id(n) AS source, id(m) AS target, type(r) AS type".format(label=label),
                name=graph_name,
            )
            # Stream Louvain communities.
            result = s.run(
                "CALL gds.louvain.stream($name) "
                "YIELD nodeId, communityId "
                "RETURN nodeId, communityId",
                name=graph_name,
            )
            rows = [r.data() for r in result]
            # Resolve GDS internal node ids back to node_refs.
            ref_rows = s.run(
                "MATCH (n:`__{label}__`) RETURN id(n) AS id, n.ref AS ref".format(label=label)
            )
            id_to_ref = {r["id"]: r["ref"] for r in ref_rows}
            communities_by_id: dict[int, list[str]] = {}
            for r in rows:
                cid = r["communityId"]
                nid = r["nodeId"]
                ref = id_to_ref.get(nid)
                if ref is not None:
                    communities_by_id.setdefault(cid, []).append(ref)
            # Drop the projection.
            s.run("CALL gds.graph.drop($name)", name=graph_name)
            communities = [sorted(v) for v in communities_by_id.values()]
            return CommunityResult(
                provider="gds",
                algorithm="louvain",
                communities=communities,
                modularity=None,
                note="gds.louvain.stream; projection dropped after use",
            )
    except Exception as exc:
        log.warning(
            "gds community detection failed; falling back to NetworkX",
            extra={"error": f"{type(exc).__name__}: {exc}"},
        )
        return _networkx_fallback(
            db, session, dataset_id,
            note=f"gds_call_failed: {type(exc).__name__}",
        )


def _networkx_fallback(
    db: Session,
    session: GuestSession,
    dataset_id: str,
    *,
    note: str,
) -> CommunityResult:
    """Run greedy_modularity_communities on the directed graph and label
    the result as a NetworkX fallback — never as GDS."""
    g = graph_algorithms.build_digraph(db, session, dataset_id)
    # Use undirected version for community detection (NetworkX idiom).
    gu = g.to_undirected()
    try:
        from networkx.algorithms.community import greedy_modularity_communities
        communities = [sorted(c) for c in greedy_modularity_communities(gu)]
    except Exception:
        # Last-resort: connected components as trivial communities.
        communities = [sorted(c) for c in nx_components(gu)]
    return CommunityResult(
        provider="networkx_fallback",
        algorithm="greedy_modularity",
        communities=communities,
        modularity=None,
        note=(
            "NetworkX fallback (NOT GDS). "
            "Use this for learning the algorithm shape; "
            "do not certify native GDS behavior. "
            f"reason: {note}"
        ),
    )


def nx_components(g_undirected) -> list:
    """Trivial connected-components fallback."""
    import networkx as nx
    return list(nx.connected_components(g_undirected))
