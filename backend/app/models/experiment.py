"""Experiment manifest record. Wired in G05 with full manifest parsing."""
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, GUID, TimestampMixin


class Experiment(Base, TimestampMixin):
    __tablename__ = "experiments"
    __table_args__ = (
        Index("ix_experiments_module_id", "module_id"),
        Index("ux_experiments_id_version", "id", "version", unique=True),
    )

    pk: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, default=uuid.uuid4
    )
    id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    module_id: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    manifest_digest: Mapped[str] = mapped_column(String(128), nullable=False)
    manifest_yaml: Mapped[str] = mapped_column(Text, nullable=False)
