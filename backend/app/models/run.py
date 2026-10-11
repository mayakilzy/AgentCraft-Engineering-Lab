"""Run + RunEvent models.

Run state machine (contract §5):
`CREATED → RUNNING → PASSED|FAILED|BLOCKED`; terminal states immutable.

A rerun creates a new run row. Reset creates a clean dataset snapshot
without mutating the prior terminal run (handled in G05+).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base, GUID, TimestampMixin


# Use JSONB on PostgreSQL, JSON elsewhere (SQLite tests).
JSONType = JSON().with_variant(JSONB(), "postgresql")


class Run(Base, TimestampMixin):
    __tablename__ = "runs"
    __table_args__ = (
        Index("ix_runs_session_id", "session_id"),
        Index("ix_runs_experiment_id", "experiment_id"),
        Index("ix_runs_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("guest_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    experiment_id: Mapped[str] = mapped_column(String(128), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)  # guided|challenge
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="CREATED"
    )  # CREATED|RUNNING|PASSED|FAILED|BLOCKED
    inputs_json: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    outputs_json: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    verification_json: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)


class RunEvent(Base, TimestampMixin):
    """Append-only event log per run. Used for step diagnostics + mentor grounding."""

    __tablename__ = "run_events"
    __table_args__ = (
        Index("ix_run_events_run_id", "run_id"),
        Index("ix_run_events_step", "step"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    step: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    record_json: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
