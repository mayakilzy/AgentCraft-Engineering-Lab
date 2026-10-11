"""Relational vs graph parity (T10).

Per the contract §6: 'SQL and Cypher parity use exactly same synthetic
snapshot; compare canonical sets, not ordering. ... latency comparisons
label cold/warm/sample/iterations.'

This service runs an allowlisted SQL query and an allowlisted Cypher
query against the same session-scoped snapshot and compares the canonical
result sets (order-independent). Timing is reported with explicit
context: cold vs warm, sample size, iteration count.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.errors import ServiceUnavailableError
from app.models.guest_session import GuestSession
from app.services import cypher_queries, graph_service, neo4j_service


@dataclass
class ParityResult:
    """Outcome of a parity check. The verdict is binary: equal/not-equal.
    Timing is reported with explicit context per the contract."""
    query_key: str
    sql_rows: list[dict] = field(default_factory=list)
    cypher_rows: list[dict] = field(default_factory=list)
    sql_latency_ms: float | None = None
    cypher_latency_ms: float | None = None
    equal: bool = False
    timing_context: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


# Allowlisted SQL counterparts to the Cypher queries above.
# Each returns rows as a list of dicts with the SAME column names so the
# canonical-set comparison is meaningful. We return node_ref (the stable
# external id) rather than label, matching the Cypher `s.ref` shape.
ALLOWLISTED_SQL: dict[str, str] = {
    "app_uses_tool_direct": (
        "SELECT n.node_ref AS app, m.node_ref AS tool "
        "FROM graph_edges e "
        "JOIN graph_nodes n ON e.source_id = n.id "
        "JOIN graph_nodes m ON e.target_id = m.id "
        "WHERE e.session_id = :session_id "
        "  AND e.dataset_id = :dataset_id "
        "  AND e.relation = 'APP_USES_TOOL' "
        "  AND n.kind = 'app' AND m.kind = 'tool' "
        "ORDER BY app, tool"
    ),
    "tool_depends_on_tool": (
        "SELECT n.node_ref AS source, m.node_ref AS target "
        "FROM graph_edges e "
        "JOIN graph_nodes n ON e.source_id = n.id "
        "JOIN graph_nodes m ON e.target_id = m.id "
        "WHERE e.session_id = :session_id "
        "  AND e.dataset_id = :dataset_id "
        "  AND e.relation = 'TOOL_DEPENDS_ON_TOOL' "
        "  AND n.kind = 'tool' AND m.kind = 'tool' "
        "ORDER BY source, target"
    ),
    "kind_counts": (
        "SELECT n.kind AS kind, COUNT(*) AS cnt "
        "FROM graph_nodes n "
        "WHERE n.session_id = :session_id AND n.dataset_id = :dataset_id "
        "GROUP BY n.kind ORDER BY n.kind"
    ),
}


def get_sql(query_key: str) -> str:
    if query_key not in ALLOWLISTED_SQL:
        from app.core.errors import InvalidStateError
        raise InvalidStateError(
            f"unknown sql query_key: {query_key}",
            details={"requested": query_key},
        )
    return ALLOWLISTED_SQL[query_key]


def _to_canonical(rows: Iterable[dict]) -> frozenset[tuple]:
    """Convert a list of dict rows to a frozenset of sorted-tuple rows
    (order-independent comparison per the contract)."""
    return frozenset(tuple(sorted(d.items())) for d in rows)


def run_parity(
    db: Session,
    settings: Settings,
    session: GuestSession,
    dataset_id: str,
    query_key: str,
    *,
    iterations: int = 1,
    warmup: int = 0,
) -> ParityResult:
    """Run an allowlisted SQL + Cypher query pair and compare canonical
    result sets. Returns timing in milliseconds with explicit context:
    - `iterations`: how many times each query was executed.
    - `warmup`: how many warm-up runs were discarded before timing.
    - `cold`: True if iterations == 1 and warmup == 0 (first-touch).
    """
    if query_key not in ALLOWLISTED_SQL or query_key not in cypher_queries.ALLOWLISTED_CYPHER:
        return ParityResult(
            query_key=query_key,
            error=f"query_key not allowlisted on both sides: {query_key}",
        )

    # ---- SQL side ----
    sql = text(ALLOWLISTED_SQL[query_key])
    sql_rows: list[dict] = []
    sql_times: list[float] = []
    # SQLite's pysqlite driver doesn't accept UUID objects directly in
    # bind parameters; convert to string. PostgreSQL accepts UUID natively
    # and also accepts its string form, so this is dialect-safe.
    sql_params = {"session_id": str(session.id), "dataset_id": dataset_id}
    # Warmup
    for _ in range(warmup):
        db.execute(sql, sql_params).mappings().all()
    for _ in range(iterations):
        t0 = time.perf_counter()
        result = db.execute(sql, sql_params).mappings().all()
        t1 = time.perf_counter()
        sql_times.append((t1 - t0) * 1000)
        sql_rows = [dict(r) for r in result]

    sql_latency = sum(sql_times) / max(1, len(sql_times)) if sql_times else 0.0

    # ---- Cypher side ----
    driver = neo4j_service.get_driver(settings)
    if driver is None:
        # Honest BLOCKED: Neo4j not configured in this env.
        return ParityResult(
            query_key=query_key,
            sql_rows=sql_rows,
            sql_latency_ms=sql_latency,
            cypher_latency_ms=None,
            equal=False,
            error="NEO4J_URI not configured (BLOCKED — see G03 report)",
            timing_context={
                "iterations": iterations,
                "warmup": warmup,
                "cold": iterations == 1 and warmup == 0,
                "sql_only": True,
            },
        )

    # Use the SAME label function that `import_fixture` uses so the
    # parity query reads the namespace we actually imported into.
    # Per G03-C1 reviewer note #2: shared label helper, no duplication.
    full_label = neo4j_service.dataset_label(session.id, dataset_id)
    cypher = cypher_queries.get_query(query_key, full_label)
    params = {"app_ref": ""}  # placeholder; queries without params ignore it
    cypher_rows: list[dict] = []
    cypher_times: list[float] = []
    try:
        with driver.session(database=settings.neo4j_database) as s:
            for _ in range(warmup):
                list(s.run(cypher, **params))
            for _ in range(iterations):
                t0 = time.perf_counter()
                result = s.run(cypher, **params)
                rows = [r.data() for r in result] if hasattr(result, "__iter__") else []
                t1 = time.perf_counter()
                cypher_times.append((t1 - t0) * 1000)
                cypher_rows = rows
    except Exception as exc:
        return ParityResult(
            query_key=query_key,
            sql_rows=sql_rows,
            sql_latency_ms=sql_latency,
            cypher_latency_ms=None,
            equal=False,
            error=f"cypher failed: {type(exc).__name__}: {exc}",
            timing_context={
                "iterations": iterations,
                "warmup": warmup,
                "cold": iterations == 1 and warmup == 0,
            },
        )

    cypher_latency = sum(cypher_times) / max(1, len(cypher_times)) if cypher_times else 0.0

    equal = _to_canonical(sql_rows) == _to_canonical(cypher_rows)
    return ParityResult(
        query_key=query_key,
        sql_rows=sql_rows,
        cypher_rows=cypher_rows,
        sql_latency_ms=sql_latency,
        cypher_latency_ms=cypher_latency,
        equal=equal,
        timing_context={
            "iterations": iterations,
            "warmup": warmup,
            "cold": iterations == 1 and warmup == 0,
            "sample_size": len(sql_rows),
        },
    )
