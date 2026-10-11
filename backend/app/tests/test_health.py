"""Health endpoint tests — A01 gate: health passes on clean checkout."""
from __future__ import annotations


def test_live_ok(client):
    r = client.get("/api/v1/health/live")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "app" in body and isinstance(body["app"], str)


def test_ready_includes_database(client):
    r = client.get("/api/v1/health/ready")
    # In-memory SQLite should be `up` → overall `ready` → 200.
    assert r.status_code in (200, 503)
    body = r.json()
    assert "database" in body["services"]
    db = body["services"]["database"]
    # The SQLite in-memory probe must succeed in the test env.
    assert db["state"] == "up"
    assert body["status"] in ("ready", "degraded")


def test_request_id_echoed(client):
    rid = "test-rid-12345"
    r = client.get("/api/v1/health/live", headers={"x-request-id": rid})
    assert r.headers.get("x-request-id") == rid


def test_request_id_minted_when_missing(client):
    r = client.get("/api/v1/health/live")
    rid = r.headers.get("x-request-id")
    assert rid is not None and len(rid) > 0
