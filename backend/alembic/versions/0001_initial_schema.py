"""Initial schema: guest sessions, experiments, runs, run events, graph nodes/edges.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-11
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _guid():
    from app.models.base import GUID

    return GUID()


def upgrade() -> None:
    # guest_sessions — unique cookie token inline (SQLite-friendly).
    op.create_table(
        "guest_sessions",
        sa.Column("id", _guid(), primary_key=True, nullable=False),
        sa.Column("cookie_token", sa.String(128), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locale", sa.String(8), nullable=False, server_default="en"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_guest_sessions_expires_at", "guest_sessions", ["expires_at"])
    op.create_index("ix_guest_sessions_cookie_token", "guest_sessions", ["cookie_token"])

    # experiments — unique (id, version) inline.
    op.create_table(
        "experiments",
        sa.Column("pk", _guid(), primary_key=True, nullable=False),
        sa.Column("id", sa.String(128), nullable=False, index=True),
        sa.Column("module_id", sa.String(128), nullable=False, index=True),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("manifest_digest", sa.String(128), nullable=False),
        sa.Column("manifest_yaml", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("id", "version", name="ux_experiments_id_version"),
    )

    # runs
    op.create_table(
        "runs",
        sa.Column("id", _guid(), primary_key=True, nullable=False),
        sa.Column("session_id", _guid(), nullable=False),
        sa.Column("experiment_id", sa.String(128), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="CREATED"),
        sa.Column("inputs_json", sa.JSON(), nullable=True),
        sa.Column("outputs_json", sa.JSON(), nullable=True),
        sa.Column("verification_json", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trace_id", sa.String(128), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["guest_sessions.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_runs_session_id", "runs", ["session_id"])
    op.create_index("ix_runs_experiment_id", "runs", ["experiment_id"])
    op.create_index("ix_runs_status", "runs", ["status"])

    # run_events
    op.create_table(
        "run_events",
        sa.Column("id", _guid(), primary_key=True, nullable=False),
        sa.Column("run_id", _guid(), nullable=False),
        sa.Column("step", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("record_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_run_events_run_id", "run_events", ["run_id"])
    op.create_index("ix_run_events_step", "run_events", ["step"])

    # graph_nodes — unique (session, dataset, ref) inline.
    op.create_table(
        "graph_nodes",
        sa.Column("id", _guid(), primary_key=True, nullable=False),
        sa.Column("session_id", _guid(), nullable=False),
        sa.Column("dataset_id", sa.String(128), nullable=False),
        sa.Column("node_ref", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("attributes_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["guest_sessions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("session_id", "dataset_id", "node_ref", name="ux_gn_session_dataset_ref"),
    )
    op.create_index("ix_gn_session_dataset", "graph_nodes", ["session_id", "dataset_id"])
    op.create_index("ix_gn_kind", "graph_nodes", ["kind"])

    # graph_edges
    op.create_table(
        "graph_edges",
        sa.Column("id", _guid(), primary_key=True, nullable=False),
        sa.Column("session_id", _guid(), nullable=False),
        sa.Column("dataset_id", sa.String(128), nullable=False),
        sa.Column("source_id", _guid(), nullable=False),
        sa.Column("target_id", _guid(), nullable=False),
        sa.Column("relation", sa.String(64), nullable=False),
        sa.Column("attributes_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["guest_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["graph_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_id"], ["graph_nodes.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "session_id", "dataset_id", "source_id", "target_id", "relation",
            name="ux_ge_session_dataset_src_tgt_rel",
        ),
    )
    op.create_index("ix_ge_session_dataset", "graph_edges", ["session_id", "dataset_id"])
    op.create_index("ix_ge_relation", "graph_edges", ["relation"])


def downgrade() -> None:
    op.drop_table("graph_edges")
    op.drop_table("graph_nodes")
    op.drop_table("run_events")
    op.drop_table("runs")
    op.drop_table("experiments")
    op.drop_table("guest_sessions")
