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
    """Delete expired guest_sessions + their cascaded data + Neo4j namespaces.

    Per ADR-0003 Part B #10 + G07-C2-01: recoverable Neo4j cleanup.

    G08 قبول-1: failed tasks (status='failed') stay in the purge_tasks
    table and are reported in the result. The cleanup_purge command
    returns exit 2 when failed tasks remain — they don't become
    invisible. A subsequent run cannot return exit 0 while failed tasks
    exist.

    G08 قبول-3: the namespace stored in purge_tasks uses the SAME
    `session_namespace()` function as `neo4j_service.cleanup_session`
    and `neo4j_service.dataset_label`. This guarantees the retry cleans
    up the correct nodes (not a different session's namespace).

    G08 قبول-2 + C1-06 retention: with session_ttl_hours=24 and a 6h
    purge interval, the worst-case DATA RETENTION is 30h (TTL +
    purge_interval). This is NOT a ≤24h guarantee. To achieve a target
    data retention R, set TTL + purge_interval ≤ R. The previous claim
    that "purge interval ≤1h guarantees ≤24h" was incorrect —
    TTL=24h + purge_interval=1h = 25h. The guarantee does NOT hold
    during DB outages (the purge can't run if the DB is down).

    Session expiry (TTL) and data retention are DIFFERENT concepts:
    - TTL = how long a session is USABLE (default 24h).
    - Data retention = how long data STAYS in the DB after expiry
      (worst-case = TTL + purge_interval).

    Returns a dict with:
    - deleted_sessions: count of PostgreSQL rows deleted
    - neo4j_nodes_deleted: count of Neo4j nodes deleted this run
    - neo4j_cleanup_failures: count of tasks that transitioned to
      'failed' this run
    - pending_tasks_remaining: count of tasks still pending (will be
      retried next run)
    - failed_tasks_remaining: count of failed tasks in the table
      (including from previous runs — G08 قبول-1)
    - failed_task_ids: list of failed task IDs (for monitoring)
    - purged_at: ISO timestamp
    """
    from app.models.purge_task import PurgeTask, MAX_PURGE_ATTEMPTS

    now = _now_utc()
    # Find expired sessions.
    expired = db.execute(
        select(GuestSession).where(GuestSession.expires_at <= now)
    ).scalars().all()

    # G07-C2-01: create purge_tasks rows BEFORE deleting PostgreSQL.
    # This ensures the session_id + Neo4j namespace are preserved for
    # retry even if the Neo4j cleanup fails.
    #
    # G08 قبول-3: the namespace stored here MUST match the prefix used
    # by `neo4j_service.cleanup_session` and the labels created by
    # `neo4j_service.dataset_label`. Both use `session_namespace(session_id)`
    # as the base, so we use the same function here.
    from app.services.neo4j_service import session_namespace
    tasks_created = 0
    for gs in expired:
        # G08 قبول-3: use the SAME namespace function as neo4j_service
        # so the retry cleans up the correct nodes.
        ns = session_namespace(gs.id)
        namespace = f"__{ns}__"  # matches the prefix in cleanup_session
        task = PurgeTask(
            session_id=gs.id,
            neo4j_namespace=namespace,
            status="pending",
            attempts=0,
        )
        db.add(task)
        tasks_created += 1

    if tasks_created:
        db.commit()

    # Delete the PostgreSQL rows (CASCADE removes runs, run_events,
    # graph_nodes, graph_edges). The purge_tasks rows are NOT cascaded
    # (no FK), so they survive for retry.
    if expired:
        db.execute(
            delete(GuestSession).where(GuestSession.expires_at <= now)
        )
        db.commit()

    # G08 قبول-1: query BOTH pending AND failed tasks. Failed tasks
    # stay visible in the result so the operator can monitor them.
    # Failed tasks are NOT retried automatically (they've exhausted
    # MAX_PURGE_ATTEMPTS), but they remain in the purge_tasks table
    # until the operator resolves them (or deletes the row).
    pending = db.execute(
        select(PurgeTask).where(PurgeTask.status == "pending")
    ).scalars().all()

    neo4j_deleted = 0
    failures_this_run = 0

    # G08 قبول-1: count existing failed tasks (from previous runs).
    # These are NOT retried, but they must be reported so the operator
    # sees them. The cleanup_purge command returns exit 2 when there
    # are unresolved failed tasks.
    existing_failed = db.execute(
        select(PurgeTask).where(PurgeTask.status == "failed")
    ).scalars().all()

    # Check if Neo4j is configured.
    from app.config import get_settings
    from app.services import neo4j_service
    settings = get_settings()
    neo4j_configured = neo4j_service.get_driver(settings) is not None

    for task in pending:
        task.attempts += 1
        if not neo4j_configured:
            # Neo4j not configured → the namespace was never created.
            # Mark done (honest no-op).
            task.status = "done"
            db.delete(task)
            continue

        try:
            # Use the stored namespace to clean up. We construct a
            # minimal "session-like" object because cleanup_session
            # expects a session_id, but we have the namespace directly.
            # We call the Cypher directly via the driver.
            driver = neo4j_service.get_driver(settings)
            if driver is not None:
                with driver.session(database=settings.neo4j_database) as s:
                    result = s.run(
                        "MATCH (n) WHERE ANY(l IN labels(n) "
                        "WHERE l STARTS WITH $ns_prefix) "
                        "DETACH DELETE n",
                        ns_prefix=task.neo4j_namespace,
                    )
                    summary = result.consume()
                    # Neo4j's SummaryCounters has attributes like
                    # .nodes_deleted. We try the attribute first, then
                    # fall back to .get() (for our FakeDriver tests).
                    counters = getattr(summary, "counters", None)
                    if counters is not None:
                        deleted = int(getattr(counters, "nodes_deleted", 0))
                    else:
                        deleted = 0
                    neo4j_deleted += deleted
            task.status = "done"
            db.delete(task)
        except Exception as exc:
            task.last_error = f"{type(exc).__name__}: {exc}"
            log.warning(
                "neo4j cleanup failed for task",
                extra={
                    "task_id": str(task.id),
                    "session_id": str(task.session_id),
                    "attempts": task.attempts,
                    "error": task.last_error,
                },
            )
            if task.attempts >= MAX_PURGE_ATTEMPTS:
                task.status = "failed"
                failures_this_run += 1
            # else: stays pending, retried next run.

    db.commit()

    # G08 قبول-1: count remaining pending + failed tasks.
    remaining_pending = db.execute(
        select(PurgeTask).where(PurgeTask.status == "pending")
    ).scalars().all()
    remaining_failed = db.execute(
        select(PurgeTask).where(PurgeTask.status == "failed")
    ).scalars().all()

    log.info(
        "purged expired sessions",
        extra={
            "deleted_sessions": len(expired),
            "tasks_created": tasks_created,
            "neo4j_nodes_deleted": neo4j_deleted,
            "failures_this_run": failures_this_run,
            "pending_remaining": len(remaining_pending),
            "failed_remaining": len(remaining_failed),
        },
    )
    return {
        "deleted_sessions": len(expired),
        "neo4j_nodes_deleted": neo4j_deleted,
        # G08 قبول-1: failures_this_run is the count of tasks that
        # transitioned to 'failed' THIS run. failed_remaining is the
        # total count of failed tasks still in the table (including
        # from previous runs).
        "neo4j_cleanup_failures": failures_this_run,
        "pending_tasks_remaining": len(remaining_pending),
        "failed_tasks_remaining": len(remaining_failed),
        "failed_task_ids": [str(t.id) for t in remaining_failed],
        "purged_at": now.isoformat(),
    }
