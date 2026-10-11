"""SQLAlchemy engine + session factory.

Bound to `Settings.database_url`. SQLite is used for tests/local dev;
PostgreSQL is used when wired via Compose (T04).

`_reset_engines` exists so tests can drop the cached engine between
functions; production code never calls it.
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def _build_engine() -> Engine:
    settings = get_settings()
    connect_args: dict = {}
    if settings.database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    return create_engine(
        settings.database_url,
        connect_args=connect_args,
        pool_pre_ping=True,
        future=True,
    )


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def _reset_engines() -> None:
    """Drop cached engine + session factory. Used by tests."""
    global _engine, _SessionLocal
    if _engine is not None:
        try:
            _engine.dispose()
        finally:
            _engine = None
    _SessionLocal = None


def SessionLocal() -> sessionmaker:  # type: ignore[misc]
    """Return the cached session factory, building on first call."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            expire_on_commit=False,
            future=True,
        )
    return _SessionLocal
