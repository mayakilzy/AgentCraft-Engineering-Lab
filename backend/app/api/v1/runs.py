"""Runs API — T18 (G05).

Per the architecture contract §4:
- `POST /api/v1/experiments/{id}/runs` body `{mode, inputs}`; returns
  `{run_id, status, trace_id}`.
- `GET /api/v1/runs/{id}` returns bounded run state/output/verification,
  scoped to cookie session (404 on cross-session).
- `GET /api/v1/runs?experiment_id=&limit=` paginated/scope-limited.
- `POST /api/v1/runs/{id}/reset` recreates clean fixture; does not mutate
  the prior terminal run.
- `GET /api/v1/runs/{id}/export?format=md|json` report including
  provenance, expected/actual, metric definitions.
- `POST /api/v1/runs/compare` two scoped run IDs; neutral relative
  comparisons with runtime/context warnings.

Per ADR-0003 Part A step 1: trace_id is captured from the active OTEL span
at run creation (handled in run_service.create_and_execute_run).
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.api.deps import DbDep, GuestSessionDep, SettingsDep
from app.core.errors import AppError, InvalidStateError, NotFoundError
from app.services import run_service

router = APIRouter(prefix="/runs", tags=["runs"])


# ---- POST /experiments/{id}/runs ----

class RunCreateRequest(BaseModel):
    mode: Literal["guided", "challenge"] = "guided"
    inputs: Dict[str, Any] = Field(default_factory=dict)


class RunCreateResponse(BaseModel):
    run_id: str
    status: str
    trace_id: Optional[str] = None
    error_code: Optional[str] = None
    step_verdicts: List[Dict[str, Any]] = Field(default_factory=list)


# Note: this route lives under /experiments/{id}/runs (per the contract §4),
# but we keep it in this module because the runs service owns the lifecycle.
# It's mounted at the application level under /api/v1.
experiments_router = APIRouter(prefix="/experiments", tags=["experiments"])


@experiments_router.post(
    "/{experiment_id}/runs",
    response_model=RunCreateResponse,
)
def create_run(
    experiment_id: str,
    payload: RunCreateRequest,
    db: DbDep,
    settings: SettingsDep,
    session: GuestSessionDep,
) -> RunCreateResponse:
    """Create + execute a run for the given experiment.

    Per ADR-0003 step 1: the run record's trace_id is captured from the
    active OTEL span and stored on the runs table.

    G07/T26: the runs endpoint is rate-limited per session
    (RATE_LIMIT_PER_MINUTE=60 by default). This prevents a single
    guest session from overwhelming the lab with run requests.
    """
    # G07/T26: rate limit per session.
    from app.core.rate_limit import get_rate_limiter
    limiter = get_rate_limiter(settings)
    limiter.acquire(session.id)

    outcome = run_service.create_and_execute_run(
        db, settings, session, experiment_id, payload.mode, payload.inputs,
    )
    return RunCreateResponse(
        run_id=str(outcome.run_id),
        status=outcome.status,
        trace_id=outcome.trace_id,
        error_code=outcome.error_code,
        step_verdicts=outcome.step_verdicts,
    )


# ---- GET /runs/{id} ----

@router.get("/{run_id}")
def get_run(
    run_id: str,
    db: DbDep,
    session: GuestSessionDep,
) -> dict:
    """Return the run record (session-scoped). 404 on cross-session."""
    try:
        rid = uuid.UUID(run_id)
    except ValueError as exc:
        raise NotFoundError(f"invalid run_id: {run_id}") from exc
    return run_service.get_run(db, session, rid)


# ---- GET /runs ----

@router.get("")
def list_runs(
    db: DbDep,
    session: GuestSessionDep,
    experiment_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    """List the caller's run history (session-scoped, newest first)."""
    runs = run_service.list_runs(db, session, experiment_id=experiment_id, limit=limit)
    return {"count": len(runs), "runs": runs}


# ---- POST /runs/{id}/reset ----

class ResetResponse(BaseModel):
    run_id: str
    experiment_id: str
    dataset_id: Optional[str]
    dataset_ids: List[str] = Field(default_factory=list)
    deleted_nodes: int
    deleted_edges: int
    reset_event_id: str


@router.post("/{run_id}/reset", response_model=ResetResponse)
def reset_run(
    run_id: str,
    db: DbDep,
    settings: SettingsDep,
    session: GuestSessionDep,
) -> ResetResponse:
    """Recreate a clean fixture snapshot for the run's experiment.

    Per the contract: reset does NOT mutate the prior terminal run. It
    deletes the (session, dataset) graph rows and records an auditable
    reset event.
    """
    try:
        rid = uuid.UUID(run_id)
    except ValueError as exc:
        raise NotFoundError(f"invalid run_id: {run_id}") from exc
    result = run_service.reset_run(db, settings, session, rid)
    return ResetResponse(**result)


# ---- GET /runs/{id}/export ----

@router.get("/{run_id}/export")
def export_run(
    run_id: str,
    db: DbDep,
    session: GuestSessionDep,
    format: Literal["md", "json"] = Query(default="md"),
) -> dict:
    """Export a run as Markdown or JSON.

    Per the contract §4: `GET /api/v1/runs/{id}/export?format=md|json`.
    """
    try:
        rid = uuid.UUID(run_id)
    except ValueError as exc:
        raise NotFoundError(f"invalid run_id: {run_id}") from exc
    return run_service.export_run(db, session, rid, format)


# ---- POST /runs/compare ----

class CompareRequest(BaseModel):
    run_a_id: str
    run_b_id: str


class CompareResponse(BaseModel):
    run_a_id: str
    run_b_id: str
    same_experiment: bool
    same_final_status: bool
    same_step_count: bool
    step_diffs: List[Dict[str, Any]]
    note: str


@router.post("/compare", response_model=CompareResponse)
def compare_runs(
    payload: CompareRequest,
    db: DbDep,
    session: GuestSessionDep,
) -> CompareResponse:
    """Compare two session-scoped runs (neutral relative comparison)."""
    try:
        a_id = uuid.UUID(payload.run_a_id)
        b_id = uuid.UUID(payload.run_b_id)
    except ValueError as exc:
        raise NotFoundError("invalid run_id in compare payload") from exc
    result = run_service.compare_runs(db, session, a_id, b_id)
    return CompareResponse(
        run_a_id=str(result.run_a_id),
        run_b_id=str(result.run_b_id),
        same_experiment=result.same_experiment,
        same_final_status=result.same_final_status,
        same_step_count=result.same_step_count,
        step_diffs=result.step_diffs,
        note=result.note,
    )
