"""Graph node/edge models — relational baseline (contract §2 + §10).

Seed fixture skeleton committed in T04; concrete datasets (E01–E10) wired in
G02/G05. Synthetic AgentCraft-style data only; no scraped repos/accounts.
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base, GUID, TimestampMixin

JSONType = JSON().with_variant(JSONB(), "postgresql")


class GraphNode(Base, TimestampMixin):
    __tablename__ = "graph_nodes"
    __table_args__ = (
        UniqueConstraint("session_id", "dataset_id", "node_ref", name="ux_gn_session_dataset_ref"),
        Index("ix_gn_session_dataset", "session_id", "dataset_id"),
        Index("ix_gn_kind", "kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("guest_sessions.id", ondelete="CASCADE"), nullable=False
    )
    dataset_id: Mapped[str] = mapped_column(String(128), nullable=False)
    node_ref: Mapped[str] = mapped_column(String(128), nullable=False)  # stable external id
    kind: Mapped[str] = mapped_column(String(64), nullable=False)  # app|tool|skill|...
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    attributes_json: Mapped[dict | None] = mapped_column(JSONType, nullable=True)


class GraphEdge(Base, TimestampMixin):
    __tablename__ = "graph_edges"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "dataset_id",
            "source_id",
            "target_id",
            "relation",
            name="ux_ge_session_dataset_src_tgt_rel",
        ),
        Index("ix_ge_session_dataset", "session_id", "dataset_id"),
        Index("ix_ge_relation", "relation"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("guest_sessions.id", ondelete="CASCADE"), nullable=False
    )
    dataset_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("graph_nodes.id", ondelete="CASCADE"), nullable=False
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("graph_nodes.id", ondelete="CASCADE"), nullable=False
    )
    relation: Mapped[str] = mapped_column(String(64), nullable=False)
    attributes_json: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
