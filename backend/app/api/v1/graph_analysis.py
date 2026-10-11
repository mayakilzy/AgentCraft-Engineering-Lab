"""Graph analysis endpoints — expose NetworkX results via the scoped API.

Per the architecture contract §6: shortest path, centralities, component
analysis. Each endpoint is session-scoped and takes the dataset_id path
parameter.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import DbDep, GuestSessionDep
from app.services.graph_algorithms import (
    build_digraph,
    components,
    degree_centrality,
    graph_metrics,
    in_out_degrees,
    reachable_ancestors,
    reachable_descendants,
    shortest_path,
)
from app.core.errors import AppError

router = APIRouter(prefix="/graph", tags=["graph-analysis"])


class ShortestPathRequest(BaseModel):
    source: str = Field(..., min_length=1, max_length=128)
    target: str = Field(..., min_length=1, max_length=128)


class ShortestPathResponse(BaseModel):
    dataset_id: str
    source: str
    target: str
    path: list[str] | None
    length: int | None  # number of edges; None if no path


class CentralityResponse(BaseModel):
    dataset_id: str
    degree_centrality: dict[str, float]
    in_out_degrees: dict[str, list[int]]


class ReachabilityResponse(BaseModel):
    dataset_id: str
    node: str
    descendants: list[str]
    ancestors: list[str]


class ComponentsResponse(BaseModel):
    dataset_id: str
    weakly_connected: list[list[str]]
    strongly_connected: list[list[str]]


class MetricsResponse(BaseModel):
    dataset_id: str
    node_count: int
    edge_count: int
    is_directed: bool
    is_dag: bool
    weakly_connected_components: int
    strongly_connected_components: int
    density: float
    selfloops: list[str]


@router.post("/{dataset_id}/shortest-path", response_model=ShortestPathResponse)
def post_shortest_path(
    dataset_id: str,
    payload: ShortestPathRequest,
    db: DbDep,
    session: GuestSessionDep,
) -> ShortestPathResponse:
    g = build_digraph(db, session, dataset_id)
    try:
        path = shortest_path(g, payload.source, payload.target)
    except ValueError as exc:
        raise AppError(str(exc), status_code=400, code="bad_request") from exc
    return ShortestPathResponse(
        dataset_id=dataset_id,
        source=payload.source,
        target=payload.target,
        path=path,
        length=(len(path) - 1) if path is not None else None,
    )


@router.get("/{dataset_id}/centrality", response_model=CentralityResponse)
def get_centrality(
    dataset_id: str,
    db: DbDep,
    session: GuestSessionDep,
) -> CentralityResponse:
    g = build_digraph(db, session, dataset_id)
    dc = degree_centrality(g)
    deg = in_out_degrees(g)
    # Convert tuples to lists for JSON.
    deg_list = {n: [i, o] for n, (i, o) in deg.items()}
    return CentralityResponse(
        dataset_id=dataset_id,
        degree_centrality=dc,
        in_out_degrees=deg_list,
    )


@router.get(
    "/{dataset_id}/reachability/{node_ref}",
    response_model=ReachabilityResponse,
)
def get_reachability(
    dataset_id: str,
    node_ref: str,
    db: DbDep,
    session: GuestSessionDep,
) -> ReachabilityResponse:
    g = build_digraph(db, session, dataset_id)
    try:
        desc = reachable_descendants(g, node_ref)
        anc = reachable_ancestors(g, node_ref)
    except ValueError as exc:
        raise AppError(str(exc), status_code=404, code="not_found") from exc
    return ReachabilityResponse(
        dataset_id=dataset_id,
        node=node_ref,
        descendants=desc,
        ancestors=anc,
    )


@router.get("/{dataset_id}/components", response_model=ComponentsResponse)
def get_components(
    dataset_id: str,
    db: DbDep,
    session: GuestSessionDep,
) -> ComponentsResponse:
    g = build_digraph(db, session, dataset_id)
    c = components(g)
    return ComponentsResponse(
        dataset_id=dataset_id,
        weakly_connected=c["weakly_connected"],
        strongly_connected=c["strongly_connected"],
    )


@router.get("/{dataset_id}/metrics", response_model=MetricsResponse)
def get_metrics(
    dataset_id: str,
    db: DbDep,
    session: GuestSessionDep,
) -> MetricsResponse:
    g = build_digraph(db, session, dataset_id)
    m = graph_metrics(g)
    return MetricsResponse(dataset_id=dataset_id, **m)
