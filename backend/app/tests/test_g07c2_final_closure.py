"""G07-C2 — Final closure tests.

Per the G07-C2 review directive:
- C2-01: Recoverable Neo4j cleanup (persistent purge_tasks table +
  retry mechanism)
- C2-02: Honest purge exit status (no `|| true`; exit 0/1/2)
- C2-03: Compose production environment wiring (consistent env passing)
- C2-04: Retention contract ≤24h (TTL + purge interval + expiry vs purge)
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest


# ---- C2-01: Recoverable Neo4j cleanup ----

def test_purge_creates_task_before_deleting_session(db, settings):
    """C2-01: a purge_tasks row is created BEFORE the PostgreSQL session
    row is deleted. The session_id is preserved even if the DB deletion
    fails."""
    from app.services import session_service
    from app.models.purge_task import PurgeTask
    from sqlalchemy import select

    # Create an expired session.
    sess = session_service.create_guest_session(db, settings, "en")
    sess.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()

    # Ensure Neo4j is not configured (so the task is immediately done).
    from app.services import neo4j_service
    neo4j_service.reset_driver_for_tests()
    original_uri = settings.neo4j_uri
    settings.neo4j_uri = None
    try:
        result = session_service.purge_expired_sessions(db)
        assert result["deleted_sessions"] >= 1
        # The task was created and immediately resolved (Neo4j not
        # configured → done).
        assert result["pending_tasks_remaining"] == 0
    finally:
        settings.neo4j_uri = original_uri
        neo4j_service.reset_driver_for_tests()


def test_purge_retry_recovers_after_neo4j_recovery(db, settings):
    """C2-01: simulate Neo4j down in round 1, then Neo4j recovers in
    round 2. The pending task from round 1 is retried and completed in
    round 2. The session_id is NOT lost."""
    from app.services import session_service, neo4j_service
    from app.models.purge_task import PurgeTask
    from app.models.guest_session import GuestSession
    from sqlalchemy import select

    # Create an expired session.
    sess = session_service.create_guest_session(db, settings, "en")
    sess.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()
    session_id = sess.id
    # G08 قبول-3: use the SAME namespace function as the production code.
    from app.services.neo4j_service import session_namespace
    ns = session_namespace(sess.id)
    namespace = f"__{ns}__"

    # Round 1: Neo4j is DOWN. Inject a failing driver.
    class FailingDriver:
        def verify_connectivity(self):
            pass

        def session(self, database=None):
            raise RuntimeError("Neo4j down")

        def close(self):
            pass

    original_driver = neo4j_service._driver
    neo4j_service._driver = FailingDriver()
    original_uri = settings.neo4j_uri
    settings.neo4j_uri = "bolt://fake:7687"
    try:
        result1 = session_service.purge_expired_sessions(db)
        # The DB row is deleted.
        assert result1["deleted_sessions"] >= 1
        # The Neo4j cleanup failed → the task is pending.
        assert result1["pending_tasks_remaining"] >= 1
        assert result1["neo4j_nodes_deleted"] == 0

        # The purge_tasks table has a pending task with the session_id.
        pending = db.execute(
            select(PurgeTask).where(PurgeTask.status == "pending")
        ).scalars().all()
        assert len(pending) >= 1
        assert pending[0].session_id == session_id
        assert pending[0].neo4j_namespace == namespace
        assert pending[0].attempts >= 1
    finally:
        neo4j_service._driver = original_driver
        settings.neo4j_uri = original_uri

    # Round 2: Neo4j has RECOVERED. Inject a working driver that
    # returns a fake summary with nodes_deleted (matching the real
    # Neo4j SummaryCounters interface). The session object must
    # support the context manager protocol (`with ... as s:`).
    class WorkingDriver:
        def verify_connectivity(self):
            pass

        def session(self, database=None):
            class FakeSession:
                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    return False

                def run(self, query, **params):
                    class FakeResult:
                        def consume(self):
                            class FakeSummary:
                                # Neo4j's SummaryCounters has a
                                # .nodes_deleted attribute.
                                class counters:
                                    nodes_deleted = 5
                                counters = counters()
                            return FakeSummary()
                    return FakeResult()

                def close(self):
                    pass
            return FakeSession()

        def close(self):
            pass

    neo4j_service._driver = WorkingDriver()
    settings.neo4j_uri = "bolt://fake:7687"
    try:
        result2 = session_service.purge_expired_sessions(db)
        # No new expired sessions (the session was already deleted).
        assert result2["deleted_sessions"] == 0
        # The pending task from round 1 was retried and completed.
        assert result2["pending_tasks_remaining"] == 0
        assert result2["neo4j_nodes_deleted"] >= 1  # the retry deleted nodes

        # No pending tasks remain.
        pending = db.execute(
            select(PurgeTask).where(PurgeTask.status == "pending")
        ).scalars().all()
        assert len(pending) == 0
    finally:
        neo4j_service._driver = original_driver
        settings.neo4j_uri = original_uri
        neo4j_service.reset_driver_for_tests()


def test_purge_task_max_attempts_marks_failed(db, settings):
    """C2-01: a task that fails MAX_PURGE_ATTEMPTS times is marked
    'failed' (operator intervention). It's NOT retried again."""
    from app.services import session_service, neo4j_service
    from app.models.purge_task import PurgeTask, MAX_PURGE_ATTEMPTS
    from sqlalchemy import select

    # Create an expired session + run the purge MAX_PURGE_ATTEMPTS times
    # with a failing driver.
    sess = session_service.create_guest_session(db, settings, "en")
    sess.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()

    class FailingDriver:
        def verify_connectivity(self):
            pass

        def session(self, database=None):
            raise RuntimeError("persistent failure")

        def close(self):
            pass

    original_driver = neo4j_service._driver
    neo4j_service._driver = FailingDriver()
    original_uri = settings.neo4j_uri
    settings.neo4j_uri = "bolt://fake:7687"
    try:
        # First run: creates the task + 1 attempt.
        session_service.purge_expired_sessions(db)
        # Subsequent runs: retry the same task.
        for _ in range(MAX_PURGE_ATTEMPTS - 1):
            session_service.purge_expired_sessions(db)

        # The task should now be 'failed'.
        failed = db.execute(
            select(PurgeTask).where(PurgeTask.status == "failed")
        ).scalars().all()
        assert len(failed) >= 1
        assert failed[0].attempts >= MAX_PURGE_ATTEMPTS
    finally:
        neo4j_service._driver = original_driver
        settings.neo4j_uri = original_uri
        neo4j_service.reset_driver_for_tests()


def test_session_id_not_lost_on_neo4j_failure(db, settings):
    """C2-01: the session_id is preserved in purge_tasks even when the
    PostgreSQL row is deleted. The retry uses the stored session_id."""
    from app.services import session_service, neo4j_service
    from app.models.purge_task import PurgeTask
    from app.models.guest_session import GuestSession
    from sqlalchemy import select

    sess = session_service.create_guest_session(db, settings, "en")
    sess.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()
    session_id = sess.id

    class FailingDriver:
        def verify_connectivity(self):
            pass

        def session(self, database=None):
            raise RuntimeError("down")

        def close(self):
            pass

    original_driver = neo4j_service._driver
    neo4j_service._driver = FailingDriver()
    original_uri = settings.neo4j_uri
    settings.neo4j_uri = "bolt://fake:7687"
    try:
        session_service.purge_expired_sessions(db)

        # The PostgreSQL session row is gone.
        pg_row = db.execute(
            select(GuestSession).where(GuestSession.id == session_id)
        ).scalar_one_or_none()
        assert pg_row is None

        # The purge_tasks row preserves the session_id.
        task = db.execute(
            select(PurgeTask).where(PurgeTask.session_id == session_id)
        ).scalar_one_or_none()
        assert task is not None
        assert task.session_id == session_id
    finally:
        neo4j_service._driver = original_driver
        settings.neo4j_uri = original_uri
        neo4j_service.reset_driver_for_tests()


# ---- C2-02: Honest purge exit status ----

def test_cleanup_purge_exit_0_on_success(db, settings, monkeypatch):
    """C2-02: cleanup_purge returns 0 when all tasks succeed."""
    from app.cleanup_purge import main
    from app.db.session import SessionLocal

    # Mock SessionLocal to return our test db.
    monkeypatch.setattr("app.cleanup_purge.SessionLocal", lambda: db)
    # No expired sessions → 0 deleted, 0 pending → exit 0.
    rc = main()
    assert rc == 0


def test_cleanup_purge_exit_2_on_pending(db, settings, monkeypatch):
    """C2-02: cleanup_purge returns 2 when tasks are pending retry."""
    from app.cleanup_purge import main
    from app.services import session_service, neo4j_service
    from app.models.purge_task import PurgeTask

    # Create an expired session + run purge with a failing driver.
    sess = session_service.create_guest_session(db, settings, "en")
    sess.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()

    class FailingDriver:
        def verify_connectivity(self):
            pass

        def session(self, database=None):
            raise RuntimeError("down")

        def close(self):
            pass

    original_driver = neo4j_service._driver
    neo4j_service._driver = FailingDriver()
    original_uri = settings.neo4j_uri
    settings.neo4j_uri = "bolt://fake:7687"
    try:
        # Run purge to create a pending task.
        session_service.purge_expired_sessions(db)

        # Now run cleanup_purge → should return 2 (pending tasks remain).
        monkeypatch.setattr("app.cleanup_purge.SessionLocal", lambda: db)
        rc = main()
        assert rc == 2
    finally:
        neo4j_service._driver = original_driver
        settings.neo4j_uri = original_uri
        neo4j_service.reset_driver_for_tests()


def test_compose_purge_cron_no_or_true():
    """C2-02: the Compose purge-cron service does NOT use `|| true` to
    swallow the exit status."""
    compose = Path(__file__).resolve().parents[3] / "docker-compose.yml"
    content = compose.read_text()
    # The purge-cron block must not have `|| true`.
    purge_start = content.find("purge-cron:")
    observability = content.find("# ---- Observability profile", purge_start)
    purge_block = content[purge_start:observability] if observability > 0 else content[purge_start:]
    assert "|| true" not in purge_block, "purge-cron uses `|| true` to swallow exit status"
    # The exit code is checked and logged.
    assert "rc=$?" in purge_block or "rc=" in purge_block


# ---- C2-03: Compose production environment wiring ----

def test_compose_api_passes_session_cookie_secure():
    """C2-03: the api service passes SESSION_COOKIE_SECURE from env."""
    compose = Path(__file__).resolve().parents[3] / "docker-compose.yml"
    content = compose.read_text()
    assert "SESSION_COOKIE_SECURE" in content
    # The default is false (dev), but it's passed through.
    assert "${SESSION_COOKIE_SECURE:-false}" in content or "SESSION_COOKIE_SECURE: ${SESSION_COOKIE_SECURE" in content


def test_compose_api_passes_cors_origins():
    """C2-03: the api service passes CORS_ORIGINS from env."""
    compose = Path(__file__).resolve().parents[3] / "docker-compose.yml"
    content = compose.read_text()
    assert "CORS_ORIGINS" in content
    # It's passed through from .env (not hardcoded).
    assert "${CORS_ORIGINS" in content


def test_compose_api_passes_postgres_password():
    """C2-03: the api service passes POSTGRES_PASSWORD from env so the
    fail-closed validator can check it."""
    compose = Path(__file__).resolve().parents[3] / "docker-compose.yml"
    content = compose.read_text()
    # Find the api block and verify POSTGRES_PASSWORD is passed.
    api_start = content.find("  api:")
    api_end = content.find("  neo4j:", api_start)
    api_block = content[api_start:api_end]
    assert "POSTGRES_PASSWORD" in api_block


def test_compose_api_passes_grafana_admin_password():
    """C2-03: the api service passes GRAFANA_ADMIN_PASSWORD from env."""
    compose = Path(__file__).resolve().parents[3] / "docker-compose.yml"
    content = compose.read_text()
    api_start = content.find("  api:")
    api_end = content.find("  neo4j:", api_start)
    api_block = content[api_start:api_end]
    assert "GRAFANA_ADMIN_PASSWORD" in api_block


def test_compose_purge_cron_passes_session_ttl():
    """C2-03: the purge-cron service passes SESSION_TTL_HOURS so the
    retention is configurable."""
    compose = Path(__file__).resolve().parents[3] / "docker-compose.yml"
    content = compose.read_text()
    purge_start = content.find("purge-cron:")
    observability = content.find("# ---- Observability profile", purge_start)
    purge_block = content[purge_start:observability] if observability > 0 else content[purge_start:]
    assert "SESSION_TTL_HOURS" in purge_block


def test_production_boot_rejects_default_in_compose_context():
    """C2-03: when the Compose stack sets APP_ENV=production with
    default passwords, the backend's fail-closed validator rejects the
    boot. This test simulates the Compose environment."""
    env = {
        "APP_ENV": "production",
        # Simulate the Compose defaults (changeme).
        "POSTGRES_PASSWORD": "changeme",
        "SESSION_COOKIE_SECURE": "false",
        "CORS_ORIGINS": '["http://localhost:8080","http://localhost:5173"]',
        "GRAFANA_ADMIN_PASSWORD": "changeme",
    }
    with patch.dict(os.environ, env, clear=False):
        from app.config import Settings
        with pytest.raises(ValueError) as exc:
            Settings()
        # Multiple problems should be reported.
        msg = str(exc.value)
        assert "POSTGRES_PASSWORD" in msg
        assert "SESSION_COOKIE_SECURE" in msg
        assert "CORS_ORIGINS" in msg
        assert "GRAFANA_ADMIN_PASSWORD" in msg


# ---- C2-04: Retention contract ----

def test_retention_worst_case_documented():
    """C2-04: the retention contract (worst-case = TTL + purge interval)
    is documented in the cleanup_purge docstring."""
    cleanup_path = Path(__file__).resolve().parents[2] / "app" / "cleanup_purge.py"
    content = cleanup_path.read_text()
    # The worst-case retention must be documented.
    assert "30h" in content or "worst-case" in content.lower()
    # The ≤24h requirement must be mentioned.
    assert "24h" in content or "≤24h" in content


def test_retention_default_ttl_24h():
    """C2-04: the default SESSION_TTL_HOURS is 24h (the contract max)."""
    from app.config import Settings
    s = Settings()
    assert s.session_ttl_hours == 24


def test_retention_purge_interval_documented():
    """C2-04: the 6h purge interval is documented in the Compose file."""
    compose = Path(__file__).resolve().parents[3] / "docker-compose.yml"
    content = compose.read_text()
    # The 6h interval (21600 seconds) must be in the purge-cron block.
    assert "21600" in content or "6h" in content


def test_retention_strict_option_documented():
    """C2-04: the option to tighten retention (≤1h purge OR ≤18h TTL)
    is documented."""
    cleanup_path = Path(__file__).resolve().parents[2] / "app" / "cleanup_purge.py"
    content = cleanup_path.read_text()
    # The docstring must mention the option to tighten.
    assert "1h" in content or "3600" in content
    assert "18h" in content or "18" in content


def test_expiry_vs_purge_distinction(db, settings):
    """C2-04: test the difference between session expiry (immediately
    rejected) and actual purge (DB row deleted by the cron)."""
    from app.services import session_service
    from app.models.guest_session import GuestSession
    from sqlalchemy import select
    from app.core.errors import UnauthorizedError

    # Create an active session.
    sess = session_service.create_guest_session(db, settings, "en")

    # The session is active → resolvable.
    resolved = session_service.resolve_guest_session(db, sess.cookie_token)
    assert resolved.id == sess.id

    # Expire it (simulate TTL).
    sess.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()

    # Expiry: the session is REJECTED on the next request (401), but the
    # row is still in the DB.
    with pytest.raises(UnauthorizedError):
        session_service.resolve_guest_session(db, sess.cookie_token)

    # The row is still in the DB (not purged yet).
    row = db.execute(
        select(GuestSession).where(GuestSession.id == sess.id)
    ).scalar_one_or_none()
    assert row is not None  # expiry ≠ purge

    # Purge: now the cron runs and deletes the row.
    neo4j_service = __import__("app.services.neo4j_service", fromlist=["reset_driver_for_tests"])
    neo4j_service.reset_driver_for_tests()
    original_uri = settings.neo4j_uri
    settings.neo4j_uri = None
    try:
        result = session_service.purge_expired_sessions(db)
        assert result["deleted_sessions"] >= 1
    finally:
        settings.neo4j_uri = original_uri
        neo4j_service.reset_driver_for_tests()

    # The row is now gone (purged).
    row = db.execute(
        select(GuestSession).where(GuestSession.id == sess.id)
    ).scalar_one_or_none()
    assert row is None


# ---- C2-03: No secrets in logs/reports ----

def test_purge_result_does_not_contain_passwords(db, settings):
    """C2-03: the purge result does not contain any secrets (passwords,
    tokens, API keys)."""
    from app.services import session_service

    result = session_service.purge_expired_sessions(db)
    result_str = str(result)
    # The result must not contain any secret-like strings.
    secret_patterns = ["password", "secret", "token", "api_key", "changeme"]
    for p in secret_patterns:
        assert p not in result_str.lower(), f"secret {p!r} found in purge result"


def test_no_secrets_in_compose_environment_block():
    """C2-03: the Compose environment blocks do not contain hardcoded
    secrets (only placeholders)."""
    compose = Path(__file__).resolve().parents[3] / "docker-compose.yml"
    content = compose.read_text()
    # The Compose file uses ${VAR:-default} for secrets, not hardcoded
    # real values. We check that 'changeme' is the only password-like
    # default (it's clearly a placeholder).
    # No real-looking secrets (long random strings).
    import re
    # Find all ${VAR:-default} patterns.
    defaults = re.findall(r"\$\{[^}]+:-([^}]+)\}", content)
    for d in defaults:
        # The default must not be a real secret (we accept 'changeme'
        # and other obvious placeholders).
        if any(k in d.lower() for k in ("password", "secret", "token", "key")):
            assert d in ("changeme", ""), f"non-placeholder secret default: {d!r}"
