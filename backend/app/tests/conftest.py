"""Shared pytest fixtures.

- `client`: a TestClient bound to a fresh in-memory SQLite DB per test
  function, with settings overrides that disable real network calls.
- `settings`: a Settings instance pinned to test defaults.
- `db`: a Session against the same engine the app uses (for direct ORM
  assertions in service-layer tests).
- `guest_cookie`: an existing guest session's cookie value for graph tests.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

# Force test settings BEFORE importing the app. We overwrite (not setdefault)
# because the host environment may carry an unrelated DATABASE_URL.
os.environ["APP_ENV"] = "local"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["MENTOR_PROVIDER"] = "disabled"
os.environ["CORS_ORIGINS"] = '["http://localhost:5173"]'


@pytest.fixture()
def settings():
    from app.config import get_settings
    # Drop the lru_cache so each test session can re-read env.
    get_settings.cache_clear()
    return get_settings()


@pytest.fixture()
def db(settings):
    """Yield a Session against the test DB. Apply migrations once."""
    from alembic import command
    from alembic.config import Config as AlembicConfig
    from app.config import get_settings
    from app.db.session import _reset_engines, SessionLocal
    import tempfile

    _reset_engines()
    # Use a file-backed SQLite DB so tables persist across the app session
    # AND so alembic can run against the same file.
    fdb = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    fdb.close()
    os.environ["DATABASE_URL"] = f"sqlite:///{fdb.name}"
    get_settings.cache_clear()
    _reset_engines()

    # Run migrations on this file DB.
    cfg = AlembicConfig("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{fdb.name}")
    command.upgrade(cfg, "head")

    session = SessionLocal()
    yield session
    session.close()
    _reset_engines()
    try:
        os.unlink(fdb.name)
    except OSError:
        pass


@pytest.fixture()
def client(db):
    """TestClient against the production app, sharing the migration-applied DB.

    The `db` fixture already runs migrations and resets the engine cache; we
    just build the app on top of the same settings/env.
    """
    from app.config import get_settings
    from app.db.session import _reset_engines, SessionLocal
    _reset_engines()
    # Bind the engine factory to the migrated DB.
    get_settings.cache_clear()
    from app.main import create_app
    app = create_app(settings=get_settings())
    # Override the get_db dependency so the app uses our migrated engine.
    from app.api.deps import get_db
    def _override_get_db():
        s = SessionLocal()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
