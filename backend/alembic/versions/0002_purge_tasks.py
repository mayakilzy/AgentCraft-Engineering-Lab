"""Add purge_tasks table for recoverable Neo4j cleanup.

Revision ID: 0002_purge_tasks
Revises: 0001_initial
Create Date: 2026-10-12

G07-C2-01: a persistent record of incomplete Neo4j cleanup tasks. When
a guest session expires and the purge cron runs, the session_id + Neo4j
namespace are recorded in `purge_tasks` BEFORE the PostgreSQL row is
deleted. If the Neo4j cleanup fails, the task stays in `pending` status
and is retried on the next purge run. This ensures no session_id is lost
even if Neo4j is temporarily unavailable.

The table does NOT have a foreign key to guest_sessions (the session row
is deleted before the Neo4j cleanup, so a FK would be violated). The
session_id is stored as a plain UUID for the retry loop.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_purge_tasks"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _guid():
    from app.models.base import GUID
    return GUID()


def upgrade() -> None:
    op.create_table(
        "purge_tasks",
        sa.Column("id", _guid(), primary_key=True, nullable=False),
        # The session_id whose Neo4j namespace needs cleanup.
        # No FK — the guest_sessions row is deleted before the Neo4j
        # cleanup, so a FK would be violated. The session_id is stored
        # as a plain UUID for the retry loop.
        sa.Column("session_id", _guid(), nullable=False),
        # The Neo4j namespace prefix (e.g., "__sess_abc123def456__").
        # Stored so the retry knows what to clean up without needing
        # the guest_sessions row.
        sa.Column("neo4j_namespace", sa.String(128), nullable=False),
        # pending: needs cleanup; done: cleanup succeeded; failed:
        # cleanup failed after max retries (operator intervention).
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_purge_tasks_status", "purge_tasks", ["status"])
    op.create_index("ix_purge_tasks_session_id", "purge_tasks", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_purge_tasks_session_id", table_name="purge_tasks")
    op.drop_index("ix_purge_tasks_status", table_name="purge_tasks")
    op.drop_table("purge_tasks")
