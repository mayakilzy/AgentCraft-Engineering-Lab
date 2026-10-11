"""FastAPI dependencies (settings, db session, request id).

Kept thin so test overrides are easy: `app.dependency_overrides[get_db] = ...`.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.core.logging import set_request_id

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_db() -> Session:
    """Yield a SQLAlchemy session. Wired in T04 with the real engine factory."""
    # Imported lazily so unit tests can run without a configured engine.
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbDep = Annotated[Session, Depends(get_db)]


def request_id_dep(request: Request) -> str:
    """Read or mint a request id, and stash it in the logging context var."""
    rid = request.headers.get("x-request-id") or str(uuid.uuid4())
    set_request_id(rid)
    return rid


RequestIdDep = Annotated[str, Depends(request_id_dep)]
