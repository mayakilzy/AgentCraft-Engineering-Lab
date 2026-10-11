"""Seed endpoint — load a deterministic fixture into a (session, dataset)."""
from __future__ import annotations

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.api.deps import DbDep, GuestSessionDep, SettingsDep
from app.services import graph_service

router = APIRouter(prefix="/graph", tags=["graph"])


class SeedRequest(BaseModel):
    dataset_key: str = Field(..., min_length=1, max_length=128)


class SeedResponse(BaseModel):
    dataset_id: str
    node_count: int
    edge_count: int


@router.post(
    "/{dataset_id}/seed",
    response_model=SeedResponse,
    status_code=status.HTTP_200_OK,
)
def seed_dataset(
    dataset_id: str,
    payload: SeedRequest,
    db: DbDep,
    settings: SettingsDep,
    session: GuestSessionDep,
) -> SeedResponse:
    """Idempotent seed: loads the named fixture if the dataset is empty;
    otherwise returns the existing counts (deterministic reruns)."""
    summary = graph_service.load_fixture(
        db, settings, session, dataset_id, payload.dataset_key,
    )
    return SeedResponse(
        dataset_id=summary["dataset_id"],
        node_count=summary["node_count"],
        edge_count=summary["edge_count"],
    )
