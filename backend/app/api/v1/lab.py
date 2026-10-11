"""Neo4j + GDS + parity + critical-dependencies endpoints.

All session-scoped; all return honest provenance and BLOCKED labels when
Neo4j/GDS is unavailable (per the architecture contract §6 + acceptance
gate A05). No mock PASS.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import DbDep, GuestSessionDep, SettingsDep
from app.services import gds_service, neo4j_service, parity_service
from app.services.graph_algorithms import critical_dependencies, build_digraph
from app.core.errors import AppError

router = APIRouter(prefix="/lab", tags=["lab"])


class CapabilityResponse(BaseModel):
    connected: bool
    server_info: dict
    gds_available: bool
    gds_licensed: bool
    error: str | None


@router.get("/neo4j/capability", response_model=CapabilityResponse)
def get_capability(settings: SettingsDep) -> CapabilityResponse:
    cap = neo4j_service.probe_capability(settings)
    return CapabilityResponse(
        connected=cap.connected,
        server_info=cap.server_info,
        gds_available=cap.gds_available,
        gds_licensed=cap.gds_licensed,
        error=cap.error,
    )


class ParityRequest(BaseModel):
    dataset_id: str = Field(..., min_length=1, max_length=128)
    query_key: str = Field(..., min_length=1, max_length=128)
    iterations: int = Field(default=1, ge=1, le=10)
    warmup: int = Field(default=0, ge=0, le=5)


class ParityRow(BaseModel):
    app: str | None = None
    tool: str | None = None
    source: str | None = None
    target: str | None = None
    kind: str | None = None
    cnt: int | None = None


class ParityResponse(BaseModel):
    query_key: str
    sql_rows: list[dict]
    cypher_rows: list[dict]
    sql_latency_ms: float | None
    cypher_latency_ms: float | None
    equal: bool
    timing_context: dict
    error: str | None = None


@router.post("/parity", response_model=ParityResponse)
def post_parity(
    payload: ParityRequest,
    db: DbDep,
    settings: SettingsDep,
    session: GuestSessionDep,
) -> ParityResponse:
    result = parity_service.run_parity(
        db, settings, session, payload.dataset_id,
        payload.query_key,
        iterations=payload.iterations,
        warmup=payload.warmup,
    )
    return ParityResponse(
        query_key=result.query_key,
        sql_rows=result.sql_rows,
        cypher_rows=result.cypher_rows,
        sql_latency_ms=result.sql_latency_ms,
        cypher_latency_ms=result.cypher_latency_ms,
        equal=result.equal,
        timing_context=result.timing_context,
        error=result.error,
    )


class CommunityResponse(BaseModel):
    provider: str
    algorithm: str
    communities: list[list[str]]
    modularity: float | None
    note: str


@router.get(
    "/communities/{dataset_id}",
    response_model=CommunityResponse,
)
def get_communities(
    dataset_id: str,
    db: DbDep,
    settings: SettingsDep,
    session: GuestSessionDep,
) -> CommunityResponse:
    result = gds_service.detect_communities(db, settings, session, dataset_id)
    return CommunityResponse(
        provider=result.provider,
        algorithm=result.algorithm,
        communities=result.communities,
        modularity=result.modularity,
        note=result.note,
    )


class CriticalDepsResponse(BaseModel):
    target: str
    impact_set: list[str]
    impact_size: int
    target_in_degree: int
    target_out_degree: int
    target_degree_centrality: float
    note: str


@router.get(
    "/critical/{dataset_id}/{node_ref}",
    response_model=CriticalDepsResponse,
)
def get_critical_deps(
    dataset_id: str,
    node_ref: str,
    db: DbDep,
    session: GuestSessionDep,
) -> CriticalDepsResponse:
    g = build_digraph(db, session, dataset_id)
    try:
        cd = critical_dependencies(g, node_ref)
    except ValueError as exc:
        raise AppError(str(exc), status_code=404, code="not_found") from exc
    return CriticalDepsResponse(**cd)
