"""Management command: purge expired guest sessions.

Per ADR-0003 Part B #10 + G07-C2-02: the exit status honestly reflects
the purge outcome:
- exit 0: all purges succeeded (no pending tasks, no failures)
- exit 1: purge failed (DB error or unexpected exception)
- exit 2: partial success (some tasks pending retry or failed after
  max attempts)

The `|| true` pattern is NOT used — the cron loop logs the exit status
and continues, but the operator can alert on non-zero exits.

Usage:
    python -m app.cleanup_purge

G07-C2-04 retention semantics:
- A guest session is EXPIRED when `expires_at <= now()`. The session
  is immediately REJECTED on any API request (401), but the row stays
  in the DB until the purge cron deletes it.
- A session is PURGED (DB row + cascaded data deleted) only when the
  purge cron runs. Between expiry and purge, the row exists but is
  unusable.
- G07-C2-01: the Neo4j namespace cleanup is recoverable. If Neo4j is
  down during a purge run, a `purge_tasks` row records the pending
  cleanup. The next purge run retries it. The session_id is NOT lost
  (it's stored in `purge_tasks.session_id`).
- G07-C2-04 worst-case retention: with session_ttl_hours=24 and a 6h
  purge interval, the worst-case is 30h. To guarantee ≤24h, set the
  purge interval to ≤1h OR set session_ttl_hours to ≤18h. The default
  is 24h TTL + 6h purge = 30h — documented honestly.

Exit codes:
- 0: success (all pending tasks resolved, no failures)
- 1: error (DB error or unexpected exception)
- 2: partial (some tasks pending retry or failed — not full success)
"""
from __future__ import annotations

import sys

from app.db.session import SessionLocal
from app.services.session_service import purge_expired_sessions


def main() -> int:
    """Purge expired guest sessions. Returns 0/1/2 per the exit code contract.

    G08 قبول-1: exit 2 is returned when there are UNRESOLVED failed tasks
    (from this run or previous runs). This ensures failed tasks stay
    visible to monitoring — a subsequent run cannot return exit 0 while
    failed tasks remain in the table.
    """
    db = SessionLocal()
    try:
        result = purge_expired_sessions(db)
        deleted = result["deleted_sessions"]
        neo4j_deleted = result["neo4j_nodes_deleted"]
        failures_this_run = result["neo4j_cleanup_failures"]
        pending = result["pending_tasks_remaining"]
        failed = result["failed_tasks_remaining"]

        print(
            f"purged {deleted} expired sessions; "
            f"neo4j nodes deleted: {neo4j_deleted}; "
            f"failures this run: {failures_this_run}; "
            f"pending tasks remaining: {pending}; "
            f"failed tasks remaining: {failed}; "
            f"at {result['purged_at']}"
        )

        # G08 قبول-1: if there are failed tasks (from this run OR
        # previous runs), the exit status is 2 (partial). This makes
        # failed tasks visible to monitoring — the operator must
        # resolve them (or delete the purge_tasks row) before the
        # cron can return exit 0 again.
        if failed > 0:
            print(
                f"WARNING: {failed} failed purge tasks remain in the "
                f"purge_tasks table. Operator intervention required.",
                file=sys.stderr,
            )
            return 2
        if failures_this_run > 0:
            # Tasks that just transitioned to failed this run.
            return 2
        if pending > 0:
            # Some tasks are pending retry — partial success.
            return 2
        # Full success.
        return 0
    except Exception as exc:
        print(f"purge failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
