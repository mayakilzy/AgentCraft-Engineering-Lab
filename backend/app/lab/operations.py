"""Allowlisted operation handlers for E01–E03 (G02/T08).

Each handler receives the caller's `db` Session, the resolved
GuestSession, and the inputs dict from the API. It performs the operation
and returns an `OperationResult` with deterministic outputs. Handlers
never accept raw SQL/Cypher; they call service functions.

E01 — Build Your First Graph
E02 — Shortest Path
E03 — Interactive Graph Explorer (filter + select probe)
"""
from __future__ import annotations

from typing import Any, Dict

from sqlalchemy.orm import Session

from app.config import Settings
from app.lab.registry import OperationResult, register_operation
from app.models.guest_session import GuestSession
from app.services import graph_service
from app.services.graph_algorithms import (
    build_digraph,
    graph_metrics,
    shortest_path,
)


# ---- E01 ----

@register_operation("seed_graph")
def seed_graph_op(
    db: Session,
    settings: Settings,
    session: GuestSession,
    inputs: Dict[str, Any],
) -> OperationResult:
    """Seed a named fixture into the caller's dataset scope.

    Inputs:
      dataset_id : str  (target scope in the session)
      fixture_key: str (e.g., 'starter-five-v1')

    Outputs (on success) include the full node_refs and edges lists so the
    E01 validator can check endpoint integrity (G02 reviewer note #3), not
    just counts.
    """
    dataset_id = inputs.get("dataset_id")
    fixture_key = inputs.get("fixture_key")
    if not dataset_id or not fixture_key:
        return OperationResult(
            operation_key="seed_graph",
            status="failed",
            error_code="bad_input",
            error_message="dataset_id and fixture_key are required",
        )
    try:
        summary = graph_service.load_fixture(db, settings, session, dataset_id, fixture_key)
        # Fetch the seeded node_refs + edges so the validator can check
        # endpoint integrity (G02 reviewer note #3).
        nodes = graph_service.list_nodes(db, session, dataset_id)
        edges = graph_service.list_edges(db, session, dataset_id)
        return OperationResult(
            operation_key="seed_graph",
            status="ok",
            outputs={
                "dataset_id": summary["dataset_id"],
                "node_count": summary["node_count"],
                "edge_count": summary["edge_count"],
                "node_refs": [n.node_ref for n in nodes],
                "edges": [
                    (s_ref, t_ref, e.relation)
                    for (e, s_ref, t_ref) in edges
                ],
            },
        )
    except Exception as exc:  # noqa: BLE001 — surfaces a deterministic failure
        return OperationResult(
            operation_key="seed_graph",
            status="failed",
            error_code=type(exc).__name__,
            error_message=str(exc),
        )


# ---- E02 ----

@register_operation("shortest_path")
def shortest_path_op(
    db: Session,
    settings: Settings,
    session: GuestSession,
    inputs: Dict[str, Any],
) -> OperationResult:
    """Compute the directed shortest path between two node_refs in a
    session-scoped dataset.

    Inputs:
      dataset_id : str
      source     : str (node_ref)
      target     : str (node_ref)
    """
    dataset_id = inputs.get("dataset_id")
    source = inputs.get("source")
    target = inputs.get("target")
    if not (dataset_id and source and target):
        return OperationResult(
            operation_key="shortest_path",
            status="failed",
            error_code="bad_input",
            error_message="dataset_id, source, target are required",
        )
    try:
        g = build_digraph(db, session, dataset_id)
        path = shortest_path(g, source, target)
        return OperationResult(
            operation_key="shortest_path",
            status="ok",
            outputs={
                "path": path,
                "length": (len(path) - 1) if path else None,
                "unreachable": path is None,
            },
        )
    except ValueError as exc:
        return OperationResult(
            operation_key="shortest_path",
            status="failed",
            error_code="node_not_found",
            error_message=str(exc),
        )


# ---- E03 ----

@register_operation("filter_by_kind")
def filter_by_kind_op(
    db: Session,
    settings: Settings,
    session: GuestSession,
    inputs: Dict[str, Any],
) -> OperationResult:
    """Return the subset of node_refs whose kind is in `kinds`.

    Inputs:
      dataset_id : str
      kinds      : list[str]  (e.g., ['skill'])
    """
    dataset_id = inputs.get("dataset_id")
    kinds = inputs.get("kinds") or []
    if not dataset_id:
        return OperationResult(
            operation_key="filter_by_kind",
            status="failed",
            error_code="bad_input",
            error_message="dataset_id is required",
        )
    try:
        g = build_digraph(db, session, dataset_id)
        # Build the visible subset deterministically.
        kinds_set = set(str(k) for k in kinds)
        if kinds_set:
            matched = [n for n in sorted(g.nodes) if g.nodes[n].get("kind") in kinds_set]
        else:
            matched = sorted(g.nodes)
        return OperationResult(
            operation_key="filter_by_kind",
            status="ok",
            outputs={
                "matched_node_refs": matched,
                "match_count": len(matched),
                "total_nodes": g.number_of_nodes(),
            },
        )
    except Exception as exc:  # noqa: BLE001
        return OperationResult(
            operation_key="filter_by_kind",
            status="failed",
            error_code=type(exc).__name__,
            error_message=str(exc),
        )


@register_operation("graph_metrics")
def graph_metrics_op(
    db: Session,
    settings: Settings,
    session: GuestSession,
    inputs: Dict[str, Any],
) -> OperationResult:
    """Return the deterministic metrics for the session-scoped dataset."""
    dataset_id = inputs.get("dataset_id")
    if not dataset_id:
        return OperationResult(
            operation_key="graph_metrics",
            status="failed",
            error_code="bad_input",
            error_message="dataset_id is required",
        )
    try:
        g = build_digraph(db, session, dataset_id)
        m = graph_metrics(g)
        return OperationResult(
            operation_key="graph_metrics",
            status="ok",
            outputs=m,
        )
    except Exception as exc:  # noqa: BLE001
        return OperationResult(
            operation_key="graph_metrics",
            status="failed",
            error_code=type(exc).__name__,
            error_message=str(exc),
        )
