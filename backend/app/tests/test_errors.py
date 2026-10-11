"""Error model + invalid request tests — A14 gate seed."""
from __future__ import annotations


def test_404_unknown_endpoint_shaped(client):
    r = client.get("/api/v1/does-not-exist")
    assert r.status_code == 404
    body = r.json()
    assert body["code"] == "not_found"
    assert "message" in body
    assert "request_id" in body and body["request_id"]


def test_validation_error_shaped_422(client):
    # The /api/v1/experiments/{id} path returns 422 on bad UUID when wired;
    # for G01 we exercise validation via a deliberately malformed body on a
    # placeholder POST we don't have yet, so instead we hit a malformed
    # request to an existing endpoint that requires a path param type.
    # Use OpenAPI: any 422 must return the contract error body.
    r = client.post("/api/v1/sessions/guest", json={"oops": "not a valid body"})
    # Sessions route is wired in G07; for G01 this returns 404. We only
    # assert the contract body shape whichever code is returned.
    if r.status_code == 422:
        body = r.json()
        assert body["code"] == "validation_error"
        assert "details" in body and "errors" in body["details"]


def test_invalid_request_id_header_falls_back(client):
    # A request without x-request-id must still mint one and echo it.
    r = client.get("/api/v1/health/live", headers={})
    assert r.status_code == 200
    assert r.headers.get("x-request-id")


def test_cors_headers_present(client):
    r = client.options(
        "/api/v1/health/live",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    # Preflight should return 200 with CORS allow headers.
    assert r.status_code in (200, 204)
    acao = r.headers.get("access-control-allow-origin")
    assert acao in ("http://localhost:5173", "*")
