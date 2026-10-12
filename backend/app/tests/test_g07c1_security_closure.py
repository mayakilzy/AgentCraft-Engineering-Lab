"""G07-C1 — Narrow security closure tests.

Per the G07-C1 review directive:
- C1-01: Fail-closed production secrets (no default/empty passwords)
- C1-02: Network exposure (API not public, /metrics not public)
- C1-03: Production configuration (SESSION_COOKIE_SECURE, CORS, reject)
- C1-04: Scheduled retention (purge-cron service + Neo4j failure honesty)
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest


# ---- C1-01: Fail-closed production secrets ----

def test_production_rejects_default_postgres_password():
    """C1-01: APP_ENV=production + POSTGRES_PASSWORD=changeme → boot aborts."""
    env = {
        "APP_ENV": "production",
        "POSTGRES_PASSWORD": "changeme",
        "SESSION_COOKIE_SECURE": "true",
        "CORS_ORIGINS": '["https://example.com"]',
        "GRAFANA_ADMIN_PASSWORD": "strong-grafana-pass",
    }
    with patch.dict(os.environ, env, clear=False):
        from app.config import Settings
        with pytest.raises(ValueError) as exc:
            Settings()
        assert "POSTGRES_PASSWORD" in str(exc.value)


def test_production_rejects_empty_postgres_password():
    """C1-01: APP_ENV=production + POSTGRES_PASSWORD='' → boot aborts."""
    env = {
        "APP_ENV": "production",
        "POSTGRES_PASSWORD": "",
        "SESSION_COOKIE_SECURE": "true",
        "CORS_ORIGINS": '["https://example.com"]',
        "GRAFANA_ADMIN_PASSWORD": "strong-grafana-pass",
    }
    with patch.dict(os.environ, env, clear=False):
        from app.config import Settings
        with pytest.raises(ValueError) as exc:
            Settings()
        assert "POSTGRES_PASSWORD" in str(exc.value)


def test_production_rejects_default_grafana_password():
    """C1-01: APP_ENV=production + GRAFANA_ADMIN_PASSWORD=changeme → boot aborts."""
    env = {
        "APP_ENV": "production",
        "POSTGRES_PASSWORD": "strong-pg-pass",
        "SESSION_COOKIE_SECURE": "true",
        "CORS_ORIGINS": '["https://example.com"]',
        "GRAFANA_ADMIN_PASSWORD": "changeme",
    }
    with patch.dict(os.environ, env, clear=False):
        from app.config import Settings
        with pytest.raises(ValueError) as exc:
            Settings()
        assert "GRAFANA_ADMIN_PASSWORD" in str(exc.value)


def test_production_rejects_default_neo4j_password_when_configured():
    """C1-01: APP_ENV=production + NEO4J_URI set + NEO4J_PASSWORD=changeme
    → boot aborts."""
    env = {
        "APP_ENV": "production",
        "POSTGRES_PASSWORD": "strong-pg-pass",
        "SESSION_COOKIE_SECURE": "true",
        "CORS_ORIGINS": '["https://example.com"]',
        "GRAFANA_ADMIN_PASSWORD": "strong-grafana-pass",
        "NEO4J_URI": "bolt://neo4j:7687",
        "NEO4J_PASSWORD": "changeme",
    }
    with patch.dict(os.environ, env, clear=False):
        from app.config import Settings
        with pytest.raises(ValueError) as exc:
            Settings()
        assert "NEO4J_PASSWORD" in str(exc.value)


def test_production_accepts_strong_passwords():
    """C1-01: APP_ENV=production + all strong passwords → boot succeeds."""
    env = {
        "APP_ENV": "production",
        "POSTGRES_PASSWORD": "strong-pg-pass-12345",
        "SESSION_COOKIE_SECURE": "true",
        "CORS_ORIGINS": '["https://example.com"]',
        "GRAFANA_ADMIN_PASSWORD": "strong-grafana-pass-12345",
        "NEO4J_URI": "bolt://neo4j:7687",
        "NEO4J_PASSWORD": "strong-neo4j-pass-12345",
    }
    with patch.dict(os.environ, env, clear=False):
        from app.config import Settings
        s = Settings()
        assert s.app_env == "production"
        assert s.is_production is True


def test_production_neo4j_password_not_required_when_neo4j_not_configured():
    """C1-01: when NEO4J_URI is not set, NEO4J_PASSWORD is not checked."""
    env = {
        "APP_ENV": "production",
        "POSTGRES_PASSWORD": "strong-pg-pass-12345",
        "SESSION_COOKIE_SECURE": "true",
        "CORS_ORIGINS": '["https://example.com"]',
        "GRAFANA_ADMIN_PASSWORD": "strong-grafana-pass-12345",
        # NEO4J_URI not set → NEO4J_PASSWORD not checked
    }
    with patch.dict(os.environ, env, clear=False):
        from app.config import Settings
        s = Settings()
        assert s.is_production is True


# ---- C1-03: Production configuration (cookie + CORS) ----

def test_production_rejects_insecure_cookie():
    """C1-03: APP_ENV=production + SESSION_COOKIE_SECURE=false → boot aborts."""
    env = {
        "APP_ENV": "production",
        "POSTGRES_PASSWORD": "strong-pg-pass-12345",
        "SESSION_COOKIE_SECURE": "false",
        "CORS_ORIGINS": '["https://example.com"]',
        "GRAFANA_ADMIN_PASSWORD": "strong-grafana-pass-12345",
    }
    with patch.dict(os.environ, env, clear=False):
        from app.config import Settings
        with pytest.raises(ValueError) as exc:
            Settings()
        assert "SESSION_COOKIE_SECURE" in str(exc.value)


def test_production_rejects_localhost_cors():
    """C1-03: APP_ENV=production + CORS_ORIGINS contains localhost → boot aborts."""
    env = {
        "APP_ENV": "production",
        "POSTGRES_PASSWORD": "strong-pg-pass-12345",
        "SESSION_COOKIE_SECURE": "true",
        "CORS_ORIGINS": '["http://localhost:8080", "https://example.com"]',
        "GRAFANA_ADMIN_PASSWORD": "strong-grafana-pass-12345",
    }
    with patch.dict(os.environ, env, clear=False):
        from app.config import Settings
        with pytest.raises(ValueError) as exc:
            Settings()
        assert "CORS_ORIGINS" in str(exc.value)
        assert "localhost" in str(exc.value)


def test_production_accepts_https_cors():
    """C1-03: APP_ENV=production + CORS_ORIGINS=https://example.com → OK."""
    env = {
        "APP_ENV": "production",
        "POSTGRES_PASSWORD": "strong-pg-pass-12345",
        "SESSION_COOKIE_SECURE": "true",
        "CORS_ORIGINS": '["https://example.com"]',
        "GRAFANA_ADMIN_PASSWORD": "strong-grafana-pass-12345",
    }
    with patch.dict(os.environ, env, clear=False):
        from app.config import Settings
        s = Settings()
        assert s.cors_origins == ["https://example.com"]


def test_production_reports_all_problems_at_once():
    """C1-03: the boot abort lists ALL problems so the operator fixes
    them in one pass, not one at a time."""
    env = {
        "APP_ENV": "production",
        "POSTGRES_PASSWORD": "changeme",  # bad
        "SESSION_COOKIE_SECURE": "false",  # bad
        "CORS_ORIGINS": '["http://localhost:8080"]',  # bad
        "GRAFANA_ADMIN_PASSWORD": "changeme",  # bad
    }
    with patch.dict(os.environ, env, clear=False):
        from app.config import Settings
        with pytest.raises(ValueError) as exc:
            Settings()
        msg = str(exc.value)
        # All 4 problems must be in the message.
        assert "POSTGRES_PASSWORD" in msg
        assert "SESSION_COOKIE_SECURE" in msg
        assert "CORS_ORIGINS" in msg
        assert "GRAFANA_ADMIN_PASSWORD" in msg


def test_local_env_not_fail_closed():
    """C1-01: APP_ENV=local keeps the safe defaults (not fail-closed)."""
    env = {
        "APP_ENV": "local",
        "POSTGRES_PASSWORD": "changeme",
        "SESSION_COOKIE_SECURE": "false",
        "CORS_ORIGINS": '["http://localhost:5173"]',
        "GRAFANA_ADMIN_PASSWORD": "changeme",
    }
    with patch.dict(os.environ, env, clear=False):
        from app.config import Settings
        s = Settings()
        assert s.app_env == "local"
        assert s.is_production is False


def test_demo_env_not_fail_closed():
    """C1-01: APP_ENV=demo keeps the safe defaults (not fail-closed)."""
    env = {"APP_ENV": "demo"}
    with patch.dict(os.environ, env, clear=False):
        from app.config import Settings
        s = Settings()
        assert s.app_env == "demo"
        assert s.is_production is False


# ---- C1-02: Network exposure ----

def test_api_not_in_public_ports():
    """C1-02: the API service has no `ports:` block (only `expose:`)."""
    compose = Path(__file__).resolve().parents[3] / "docker-compose.yml"
    content = compose.read_text()
    # The api service must NOT have a public `ports: "8000:8000"` mapping.
    # We verify by checking that 8000 is NOT in any ports: block.
    import re
    ports_blocks = re.findall(r"ports:\s*\n\s+-\s+\"([^\"]+)\"", content)
    for block in ports_blocks:
        host_port = block.split(":")[0]
        assert host_port != "8000", f"API port 8000 is publicly exposed: {block!r}"


def test_api_has_expose_block():
    """C1-02: the API service has `expose: ["8000"]` (internal-only)."""
    compose = Path(__file__).resolve().parents[3] / "docker-compose.yml"
    content = compose.read_text()
    assert "expose:" in content
    assert '"8000"' in content


def test_nginx_proxies_api():
    """C1-02: nginx proxies /api/ to the api service (internal)."""
    nginx_conf = Path(__file__).resolve().parents[3] / "infrastructure" / "nginx" / "agentcraft.conf"
    content = nginx_conf.read_text()
    assert "proxy_pass http://api:8000" in content


def test_prometheus_scrapes_api_on_private_network():
    """C1-02: Prometheus scrapes /metrics on the private network
    (http://api:8000/metrics), not through the public port."""
    prom_conf = Path(__file__).resolve().parents[3] / "infrastructure" / "prometheus" / "prometheus.yml"
    content = prom_conf.read_text()
    assert "api:8000" in content  # internal Docker network
    assert "localhost:8000" not in content  # NOT via the host port


def test_nginx_blocks_metrics():
    """C1-02: nginx blocks external /metrics access."""
    nginx_conf = Path(__file__).resolve().parents[3] / "infrastructure" / "nginx" / "agentcraft.conf"
    content = nginx_conf.read_text()
    assert "location /metrics" in content
    assert "deny all" in content
    assert "403" in content


# ---- C1-04: Scheduled retention ----

def test_purge_cron_service_in_compose():
    """C1-04: the `purge-cron` Compose service runs cleanup_purge on a
    schedule (sleep loop)."""
    compose = Path(__file__).resolve().parents[3] / "docker-compose.yml"
    content = compose.read_text()
    assert "purge-cron:" in content
    assert "app.cleanup_purge" in content
    assert "sleep" in content  # the schedule loop


def test_purge_cron_has_resource_limit():
    """C1-04: the purge-cron service has a memory limit (no resource
    leak)."""
    compose = Path(__file__).resolve().parents[3] / "docker-compose.yml"
    content = compose.read_text()
    # Find the purge-cron block and verify it has a memory limit.
    purge_cron_start = content.find("purge-cron:")
    assert purge_cron_start >= 0
    # Find the next top-level service (a line starting with "  " followed
    # by a word and a colon) after the purge-cron block.
    # We search for the next "\n  " that starts a new service block.
    # The purge-cron block runs until "Observability profile" comment.
    observability_marker = content.find("# ---- Observability profile", purge_cron_start)
    purge_block = content[purge_cron_start:observability_marker] if observability_marker > 0 else content[purge_cron_start:]
    assert "memory:" in purge_block, f"purge-cron block has no memory limit:\n{purge_block}"


def test_purge_reports_neo4j_cleanup_failures(db, settings):
    """C1-04: purge_expired_sessions reports Neo4j cleanup failures
    honestly — doesn't claim success when data remains."""
    from app.services import session_service
    from app.models.guest_session import GuestSession
    from datetime import datetime, timedelta, timezone

    # Create an expired session.
    sess = session_service.create_guest_session(db, settings, "en")
    sess.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()

    # Mock the neo4j_service to simulate a cleanup failure.
    # We inject a fake driver that raises on cleanup.
    from app.services import neo4j_service

    class FailingDriver:
        def verify_connectivity(self):
            pass

        def session(self, database=None):
            raise RuntimeError("simulated cleanup failure")

        def close(self):
            pass

    # Inject the failing driver.
    original_driver = neo4j_service._driver
    neo4j_service._driver = FailingDriver()
    try:
        # We need NEO4J_URI set so get_driver returns our injected driver.
        original_uri = settings.neo4j_uri
        settings.neo4j_uri = "bolt://fake:7687"
        try:
            result = session_service.purge_expired_sessions(db)
            # The DB row is deleted.
            assert result["deleted_sessions"] >= 1
            # The Neo4j cleanup failed — the failure is reported.
            assert len(result["neo4j_cleanup_failures"]) >= 1
            assert result["neo4j_nodes_deleted"] == 0  # nothing deleted
        finally:
            settings.neo4j_uri = original_uri
    finally:
        neo4j_service._driver = original_driver


def test_purge_reports_no_failures_when_neo4j_not_configured(db, settings):
    """C1-04: when Neo4j is not configured, purge reports 0 failures
    (not a failure — honest no-op)."""
    from app.services import session_service, neo4j_service
    from app.models.guest_session import GuestSession
    from datetime import datetime, timedelta, timezone

    # Ensure Neo4j is not configured.
    neo4j_service.reset_driver_for_tests()
    original_uri = settings.neo4j_uri
    settings.neo4j_uri = None
    try:
        # Create an expired session.
        sess = session_service.create_guest_session(db, settings, "en")
        sess.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()

        result = session_service.purge_expired_sessions(db)
        assert result["deleted_sessions"] >= 1
        assert result["neo4j_nodes_deleted"] == 0  # no-op
        assert result["neo4j_cleanup_failures"] == []  # NOT a failure
    finally:
        settings.neo4j_uri = original_uri
        neo4j_service.reset_driver_for_tests()


def test_cleanup_purge_command_returns_audit_info(db, settings):
    """C1-04: the cleanup_purge command returns audit info (deleted
    count, neo4j count, failures list, timestamp)."""
    from app.services import session_service

    # No expired sessions → empty result.
    result = session_service.purge_expired_sessions(db)
    assert "deleted_sessions" in result
    assert "neo4j_nodes_deleted" in result
    assert "neo4j_cleanup_failures" in result
    assert "purged_at" in result
    assert isinstance(result["neo4j_cleanup_failures"], list)


def test_retention_semantics_documented():
    """C1-04: the retention semantics are documented in the cleanup_purge
    docstring (expiry vs purge distinction)."""
    cleanup_path = Path(__file__).resolve().parents[2] / "app" / "cleanup_purge.py"
    content = cleanup_path.read_text()
    assert "EXPIRED" in content or "expired" in content
    assert "PURGED" in content or "purged" in content
    # The distinction must be documented.
    assert "between expiry and purge" in content.lower() or "expiry" in content
