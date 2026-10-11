"""Guest session service — minimal lifecycle for G02.

Full lifecycle (cookie issuance, CSRF, TTL refresh, scheduled purge,
per-IP+session rate limit) is wired in G07. For G02 we expose just enough
to:
- create a session row (POST /api/v1/sessions/guest)
- resolve a session from an opaque cookie token (dependency for graph ops)

This keeps G02 self-contained without prematurely implementing G07's
public-safety surface, and the cookie contract is already on the v1 API
contract.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.errors import UnauthorizedError
from app.models.guest_session import GuestSession


def _now_utc() -> datetime:
    """Current UTC time, tz-aware."""
    return datetime.now(timezone.utc)


def _normalize_dt(value: datetime) -> datetime:
    """Coerce a stored datetime to tz-aware UTC.

    SQLite stores `DateTime(timezone=True)` as a naive value even when the
    caller supplied tz-aware data; PostgreSQL preserves tz. We treat any
    naive stored value as UTC so comparisons stay correct.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def create_guest_session(db: Session, settings: Settings, locale: str = "en") -> GuestSession:
    """Mint a new guest session row. Caller sets the cookie."""
    if locale not in ("en", "ar"):
        locale = "en"
    token = secrets.token_urlsafe(32)  # 256-bit opaque random
    now = _now_utc()
    gs = GuestSession(
        id=uuid.uuid4(),
        cookie_token=token,
        expires_at=now + timedelta(hours=settings.session_ttl_hours),
        locale=locale,
    )
    db.add(gs)
    db.commit()
    db.refresh(gs)
    return gs


def resolve_guest_session(db: Session, cookie_token: str | None) -> GuestSession:
    """Resolve a session from the opaque cookie token. Raises 401 if missing
    or expired. Expired sessions are not auto-purged here (G07); they are
    simply rejected so callers cannot use them.
    """
    if not cookie_token:
        raise UnauthorizedError("guest session required")
    stmt = select(GuestSession).where(GuestSession.cookie_token == cookie_token)
    gs = db.execute(stmt).scalar_one_or_none()
    if gs is None:
        raise UnauthorizedError("invalid guest session")
    expires_at = _normalize_dt(gs.expires_at)
    if expires_at <= _now_utc():
        raise UnauthorizedError("guest session expired")
    return gs
