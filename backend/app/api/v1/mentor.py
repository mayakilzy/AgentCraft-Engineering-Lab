"""Mentor API — T22 (G06).

Per the architecture contract §4 + §8:
- `POST /api/v1/mentor/explain` body `{run_id, question, lang}`;
  reply `{answer, diagnosis_state, evidence_refs, next_checks, provider_mode}`.
- Read-only, deterministic fallback when no LLM is configured.
- Session-scoped; 404 on cross-session run access.
- Question length bounded (≤ 2000 chars).
- Prompt-injection resistance: forbidden patterns rejected.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import DbDep, GuestSessionDep, SettingsDep
from app.core.errors import NotFoundError
from app.services import mentor_service

router = APIRouter(prefix="/mentor", tags=["mentor"])


class MentorRequest(BaseModel):
    run_id: str = Field(..., min_length=1, max_length=64)
    question: str = Field(..., min_length=1, max_length=2000)
    lang: Literal["en", "ar"] = "en"


class MentorResponse(BaseModel):
    answer: str
    diagnosis_state: Literal["confirmed", "likely", "insufficient_evidence"]
    evidence_refs: List[Dict[str, Any]] = Field(default_factory=list)
    next_checks: List[str] = Field(default_factory=list)
    provider_mode: str


@router.post("/explain", response_model=MentorResponse)
def explain_run(
    payload: MentorRequest,
    db: DbDep,
    settings: SettingsDep,
    session: GuestSessionDep,
) -> MentorResponse:
    """Build a grounded answer for the given run + question.

    The mentor is read-only and deterministic by default. The answer is
    built from the run's step verdicts + expected/actual blocks. When
    an LLM provider is configured, the deterministic answer is still
    returned (the LLM integration is wired in a later step; for now the
    deterministic fallback is the only mode).
    """
    try:
        rid = uuid.UUID(payload.run_id)
    except ValueError as exc:
        raise NotFoundError(f"invalid run_id: {payload.run_id}") from exc

    result = mentor_service.explain_run(
        db, settings, session, rid, payload.question, payload.lang,
    )
    return MentorResponse(
        answer=result.answer,
        diagnosis_state=result.diagnosis_state,
        evidence_refs=result.evidence_refs,
        next_checks=result.next_checks,
        provider_mode=result.provider_mode,
    )
