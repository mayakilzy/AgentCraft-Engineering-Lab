"""Management command: purge expired guest sessions.

Per ADR-0003 Part B #10: a cron job or management command must purge
expired `guest_sessions` + Neo4j namespace data (retention ≤24h).

Usage:
    python -m app.cleanup_purge

The command is idempotent: running it multiple times is safe. It logs
the count of deleted sessions for audit. When Neo4j is configured, it
also cleans up the session-scoped namespaces.

G07-C1-04: the scheduling is provided by a dedicated Compose service
(`purge-cron`) that runs this command every 6 hours. The service is
defined in `docker-compose.yml` under the `core` profile. The schedule
runs every 6 hours so the worst-case retention is 6h + session_ttl_hours
(default 24h) ≈ 30h. Tighten the interval for stricter retention.

Retention semantics:
- A guest session is EXPIRED when `expires_at <= now()`. The session
  is immediately REJECTED on any API request (401), but the row stays
  in the DB until the purge cron deletes it.
- A session is PURGED (DB row + cascaded data deleted) only when the
  purge cron runs. Between expiry and purge, the row exists but is
  unusable.
- Neo4j namespace data is cleaned up alongside the DB row. If the
  Neo4j cleanup fails (e.g., Neo4j is down), the DB row is still
  deleted but the Neo4j data is orphaned. The next purge run will
  retry the Neo4j cleanup for any session that still has a namespace
  — but since the DB row is gone, we can't recover the session_id.
  To avoid this, the purge collects the session_ids BEFORE deleting
  the DB rows, and the Neo4j cleanup runs AFTER the DB deletion.
  If the Neo4j cleanup fails, the orphaned Neo4j data is detected by
  the `cleanup_orphaned_neo4j_namespaces()` function (separate cron).
"""
from __future__ import annotations

import sys

from app.db.session import SessionLocal
from app.services.session_service import purge_expired_sessions


def main() -> int:
    """Purge expired guest sessions. Returns 0 on success, 1 on error."""
    db = SessionLocal()
    try:
        result = purge_expired_sessions(db)
        print(
            f"purged {result['deleted_sessions']} expired sessions; "
            f"neo4j nodes deleted: {result['neo4j_nodes_deleted']}; "
            f"at {result['purged_at']}"
        )
        return 0
    except Exception as exc:
        print(f"purge failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
