"""PurgeTask model — persistent record of incomplete Neo4j cleanup tasks.

G07-C2-01: when a guest session expires and the purge cron runs, the
session_id + Neo4j namespace are recorded in `purge_tasks` BEFORE the
PostgreSQL row is deleted. If the Neo4j cleanup fails, the task stays in
`pending` status and is retried on the next purge run. This ensures no
session_id is lost even if Neo4j is temporarily unavailable.

The table does NOT have a foreign key to guest_sessions (the session row
is deleted before the Neo4j cleanup, so a FK would be violated).
"""
from __future__ import annotations

import uuid

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, GUID, TimestampMixin


class PurgeTask(Base, TimestampMixin):
    """A pending or completed Neo4j cleanup task.

    Lifecycle:
    - pending: needs cleanup (initial state)
    - done: cleanup succeeded (the row can be deleted by a separate
      cleanup cron, or kept for audit)
    - failed: cleanup failed after MAX_ATTEMPTS (operator intervention)
    """

    __tablename__ = "purge_tasks"
    __table_args__ = (
        Index("ix_purge_tasks_status", "status"),
        Index("ix_purge_tasks_session_id", "session_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, default=uuid.uuid4
    )
    # The session_id whose Neo4j namespace needs cleanup. No FK — the
    # guest_sessions row is deleted before the Neo4j cleanup.
    session_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    # The Neo4j namespace prefix (e.g., "__sess_abc123def456__").
    neo4j_namespace: Mapped[str] = mapped_column(String(128), nullable=False)
    # pending | done | failed
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending"
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


# Maximum cleanup attempts before a task is marked 'failed'.
# 6 attempts × 6h interval = 36h of retries before operator intervention.
MAX_PURGE_ATTEMPTS = 6
