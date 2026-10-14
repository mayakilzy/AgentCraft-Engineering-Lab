"""Guest session model. Wired into the session lifecycle in G07."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, GUID, TimestampMixin


class GuestSession(Base, TimestampMixin):
    __tablename__ = "guest_sessions"
    __table_args__ = (Index("ix_guest_sessions_expires_at", "expires_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, default=uuid.uuid4
    )
    cookie_token: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )  # opaque random token; the cookie value the client carries
    # NOTE: `index=True` is intentionally omitted here — the explicit
    # Index("ix_guest_sessions_expires_at", "expires_at") in __table_args__
    # below creates the same index. Having both caused a duplicate-index
    # error on fresh DB init (Mission H ISSUE-002, fixed Mission I).
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    locale: Mapped[str] = mapped_column(String(8), nullable=False, default="en")
