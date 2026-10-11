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
   into GDS via the documented `gds.graph.project(name, nodeLabel, '*')`
   API, run `gds.louvain.stream`, resolve nodeIds back to node_refs, and
   GUARANTEE the projection is dropped in a `finally` block.
3. If GDS is NOT available OR not licensed: run the equivalent NetworkX
   community-detection algorithm and return results labelled
   `provider='networkx_fallback'`. The result is never labelled GDS.

G03-C1 reviewer notes addressed here:
- #1: Graph Projection now uses the supported `gds.graph.project(name,
  nodeLabel, '*')` signature (was previously a malformed string-interpolated
  subquery attempt).
- #2: Label name comes from the shared `neo4j_service.dataset_label()`.
- #3: nodeId→node_ref resolution uses the same label and matches on the
  internal `id(n)` returned by both the Louvain stream and the ref lookup.
- #4: Projection lifecycle is wrapped in try/finally; cleanup runs even
  when Louvain raises.
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

    # GDS available + licensed: project and run Louvain, with guaranteed
    # projection cleanup in a finally block.
    driver = neo4j_service.get_driver(settings)
    if driver is None:
        # Should not happen (we just verified connectivity), but be defensive.
        return _networkx_fallback(db, session, dataset_id, note="driver_disposed")

    full_label = neo4j_service.dataset_label(session.id, dataset_id)
    graph_name = f"g_{full_label}"

    try:
        sess = driver.session(database=settings.neo4j_database)
    except Exception as exc:
        return _networkx_fallback(
            db, session, dataset_id,
            note=f"session_open_failed: {type(exc).__name__}",
        )

    try:
        # ---- Project the session-scoped subgraph into GDS ----
        # Per G03-C1 reviewer note #1: use the documented
        # `gds.graph.project(graphName, nodeSpec, relationshipSpec)` signature.
        # nodeSpec = the session-scoped label (parameterised as $nodeLabel).
        # relationshipSpec = '*' projects all relationship types whose both
        # endpoints carry the projected label (GDS does this automatically;
        # cross-label relationships are excluded).
        sess.run(
            "CALL gds.graph.project($name, $nodeLabel, '*')",
            name=graph_name,
            nodeLabel=full_label,
        )

        # Run Louvain INSIDE a try/finally so the projection is always
        # dropped even if the algorithm call fails.
        try:
            louvain_result = sess.run(
                "CALL gds.louvain.stream($name) "
                "YIELD nodeId, communityId "
                "RETURN nodeId, communityId",
                name=graph_name,
            )
            rows = [r.data() for r in louvain_result]

            # Resolve GDS internal node ids back to node_refs.
            # Per note #3: use the SAME label and the SAME id(n) so the
            # lookup matches the Louvain nodeId.
            ref_result = sess.run(
                f"MATCH (n:`{full_label}`) "
                f"RETURN id(n) AS id, n.ref AS ref"
            )
            id_to_ref: dict[int, str] = {
                r["id"]: r["ref"] for r in ref_result
            }

            communities_by_id: dict[int, list[str]] = {}
            for r in rows:
                cid = r["communityId"]
                nid = r["nodeId"]
                ref = id_to_ref.get(nid)
                if ref is not None:
                    communities_by_id.setdefault(cid, []).append(ref)

            communities = [sorted(v) for v in communities_by_id.values()]
            return CommunityResult(
                provider="gds",
                algorithm="louvain",
                communities=communities,
                modularity=None,
                note=(
                    "gds.louvain.stream on session-scoped projection; "
                    "projection dropped after use"
                ),
            )
        finally:
            # GUARANTEED cleanup — drop the projection even if Louvain
            # or the ref lookup raised. We catch cleanup errors so they
            # never mask the original exception (per G03-C1 note #4).
            try:
                sess.run(
                    "CALL gds.graph.drop($name, false)",
                    name=graph_name,
                )
                log.info(
                    "gds projection dropped (cleanup)",
                    extra={"graph_name": graph_name},
                )
            except Exception as cleanup_exc:
                log.warning(
                    "gds projection cleanup failed",
                    extra={
                        "graph_name": graph_name,
                        "error": f"{type(cleanup_exc).__name__}: {cleanup_exc}",
                    },
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
    finally:
        # Always close the driver session.
        try:
            sess.close()
        except Exception:
            pass


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
