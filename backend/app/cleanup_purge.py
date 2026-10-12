"""Management command: purge expired guest sessions.

Per ADR-0003 Part B #10: a cron job or management command must purge
expired `guest_sessions` + Neo4j namespace data (retention ≤24h).

Usage:
    python -m app.cleanup_purge

The command is idempotent: running it multiple times is safe. It logs
the count of deleted sessions for audit. When Neo4j is configured, it
also cleans up the session-scoped namespaces.

Cron schedule (production):
    0 */6 * * *  cd /app && python -m app.cleanup_purge >> /var/log/agentcraft-purge.log 2>&1

The schedule runs every 6 hours so the worst-case retention is 6h +
session_ttl_hours (default 24h) ≈ 30h. Tighten the cron to every hour
for stricter retention.
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
