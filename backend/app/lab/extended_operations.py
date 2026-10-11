"""Allowlisted operation handlers for E04–E10 (T19).

Each handler receives the caller's `db` Session, the resolved
GuestSession, the inputs dict from the API, and an optional `run_id`
parameter (the API populates it from the persisted run record so spans
can be correlated with the run).

Handlers never accept raw SQL/Cypher; they call service functions.

E04 — SQL vs Cypher (parity)
E05 — Critical Dependencies (directed reachability)
E06 — Discover Communities (GDS or NetworkX fallback)
E07 — Trace One Request (already in observability_operations)
E08 — Build Monitoring Dashboard (metrics summary)
E09 — Diagnose a Hidden Failure (already in observability_operations)
E10 — Integrated Challenge (graph + telemetry combined)
"""
from __future__ import annotations

from typing import Any, Dict

from sqlalchemy.orm import Session

from app.config import Settings
from app.lab.registry import OperationResult, register_operation
from app.models.guest_session import GuestSession


# ---- E04: SQL vs Cypher ----

@register_operation("parity_run")
def parity_run_op(
    db: Session,
    settings: Settings,
    session: GuestSession,
    inputs: Dict[str, Any],
) -> OperationResult:
    """Run an allowlisted SQL + Cypher query pair against the same
    session-scoped snapshot and compare canonical result sets.

    Inputs:
      dataset_id : str
      query_key  : str (must be allowlisted on both sides)
      iterations : int (1..10, default 1)
      warmup     : int (0..5, default 0)
    """
    from app.services import parity_service

    dataset_id = inputs.get("dataset_id")
    query_key = inputs.get("query_key")
    if not dataset_id or not query_key:
        return OperationResult(
            operation_key="parity_run",
            status="failed",
            error_code="bad_input",
            error_message="dataset_id and query_key are required",
        )
    try:
        iterations = int(inputs.get("iterations", 1))
        warmup = int(inputs.get("warmup", 0))
    except (TypeError, ValueError):
        return OperationResult(
            operation_key="parity_run",
            status="failed",
            error_code="bad_input",
            error_message="iterations and warmup must be integers",
        )

    try:
        result = parity_service.run_parity(
            db, settings, session, dataset_id, query_key,
            iterations=iterations, warmup=warmup,
        )
        # When Neo4j is not configured, the result is honest BLOCKED.
        if result.error and "NEO4J_URI not configured" in result.error:
            return OperationResult(
                operation_key="parity_run",
                status="blocked",
                error_code="neo4j_not_configured",
                error_message=result.error,
                outputs={
                    "query_key": result.query_key,
                    "sql_rows": result.sql_rows,
                    "sql_latency_ms": result.sql_latency_ms,
                    "cypher_latency_ms": result.cypher_latency_ms,
                    "equal": result.equal,
                    "timing_context": result.timing_context,
                    "error": result.error,
                },
            )
        return OperationResult(
            operation_key="parity_run",
            status="ok" if result.equal else "failed",
            error_code=None if result.equal else "parity_mismatch",
            error_message=None if result.equal else result.error,
            outputs={
                "query_key": result.query_key,
                "sql_rows": result.sql_rows,
                "cypher_rows": result.cypher_rows,
                "sql_latency_ms": result.sql_latency_ms,
                "cypher_latency_ms": result.cypher_latency_ms,
                "equal": result.equal,
                "timing_context": result.timing_context,
                "error": result.error,
            },
        )
    except Exception as exc:  # noqa: BLE001
        return OperationResult(
            operation_key="parity_run",
            status="failed",
            error_code=type(exc).__name__,
            error_message=str(exc),
        )


# ---- E05: Critical Dependencies ----

@register_operation("critical_dep_analysis")
def critical_dep_analysis_op(
    db: Session,
    settings: Settings,
    session: GuestSession,
    inputs: Dict[str, Any],
) -> OperationResult:
    """Run the directed reachability impact analysis for a target node.

    Inputs:
      dataset_id : str
      target     : str (node_ref)
    """
    from app.services.graph_algorithms import (
        build_digraph,
        critical_dependencies,
    )

    dataset_id = inputs.get("dataset_id")
    target = inputs.get("target")
    if not dataset_id or not target:
        return OperationResult(
            operation_key="critical_dep_analysis",
            status="failed",
            error_code="bad_input",
            error_message="dataset_id and target are required",
        )

    try:
        g = build_digraph(db, session, dataset_id)
        cd = critical_dependencies(g, target)
        return OperationResult(
            operation_key="critical_dep_analysis",
            status="ok",
            outputs=cd,
        )
    except ValueError as exc:
        return OperationResult(
            operation_key="critical_dep_analysis",
            status="failed",
            error_code="node_not_found",
            error_message=str(exc),
        )
    except Exception as exc:  # noqa: BLE001
        return OperationResult(
            operation_key="critical_dep_analysis",
            status="failed",
            error_code=type(exc).__name__,
            error_message=str(exc),
        )


# ---- E06: Discover Communities ----

@register_operation("communities_detect")
def communities_detect_op(
    db: Session,
    settings: Settings,
    session: GuestSession,
    inputs: Dict[str, Any],
) -> OperationResult:
    """Run community detection (GDS Louvain if available + licensed, else
    the labelled NetworkX fallback). Provenance is mandatory.

    Inputs:
      dataset_id : str
    """
    from app.services import gds_service

    dataset_id = inputs.get("dataset_id")
    if not dataset_id:
        return OperationResult(
            operation_key="communities_detect",
            status="failed",
            error_code="bad_input",
            error_message="dataset_id is required",
        )

    try:
        result = gds_service.detect_communities(db, settings, session, dataset_id)
        return OperationResult(
            operation_key="communities_detect",
            status="ok",
            outputs={
                "provider": result.provider,
                "algorithm": result.algorithm,
                "communities": result.communities,
                "modularity": result.modularity,
                "note": result.note,
                "community_count": len(result.communities),
            },
        )
    except Exception as exc:  # noqa: BLE001
        return OperationResult(
            operation_key="communities_detect",
            status="failed",
            error_code=type(exc).__name__,
            error_message=str(exc),
        )


# ---- E08: Build Monitoring Dashboard ----

@register_operation("metrics_demo")
def metrics_demo_op(
    db: Session,
    settings: Settings,
    session: GuestSession,
    inputs: Dict[str, Any],
) -> OperationResult:
    """Return the bounded metrics summary so the user can observe request
    rate, error rate and latency over a controlled workload.

    The operation reads the in-process metrics registry (the same one
    Prometheus scrapes via `/metrics`). The values are real — no fake
    numbers.

    Inputs: (none required; `dataset_id` is ignored)
    """
    try:
        from app.api.v1.observability import get_metrics_summary
        from app.core.metrics import render_metrics
        from prometheus_client.parser import text_string_to_metric_families

        summary = get_metrics_summary(settings)
        # Re-derive the same fields the validator consumes.
        raw = render_metrics().decode("utf-8")
        families = list(text_string_to_metric_families(raw))

        http_total = 0.0
        lab_total = 0.0
        lab_by_status: dict[str, float] = {}
        for fam in families:
            if fam.name in ("agentcraft_http_requests_total", "agentcraft_http_requests"):
                for sample in fam.samples:
                    if sample.name.endswith("_total"):
                        http_total += sample.value
            elif fam.name in ("agentcraft_lab_runs_total", "agentcraft_lab_runs"):
                for sample in fam.samples:
                    if sample.name.endswith("_total"):
                        lab_total += sample.value
                        status = sample.labels.get("status", "unknown")
                        lab_by_status[status] = lab_by_status.get(status, 0.0) + sample.value

        return OperationResult(
            operation_key="metrics_demo",
            status="ok",
            outputs={
                "http_requests_total": http_total,
                "http_request_duration_seconds_p50": summary.http_request_duration_seconds_p50,
                "http_request_duration_seconds_p95": summary.http_request_duration_seconds_p95,
                "lab_runs_total": lab_total,
                "lab_runs_by_status": lab_by_status,
                "prometheus_url": summary.prometheus_url,
                "grafana_url": summary.grafana_url,
                "tempo_url": summary.tempo_url,
                "note": summary.note,
            },
        )
    except Exception as exc:  # noqa: BLE001
        return OperationResult(
            operation_key="metrics_demo",
            status="failed",
            error_code=type(exc).__name__,
            error_message=str(exc),
        )
