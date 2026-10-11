"""Shared pytest fixtures.

- `client`: a TestClient bound to a fresh in-memory SQLite DB per test
  function, with settings overrides that disable real network calls.
- `settings`: a Settings instance pinned to test defaults.
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
def client(settings):
    """TestClient against the production app, in-memory SQLite."""
    from app.db.session import _reset_engines  # wired in T04
    _reset_engines()
    from app.main import create_app
    app = create_app(settings=settings)
    with TestClient(app) as c:
        yield c
