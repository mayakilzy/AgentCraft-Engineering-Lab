"""Session DTOs. Wire-up completed in G07 (guest session lifecycle)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class GuestSessionResponse(BaseModel):
    """Public metadata returned after creating a guest session.

    No secret is returned; the cookie carries the opaque session id.
    """
    session_id: UUID
    created_at: datetime
    expires_at: datetime
    locale: Literal["en", "ar"] = "en"
