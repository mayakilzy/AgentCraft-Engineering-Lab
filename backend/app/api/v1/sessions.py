"""Guest session endpoints. Minimal for G02; full lifecycle in G07.

- POST /api/v1/sessions/guest  → create session, set HttpOnly cookie.
"""
from __future__ import annotations

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

from app.api.deps import DbDep, GuestSessionDep, SettingsDep
from app.models.guest_session import GuestSession
from app.services import session_service

router = APIRouter(prefix="/sessions", tags=["sessions"])


class GuestCreateRequest(BaseModel):
    locale: str = Field(default="en", pattern="^(en|ar)$")


class GuestCreateResponse(BaseModel):
    session_id: str
    expires_at: str  # ISO8601
    locale: str


@router.post(
    "/guest",
    response_model=GuestCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_guest(
    payload: GuestCreateRequest,
    db: DbDep,
    settings: SettingsDep,
    response: Response,
) -> GuestCreateResponse:
    gs = session_service.create_guest_session(db, settings, payload.locale)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=gs.cookie_token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )
    return GuestCreateResponse(
        session_id=str(gs.id),
        expires_at=gs.expires_at.isoformat(),
        locale=gs.locale,
    )


@router.get("/me", tags=["sessions"])
def whoami(session: GuestSessionDep) -> dict:
    """Return public session metadata. No secret."""
    return {
        "session_id": str(session.id),
        "expires_at": session.expires_at.isoformat(),
        "locale": session.locale,
    }
