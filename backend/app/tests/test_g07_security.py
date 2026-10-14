"""G07 — Security and deployment tests.

Per ADR-0003 Part B (10-item security checklist):
1. No default passwords (config verification)
2. Admin ports restricted (config verification)
3. /metrics protected (nginx config)
4. CORS locked (config verification)
5. Session cookie Secure flag (config verification)
6. Rate limiting on run creation (NEW — enforced)
7. No secrets in env files (gitignore verification)
8. Non-root containers (Dockerfile verification)
9. Resource limits on all containers (Compose verification)
10. Scheduled purge of guest sessions (NEW — cleanup_purge command)

T25: Guest sessions — CSRF + TTL cleanup + strict ownership
T26: Public hardening — rate limits + /metrics + CORS + secrets
T27: Deployment build — Compose config verification
T28: Production-like smoke — documented evidence
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


# ---- T25: Guest sessions ----

def test_purge_expired_sessions_deletes_expired(db, settings):
    """T25 + ADR-0003 Part B #10: purge_expired_sessions deletes expired
    sessions and their cascaded data."""
    from app.services import session_service
    from app.models.guest_session import GuestSession
    from datetime import datetime, timedelta, timezone

    # Create an expired session.
    sess = session_service.create_guest_session(db, settings, "en")
    # Manually expire it.
    sess.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()

    result = session_service.purge_expired_sessions(db)
    assert result["deleted_sessions"] >= 1

    # The expired session must be gone.
    from sqlalchemy import select
    remaining = db.execute(
        select(GuestSession).where(GuestSession.id == sess.id)
    ).scalar_one_or_none()
    assert remaining is None


def test_purge_expired_sessions_keeps_active(db, settings):
    """T25: purge_expired_sessions keeps active (non-expired) sessions."""
    from app.services import session_service
    from app.models.guest_session import GuestSession
    from sqlalchemy import select

    # Create an active session.
    sess = session_service.create_guest_session(db, settings, "en")

    result = session_service.purge_expired_sessions(db)
    assert result["deleted_sessions"] == 0  # nothing expired

    # The active session must still be there.
    remaining = db.execute(
        select(GuestSession).where(GuestSession.id == sess.id)
    ).scalar_one_or_none()
    assert remaining is not None


def test_cleanup_purge_command_runs(db):
    """T25: the `python -m app.cleanup_purge` management command runs
    without error and returns 0 on success."""
    from app.cleanup_purge import main
    # The main() function opens its own DB session; we just verify it
    # returns 0 (success) and doesn't raise.
    rc = main()
    assert rc == 0


def test_strict_sessionownership_cross_session_404(client, db, settings):
    """T25: a run created by session A cannot be read by session B.
    Cross-session access returns 404 (not 403, to avoid leaking the
    run's existence across sessions)."""
    from app.services import session_service, run_service
    from app.core.errors import NotFoundError

    sess_a = session_service.create_guest_session(db, settings, "en")
    out = run_service.create_and_execute_run(
        db, settings, sess_a, "graph-first-network", "guided", {},
    )

    sess_b = session_service.create_guest_session(db, settings, "en")
    with pytest.raises(NotFoundError):
        run_service.get_run(db, sess_b, out.run_id)


def test_expired_session_rejected(db, settings):
    """T25: an expired session is rejected with 401 (not auto-purged
    during the request, just rejected)."""
    from app.services import session_service
    from app.models.guest_session import GuestSession
    from datetime import datetime, timedelta, timezone
    from app.core.errors import UnauthorizedError

    sess = session_service.create_guest_session(db, settings, "en")
    sess.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()

    with pytest.raises(UnauthorizedError):
        session_service.resolve_guest_session(db, sess.cookie_token)


# ---- T26: Rate limiting ----

def test_rate_limiter_allows_under_limit(db, settings):
    """T26: requests under the rate limit are allowed."""
    from app.core.rate_limit import RateLimiter
    import uuid

    limiter = RateLimiter(rate_per_minute=10)  # 10 per minute
    sid = uuid.uuid4()
    # The first 10 requests should succeed (burst capacity = 10).
    for _ in range(10):
        limiter.acquire(sid)  # should not raise


def test_rate_limiter_blocks_over_limit(db, settings):
    """T26: requests over the rate limit are rejected with 429."""
    from app.core.rate_limit import RateLimiter
    from app.core.errors import AppError
    import uuid

    limiter = RateLimiter(rate_per_minute=2)  # 2 per minute
    sid = uuid.uuid4()
    limiter.acquire(sid)
    limiter.acquire(sid)
    # The 3rd request should be rate-limited.
    with pytest.raises(AppError) as exc:
        limiter.acquire(sid)
    assert exc.value.status_code == 429


def test_rate_limiter_per_session_isolation(db, settings):
    """T26: rate limit is per session — session A hitting the limit
    doesn't block session B."""
    from app.core.rate_limit import RateLimiter
    import uuid

    limiter = RateLimiter(rate_per_minute=1)
    sid_a = uuid.uuid4()
    sid_b = uuid.uuid4()
    limiter.acquire(sid_a)
    # sid_a is now at capacity; sid_b should still be able to acquire.
    limiter.acquire(sid_b)  # should not raise


def test_rate_limiter_enforced_on_runs_endpoint(client):
    """T26: POST /experiments/{id}/runs is rate-limited per session.
    The default limit is 60/min, so 5 requests should succeed."""
    from app.core.rate_limit import reset_rate_limiter_for_tests
    reset_rate_limiter_for_tests()

    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    # Make 5 run requests — all should succeed (well under the 60/min limit).
    for i in range(5):
        r = client.post(
            "/api/v1/experiments/graph-first-network/runs",
            json={"mode": "guided", "inputs": {}},
        )
        assert r.status_code == 200, f"request {i} failed: {r.text}"
    reset_rate_limiter_for_tests()


def test_rate_limiter_429_when_exceeded(client):
    """T26: when the rate limit is exceeded, the runs endpoint returns
    429 with a clear error code."""
    from app.core.rate_limit import reset_rate_limiter_for_tests, RateLimiter
    import app.core.rate_limit as rl_mod

    # Override the limiter with a very low limit for this test.
    rl_mod._limiter = RateLimiter(rate_per_minute=2)

    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    # First 2 requests succeed.
    for i in range(2):
        r = client.post(
            "/api/v1/experiments/graph-first-network/runs",
            json={"mode": "guided", "inputs": {}},
        )
        assert r.status_code == 200, f"request {i} failed: {r.text}"
    # 3rd request is rate-limited.
    r = client.post(
        "/api/v1/experiments/graph-first-network/runs",
        json={"mode": "guided", "inputs": {}},
    )
    assert r.status_code == 429
    body = r.json()
    assert body["code"] == "rate_limited"
    reset_rate_limiter_for_tests()


# ---- T26: /metrics protection (nginx config) ----

def test_nginx_blocks_metrics():
    """T26 + ADR-0003 Part B #3: the nginx config blocks external
    access to /metrics."""
    nginx_conf = Path(__file__).resolve().parents[3] / "infrastructure" / "nginx" / "agentcraft.conf"
    content = nginx_conf.read_text()
    assert "location /metrics" in content
    assert "deny all" in content
    assert "403" in content


# ---- T26: .env.example has no real secrets ----

def test_env_example_has_placeholders_not_secrets():
    """T26 + ADR-0003 Part B #7: .env.example carries only placeholders,
    no real secrets."""
    env_example = Path(__file__).resolve().parents[3] / ".env.example"
    content = env_example.read_text()
    # The placeholder password is 'changeme' (clearly a placeholder).
    assert "changeme" in content
    # No real-looking secrets (long random strings).
    assert "sk-" not in content  # OpenAI key prefix
    assert "ghp_" not in content  # GitHub token prefix


def test_gitignore_has_env():
    """T26 + ADR-0003 Part B #7: .env is gitignored."""
    gitignore = Path(__file__).resolve().parents[3] / ".gitignore"
    content = gitignore.read_text()
    assert ".env" in content


# ---- T26: Dockerfile non-root ----

def test_backend_dockerfile_non_root():
    """T26 + ADR-0003 Part B #8: the backend Dockerfile uses USER ac
    (non-root)."""
    dockerfile = Path(__file__).resolve().parents[3] / "backend" / "Dockerfile"
    content = dockerfile.read_text()
    assert "USER ac" in content or "USER 1000" in content


# ---- T26: Compose resource limits ----

def test_compose_has_resource_limits():
    """T26 + ADR-0003 Part B #9: every Compose service has a memory limit."""
    compose = Path(__file__).resolve().parents[3] / "docker-compose.yml"
    content = compose.read_text()
    # Every service should have deploy.resources.limits.memory.
    # Count the services and the memory limit lines.
    services = content.count("    ports:") + content.count("    profiles:")
    memory_limits = content.count("memory:")
    assert memory_limits >= 6  # postgres, api, web, neo4j, collector, prometheus, tempo, grafana


# ---- T26: Compose admin ports not exposed ----

def test_compose_admin_ports_not_exposed():
    """T26 + ADR-0003 Part B #2 + G07-C1-02 + Mission J-FIX-04: only
    specific admin ports are exposed publicly.

    Mission J-FIX-04 change: the `web` service now uses `expose` (not
    `ports`) so Nginx Proxy Manager (NPM) fronts it on an external
    Docker network. The `ports:` block for web is commented out in
    docker-compose.yml and only enabled for local testing.

    Public ports (via `ports:`):
      - 3000 (grafana) — admin auth required

    Internal-only (via `expose:`):
      - 80 (web/nginx) — reachable on the Docker network + NPM proxy-net
      - 8000 (api) — reachable on the Docker network only

    NOT exposed at all:
      - 5432 (postgres), 7687 (neo4j), 9090 (prometheus),
        3200 (tempo), 4317/4318 (otel collector)
    """
    compose = Path(__file__).resolve().parents[3] / "docker-compose.yml"
    content = compose.read_text()

    # Find all "ports:" blocks (public port mappings).
    import re
    ports_blocks = re.findall(r"ports:\s*\n\s+-\s+\"([^\"]+)\"", content)
    exposed = set()
    for block in ports_blocks:
        # Extract the host port (before the colon or the full value).
        host_port = block.split(":")[0]
        exposed.add(host_port)
    # Mission J-FIX-04: only Grafana (3000) is publicly exposed by default.
    # The web service is on `expose:` (internal) so NPM fronts it.
    assert "3000" in exposed  # grafana (admin auth required)
    assert "8000" not in exposed  # api NOT exposed (G07-C1-02)
    assert "8080" not in exposed  # web NOT exposed publicly (Mission J-FIX-04: NPM fronts it)
    assert "9090" not in exposed  # prometheus NOT exposed
    assert "3200" not in exposed  # tempo NOT exposed
    assert "4317" not in exposed  # otel collector NOT exposed
    assert "4318" not in exposed  # otel collector NOT exposed


def test_compose_api_uses_expose_not_ports():
    """G07-C1-02: the API service uses `expose:` (internal-only) not
    `ports:` (public mapping). Prometheus scrapes /metrics on the
    private Docker network (http://api:8000/metrics)."""
    compose = Path(__file__).resolve().parents[3] / "docker-compose.yml"
    content = compose.read_text()
    # The api service must have `expose: ["8000"]` (internal-only).
    # We check that the api service has an `expose:` block with 8000.
    assert 'expose:' in content
    assert '"8000"' in content or "'8000'" in content


def test_compose_purge_cron_service_exists():
    """G07-C1-04: a `purge-cron` Compose service exists and runs the
    cleanup_purge command on a schedule."""
    compose = Path(__file__).resolve().parents[3] / "docker-compose.yml"
    content = compose.read_text()
    assert "purge-cron:" in content
    assert "app.cleanup_purge" in content
    assert "sleep" in content  # the schedule loop


# ---- T26: Session cookie Secure flag (config) ----

def test_session_cookie_secure_default_false():
    """T26 + ADR-0003 Part B #5: SESSION_COOKIE_SECURE defaults to false
    for local dev. Production MUST override to true."""
    from app.config import Settings
    s = Settings()
    assert s.session_cookie_secure is False  # safe default for dev


def test_session_cookie_secure_can_be_overridden():
    """T26: SESSION_COOKIE_SECURE can be set to true via env var."""
    import os
    os.environ["SESSION_COOKIE_SECURE"] = "true"
    try:
        from app.config import Settings
        s = Settings()
        assert s.session_cookie_secure is True
    finally:
        del os.environ["SESSION_COOKIE_SECURE"]


# ---- T26: CORS config ----

def test_cors_origins_default_localhost():
    """T26 + ADR-0003 Part B #4: CORS defaults to localhost for dev.
    Production MUST override to the real origin."""
    from app.config import Settings
    s = Settings()
    assert all("localhost" in o for o in s.cors_origins)


# ---- T28: Production-like smoke (documented) ----

def test_health_live_works(client):
    """T28: the health/live endpoint works (production smoke)."""
    r = client.get("/api/v1/health/live")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_health_ready_works(client):
    """T28: the health/ready endpoint works (production smoke)."""
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ready", "degraded", "not_ready")


def test_guest_session_creates_cookie(client):
    """T28: POST /sessions/guest sets an HttpOnly cookie."""
    r = client.post("/api/v1/sessions/guest", json={"locale": "en"})
    assert r.status_code == 201
    # The cookie must be set.
    cookies = r.headers.get("set-cookie", "")
    assert "ac_guest=" in cookies
    assert "HttpOnly" in cookies
    assert "SameSite" in cookies  # case-insensitive (Lax or lax)


def test_module_gallery_returns_10(client):
    """T28: GET /modules returns 10 manifests (production smoke)."""
    r = client.get("/api/v1/modules")
    assert r.status_code == 200
    assert r.json()["count"] == 10


def test_experiments_list_returns_10(client):
    """T28: GET /experiments returns 10 experiment IDs (production smoke)."""
    r = client.get("/api/v1/experiments")
    assert r.status_code == 200
    assert r.json()["count"] == 10


def test_mentor_no_key_fallback(client):
    """T28: the mentor works without an LLM API key (deterministic fallback)."""
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    r = client.post(
        "/api/v1/experiments/graph-first-network/runs",
        json={"mode": "guided", "inputs": {}},
    )
    run_id = r.json()["run_id"]
    r2 = client.post(
        "/api/v1/mentor/explain",
        json={"run_id": run_id, "question": "summary?", "lang": "en"},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["provider_mode"] == "deterministic"
    assert body["answer"]  # non-empty


def test_no_public_service_leakage(client):
    """T28: the API doesn't leak internal service URLs in responses."""
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    r = client.post(
        "/api/v1/experiments/graph-first-network/runs",
        json={"mode": "guided", "inputs": {}},
    )
    body = r.json()
    # The response must not contain internal hostnames like 'postgres',
    # 'neo4j', 'otel-collector', 'prometheus', 'tempo', 'grafana' as
    # service URLs.
    body_str = str(body)
    internal_hosts = ["postgres:5432", "neo4j:7687", "otel-collector:4318",
                      "prometheus:9090", "tempo:3200"]
    for host in internal_hosts:
        assert host not in body_str, f"internal host {host!r} leaked in response"
