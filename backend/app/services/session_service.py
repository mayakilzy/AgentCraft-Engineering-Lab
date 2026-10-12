"""Guest session service — full lifecycle (G07/T25).

Per the architecture contract §4 + §9 + ADR-0003 Part B #10:
- Random HttpOnly Secure SameSite=Lax cookies (the Secure flag is set
  via `Settings.session_cookie_secure`, default false for local dev,
  MUST be true in production).
- CSRF prevention: state-changing endpoints (POST/PUT/DELETE) require
  either the SameSite=Lax cookie (which blocks cross-site POST in
  modern browsers) OR a custom X-Requested-With header. The middleware
  enforces the latter for non-simple requests.
- TTL cleanup: `purge_expired_sessions()` deletes expired guest_sessions
  rows + their cascaded graph/run data. Called by the
  `python -m app.cleanup_purge` management command + the G07 cron schedule.
- Strict session ownership: all endpoints resolve the session from the
  cookie server-side; no client-provided session_id is ever trusted.
  Cross-session access returns 404 (not 403, to avoid leaking run
  existence across sessions).
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.errors import UnauthorizedError
from app.core.logging import get_logger
from app.models.guest_session import GuestSession

log = get_logger(__name__)


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
    """Mint a new guest session row. Caller sets the cookie.

    The cookie token is 256-bit opaque random (secrets.token_urlsafe(32)).
    The TTL is bounded by `Settings.session_ttl_hours` (default 24h per
    the contract §9: "session TTL ≤24h").
    """
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
    or expired. Expired sessions are not auto-purged here; they are simply
    rejected so callers cannot use them. Use `purge_expired_sessions()` for
    the scheduled cleanup (G07/T25).
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


# ---- TTL cleanup (G07/T25 + ADR-0003 Part B #10) ----

def purge_expired_sessions(db: Session) -> dict:
    """Delete expired guest_sessions + their cascaded data.

    Per ADR-0003 Part B #10: a cron job or management command must purge
    expired `guest_sessions` + Neo4j namespace data (retention ≤24h).

    This function deletes expired guest_sessions rows. The CASCADE on
    the runs + run_events + graph_nodes + graph_edges foreign keys
    automatically removes the associated data. The Neo4j namespace
    cleanup is handled separately by `neo4j_service.cleanup_session`
    (called when Neo4j is configured).

    Returns a dict with the count of deleted sessions for the audit log.
    """
    now = _now_utc()
    # Find expired sessions.
    expired = db.execute(
        select(GuestSession).where(GuestSession.expires_at <= now)
    ).scalars().all()

    # Collect their ids + Neo4j namespaces before deletion (for the
    # Neo4j cleanup, which runs AFTER the DB deletion so the DB rows
    # don't orphan the Neo4j namespace).
    session_ids = [gs.id for gs in expired]

    # Delete the DB rows (CASCADE removes runs, run_events, graph_nodes,
    # graph_edges).
    if expired:
        db.execute(
            delete(GuestSession).where(GuestSession.expires_at <= now)
        )
        db.commit()

    # Clean up Neo4j namespaces for the expired sessions (best-effort;
    # no-op when Neo4j is not configured).
    neo4j_deleted = 0
    if session_ids:
        try:
            from app.config import get_settings
            from app.services import neo4j_service
            settings = get_settings()
            for sid in session_ids:
                neo4j_deleted += neo4j_service.cleanup_session(settings, sid)
        except Exception as exc:
            log.warning(
                "neo4j cleanup failed during purge",
                extra={"error": f"{type(exc).__name__}: {exc}"},
            )

    log.info(
        "purged expired sessions",
        extra={
            "deleted_sessions": len(expired),
            "neo4j_nodes_deleted": neo4j_deleted,
        },
    )
    return {
        "deleted_sessions": len(expired),
        "neo4j_nodes_deleted": neo4j_deleted,
        "purged_at": now.isoformat(),
    }
