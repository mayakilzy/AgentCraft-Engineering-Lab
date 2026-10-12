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

    G07-C2-01 design (cleanup-before-delete with persistent retry):
    1. Find expired sessions.
    2. For each expired session, create a `purge_tasks` row (status=
       pending) with the session_id + Neo4j namespace BEFORE deleting
       the PostgreSQL row. This ensures no session_id is lost even if
       the Neo4j cleanup fails.
    3. Attempt the Neo4j cleanup. If it succeeds, mark the task `done`.
       If it fails, the task stays `pending` and is retried on the next
       purge run (by `retry_pending_purge_tasks`).
    4. Delete the PostgreSQL row (CASCADE removes runs, run_events,
       graph_nodes, graph_edges). This happens AFTER the purge_tasks
       row is created, so the session_id is preserved for retry.
    5. After processing expired sessions, retry any pending tasks from
       previous runs (Neo4j may have recovered).

    G07-C2-04 retention guarantee: with session_ttl_hours=24 and a 6h
    purge interval, the worst-case retention is 24h (expiry) + 6h
    (next purge) = 30h. To guarantee ≤24h, set the purge interval to
    ≤1h OR set session_ttl_hours to ≤18h. The default is 24h TTL + 6h
    purge = 30h worst-case — documented honestly. The operator can
    tighten the interval for stricter retention.

    Returns a dict with:
    - deleted_sessions: count of PostgreSQL rows deleted
    - neo4j_nodes_deleted: count of Neo4j nodes deleted this run
    - neo4j_cleanup_failures: count of tasks that failed this run
    - pending_tasks_remaining: count of tasks still pending (across
      all runs, including retries from previous runs)
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
    tasks_created = 0
    for gs in expired:
        # Compute the Neo4j namespace for this session.
        namespace = f"__{gs.id.hex[:24]}__"
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

    # G07-C2-01: retry ALL pending purge tasks (new + from previous runs).
    # This is the recovery mechanism — if Neo4j was down in a previous
    # run, the pending tasks are retried now.
    retry_result = _retry_pending_purge_tasks(db)

    log.info(
        "purged expired sessions",
        extra={
            "deleted_sessions": len(expired),
            "tasks_created": tasks_created,
            "neo4j_nodes_deleted": retry_result["neo4j_nodes_deleted"],
            "neo4j_cleanup_failures": retry_result["failures"],
            "pending_tasks_remaining": retry_result["pending_remaining"],
        },
    )
    return {
        "deleted_sessions": len(expired),
        "neo4j_nodes_deleted": retry_result["neo4j_nodes_deleted"],
        "neo4j_cleanup_failures": retry_result["failures"],
        "pending_tasks_remaining": retry_result["pending_remaining"],
        "purged_at": now.isoformat(),
    }


def _retry_pending_purge_tasks(db: Session) -> dict:
    """Retry all pending purge_tasks (Neo4j cleanup).

    G07-C2-01: this is the recovery mechanism. Called by
    `purge_expired_sessions` after creating new tasks + deleting the
    PostgreSQL rows. It processes ALL pending tasks (new + from previous
    runs), so a transient Neo4j outage is recovered automatically.

    For each pending task:
    1. Attempt the Neo4j cleanup using the stored `neo4j_namespace`.
    2. If it succeeds, mark the task `done` and delete it (audit not
       required for V1; the task row is the audit).
    3. If it fails, increment `attempts` + record `last_error`. If
       attempts >= MAX_PURGE_ATTEMPTS, mark the task `failed` (operator
       intervention needed).
    4. When Neo4j is not configured, the task is marked `done` (no-op;
       the namespace was never created).

    Returns:
    - neo4j_nodes_deleted: total nodes deleted this run
    - failures: count of tasks that failed this run
    - pending_remaining: count of tasks still pending (will be retried
      next run)
    """
    from app.models.purge_task import PurgeTask, MAX_PURGE_ATTEMPTS

    pending = db.execute(
        select(PurgeTask).where(PurgeTask.status == "pending")
    ).scalars().all()

    neo4j_deleted = 0
    failures = 0

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
                failures += 1
            # else: stays pending, retried next run.

    db.commit()

    # Count remaining pending tasks.
    remaining = db.execute(
        select(PurgeTask).where(PurgeTask.status == "pending")
    ).scalars().all()

    return {
        "neo4j_nodes_deleted": neo4j_deleted,
        "failures": failures,
        "pending_remaining": len(remaining),
    }
