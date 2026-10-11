"""Common DTOs shared across endpoints."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str = Field(..., description="Stable short error code")
    message: str
    request_id: str
    details: Optional[dict] = None


class PaginatedMeta(BaseModel):
    """Pagination metadata shared across list responses (added in later groups)."""
    total: int
    limit: int
    offset: int
