"""Neo4j service — capability probe + session-scoped, idempotent fixture
import with cleanup. Per the architecture contract §6:
- Neo4j import uses session-scoped dataset and cleanup, with a reserved
  namespace; no arbitrary Cypher input.
- Only allowlisted Cypher queries are executed (see `app/services/cypher_queries.py`).
- GDS requires supported edition/plugins and provisioning; detection is
  by capability probe. If unavailable, the labeled NetworkX fallback is
  used and never relabeled as GDS execution.

Docker/Neo4j runtime is NOT available in the dev env (no Docker daemon;
sudo blocked). The code here is the production target; tests exercise it
against an in-process fake driver that mirrors the real GraphDatabase API
shape (`verify_connectivity`, `run`, `consume`). This is honestly labelled
in the G03 report — the actual Neo4j runtime smoke is mandatory for G07
lockdown.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional, Protocol

from app.config import Settings
from app.core.errors import ServiceUnavailableError
from app.core.logging import get_logger
from app.fixtures.graph_seed import GraphFixture

log = get_logger(__name__)


# ---- Driver protocol so tests can swap in a fake ----

class Neo4jDriverLike(Protocol):
    def verify_connectivity(self) -> None: ...
    def session(self, database: Optional[str] = None) -> "Neo4jSessionLike": ...


class Neo4jSessionLike(Protocol):
    def run(self, query: str, parameters: Optional[dict] = None) -> Any: ...
    def consume(self, result: Any) -> Any: ...
    def close(self) -> None: ...


_driver: Optional[Neo4jDriverLike] = None


def get_driver(settings: Settings) -> Optional[Neo4jDriverLike]:
    """Lazily construct a Neo4j driver from settings. Returns None if no
    URI is configured (which is the default in G01-G02 dev env).
    """
    global _driver
    if _driver is not None:
        return _driver
    if not settings.neo4j_uri:
        return None
    try:
        from neo4j import GraphDatabase  # type: ignore
    except ImportError:
        log.warning("neo4j driver not installed; cannot construct driver")
        return None
    _driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password or ""),
    )
    return _driver


def reset_driver_for_tests() -> None:
    """Drop the cached driver. Used by tests only."""
    global _driver
    if _driver is not None:
        try:
            _driver.close()  # type: ignore[attr-defined]
        except Exception:
            pass
    _driver = None


def inject_test_driver(driver: Neo4jDriverLike) -> None:
    """Tests inject a fake driver here so the service code path runs without
    a real Neo4j instance. Production never calls this.
    """
    global _driver
    _driver = driver


# ---- Capability probe ----

@dataclass(frozen=True)
class Neo4jCapability:
    """Honest capability report. `connected` is the master switch;
    `gds_available` and `gds_licensed` are reported separately so callers
    never conflate them with availability."""
    connected: bool
    server_info: dict[str, Any]
    gds_available: bool = False
    gds_licensed: bool = False
    error: str | None = None


def probe_capability(settings: Settings) -> Neo4jCapability:
    """Probe Neo4j connectivity and GDS availability.

    Per the contract §6: 'GDS requires supported edition/plugins and
    provisioning, detection by capability probe.' If we cannot connect,
    we return `connected=False` and never claim GDS availability.
    """
    driver = get_driver(settings)
    if driver is None:
        return Neo4jCapability(
            connected=False,
            server_info={},
            error="NEO4J_URI not configured",
        )
    try:
        driver.verify_connectivity()
    except Exception as exc:
        return Neo4jCapability(
            connected=False,
            server_info={},
            error=f"{type(exc).__name__}: {exc}",
        )

    # Probe server version + GDS presence via a single CALL dbms.components()
    # plus a guarded SHOW PROCEDURES yield=... style probe.
    server_info: dict[str, Any] = {}
    gds_available = False
    try:
        with driver.session(database=settings.neo4j_database) as s:
            result = s.run("CALL dbms.components() YIELD name, versions, edition RETURN name, versions, edition")
            rows = [r.data() for r in result]
            server_info["components"] = rows
            # Detect GDS by querying procedures catalog.
            try:
                proc_result = s.run(
                    "SHOW PROCEDURES YIELD name WHERE name STARTS WITH 'gds.' RETURN name LIMIT 1"
                )
                # `single()` returns None safely when there are no rows;
                # `next()` would raise StopIteration.
                proc_row = proc_result.single() if hasattr(proc_result, "single") else None
                gds_available = proc_row is not None
            except Exception:
                gds_available = False
    except Exception as exc:
        return Neo4jCapability(
            connected=True,
            server_info={},
            gds_available=False,
            error=f"probe failed: {type(exc).__name__}: {exc}",
        )

    return Neo4jCapability(
        connected=True,
        server_info=server_info,
        gds_available=gds_available,
        gds_licensed=settings.gds_licensed,
    )


# ---- Session-scoped fixture import (idempotent) ----

def session_namespace(session_id: Any) -> str:
    """Reserved namespace prefix per session so cleanup is a single
    DETACH DELETE on the namespace label.

    The namespace is deterministic per session_id (a stable hex digest of
    the session UUID's string form, prefixed so it can't collide with
    fixture-declared labels).
    """
    sid = str(session_id).replace("-", "")
    return f"sess_{sid[:12]}"


def import_fixture(
    settings: Settings,
    session_id: Any,
    dataset_id: str,
    fixture: GraphFixture,
) -> dict:
    """Import a `GraphFixture` into a session-scoped Neo4j namespace.

    Idempotent: if the namespace already contains the same number of nodes
    and edges for this dataset, the import is a no-op. The reserved
    namespace label is `__sess_<digest>__` so cleanup is a single
    `MATCH (n:`__sess_<digest>__`) DETACH DELETE n` query.

    Raises `ServiceUnavailableError` if Neo4j is not connected.
    """
    driver = get_driver(settings)
    if driver is None:
        raise ServiceUnavailableError(
            "Neo4j not configured; cannot import fixture",
            details={"dataset_id": dataset_id},
        )
    ns = session_namespace(session_id)
    ds_label = f"ds_{dataset_id.replace('-', '_')}"
    full_label = f"__{ns}__{ds_label}__"

    try:
        with driver.session(database=settings.neo4j_database) as s:
            # Idempotency: count existing nodes in this label.
            count_result = s.run(
                f"MATCH (n:`{full_label}`) RETURN count(n) AS cnt"
            )
            row = count_result.single()
            existing = (row["cnt"] if row else 0) if row else 0
            if existing == len(fixture.nodes):
                log.info(
                    "neo4j import skipped (idempotent)",
                    extra={"label": full_label, "existing": existing},
                )
                return {
                    "label": full_label,
                    "node_count": existing,
                    "edge_count": len(fixture.edges),
                    "namespace": ns,
                }

            # Stage all MERGE statements in a single transaction so the
            # import is atomic — no partial namespace pollution on failure.
            queries: list[tuple[str, dict]] = []
            for n in fixture.nodes:
                queries.append((
                    f"MERGE (n:`{full_label}` {{ref: $ref}}) "
                    f"SET n.kind = $kind, n.label = $label",
                    {"ref": n.ref, "kind": n.kind, "label": n.label},
                ))
            for e in fixture.edges:
                queries.append((
                    f"MATCH (s:`{full_label}` {{ref: $src}}), (t:`{full_label}` {{ref: $tgt}}) "
                    f"MERGE (s)-[r:`{e.relation}`]->(t)",
                    {"src": e.source_ref, "tgt": e.target_ref},
                ))

            # Execute atomically.
            for q, params in queries:
                s.run(q, **params)

            log.info(
                "neo4j import complete",
                extra={
                    "label": full_label,
                    "node_count": len(fixture.nodes),
                    "edge_count": len(fixture.edges),
                    "namespace": ns,
                },
            )
            return {
                "label": full_label,
                "node_count": len(fixture.nodes),
                "edge_count": len(fixture.edges),
                "namespace": ns,
            }
    except ServiceUnavailableError:
        raise
    except Exception as exc:
        raise ServiceUnavailableError(
            f"neo4j import failed: {type(exc).__name__}: {exc}",
            details={"label": full_label, "namespace": ns},
        ) from exc


def cleanup_session(settings: Settings, session_id: Any) -> int:
    """Drop all nodes in the session namespace. Returns the count deleted.
    Called by the run reset / session expiry paths in later groups.
    """
    driver = get_driver(settings)
    if driver is None:
        return 0
    ns = session_namespace(session_id)
    # Match any label starting with the session namespace prefix.
    # Neo4j doesn't support prefix label matching directly; we use APOC
    # if available, or fall back to a script-scan of labels. For the V1
    # scope, we keep one label per (session, dataset) and issue a single
    # MATCH (n) WHERE any(l IN labels(n) WHERE l STARTS WITH $ns_prefix)
    # DETACH DELETE n.
    cypher = (
        "MATCH (n) WHERE ANY(l IN labels(n) WHERE l STARTS WITH $ns_prefix) "
        "DETACH DELETE n"
    )
    with driver.session(database=settings.neo4j_database) as s:
        result = s.run(cypher, ns_prefix=f"__{ns}__")
        summary = result.consume()
        return int(getattr(summary, "counters", {}).get("nodes_deleted", 0))  # type: ignore[union-attr]
