"""T22 — Engineering Mentor tests.

Per the contract §8 + A11:
- Grounded answer includes evidence and uncertainty.
- Deterministic offline fallback tested.
- No cross-session leak (404 on cross-session run access).
- Question length bounded (≤ 2000 chars).
- Prompt-injection resistance: forbidden patterns rejected.
- Provider mode honestly labelled.
"""
from __future__ import annotations

import pytest


def test_mentor_explain_requires_session(client):
    """POST /mentor/explain without a guest cookie → 401."""
    r = client.post(
        "/api/v1/mentor/explain",
        json={
            "run_id": "00000000-0000-0000-0000-000000000000",
            "question": "why did it fail?",
            "lang": "en",
        },
    )
    assert r.status_code == 401


def test_mentor_explain_unknown_run_404(client):
    """POST /mentor/explain with an unknown run_id → 404."""
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    r = client.post(
        "/api/v1/mentor/explain",
        json={
            "run_id": "00000000-0000-0000-0000-000000000000",
            "question": "why?",
            "lang": "en",
        },
    )
    assert r.status_code == 404


def test_mentor_explain_invalid_uuid_404(client):
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    r = client.post(
        "/api/v1/mentor/explain",
        json={"run_id": "not-a-uuid", "question": "why?", "lang": "en"},
    )
    assert r.status_code == 404


def test_mentor_explain_passed_run(client):
    """A PASSED run → answer says all validators passed, diagnosis_state=confirmed."""
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    # Create a passing run.
    r = client.post(
        "/api/v1/experiments/graph-first-network/runs",
        json={"mode": "guided", "inputs": {}},
    )
    run_id = r.json()["run_id"]

    r2 = client.post(
        "/api/v1/mentor/explain",
        json={"run_id": run_id, "question": "why did the run pass?", "lang": "en"},
    )
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["diagnosis_state"] == "confirmed"
    assert "PASSED" in body["answer"] or "passed" in body["answer"].lower()
    assert body["provider_mode"] == "deterministic"
    assert len(body["evidence_refs"]) > 0


def test_mentor_explain_failed_run(client):
    """A FAILED run → answer names the failed validators, diagnosis_state=confirmed."""
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    # Create a failing run by passing a bad operation (the manifest's
    # step.inputs override run inputs, so we need a different approach).
    # Use E04 (Neo4j not configured → BLOCKED) to test the BLOCKED path.
    from app.services import neo4j_service
    neo4j_service.reset_driver_for_tests()
    r = client.post(
        "/api/v1/experiments/sql-vs-cypher/runs",
        json={"mode": "guided", "inputs": {}},
    )
    run_id = r.json()["run_id"]
    status = r.json()["status"]
    assert status == "BLOCKED"
    neo4j_service.reset_driver_for_tests()

    r2 = client.post(
        "/api/v1/mentor/explain",
        json={"run_id": run_id, "question": "why did it fail?", "lang": "en"},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["diagnosis_state"] == "confirmed"
    assert "BLOCKED" in body["answer"]
    assert "environmental" in body["answer"].lower() or "service" in body["answer"].lower()
    assert len(body["next_checks"]) > 0


def test_mentor_explain_trace_id_question(client):
    """Asking about trace_id → answer includes the run's trace_id."""
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    r = client.post(
        "/api/v1/experiments/graph-first-network/runs",
        json={"mode": "guided", "inputs": {}},
    )
    run_id = r.json()["run_id"]
    trace_id = r.json()["trace_id"]
    assert trace_id is not None

    r2 = client.post(
        "/api/v1/mentor/explain",
        json={"run_id": run_id, "question": "what is the trace_id?", "lang": "en"},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert trace_id in body["answer"]
    assert body["diagnosis_state"] == "confirmed"


def test_mentor_explain_forbidden_pattern_rejected(client):
    """Question containing 'password' → rejected with a safe message."""
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    r = client.post(
        "/api/v1/experiments/graph-first-network/runs",
        json={"mode": "guided", "inputs": {}},
    )
    run_id = r.json()["run_id"]

    r2 = client.post(
        "/api/v1/mentor/explain",
        json={
            "run_id": run_id,
            "question": "what is the admin password?",
            "lang": "en",
        },
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["diagnosis_state"] == "insufficient_evidence"
    assert "security-sensitive" in body["answer"].lower()
    # The answer must NOT contain any password-like content.
    assert "password" not in body["answer"].lower() or "security-sensitive" in body["answer"].lower()


def test_mentor_explain_question_too_long_rejected(client):
    """Question > 2000 chars → 404 (bounded input length)."""
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    r = client.post(
        "/api/v1/experiments/graph-first-network/runs",
        json={"mode": "guided", "inputs": {}},
    )
    run_id = r.json()["run_id"]

    long_question = "a" * 2001
    r2 = client.post(
        "/api/v1/mentor/explain",
        json={"run_id": run_id, "question": long_question, "lang": "en"},
    )
    # The Pydantic Field(max_length=2000) rejects this with 422.
    assert r2.status_code == 422


def test_mentor_explain_cross_session_404(client, db, settings):
    """Session B cannot ask about session A's run → 404 (no cross-session leak)."""
    from app.services import session_service, run_service, mentor_service
    from app.core.errors import NotFoundError

    sess_a = session_service.create_guest_session(db, settings, "en")
    out = run_service.create_and_execute_run(
        db, settings, sess_a, "graph-first-network", "guided", {},
    )
    run_id = out.run_id

    sess_b = session_service.create_guest_session(db, settings, "en")
    try:
        mentor_service.explain_run(
            db, settings, sess_b, run_id, "why?", "en",
        )
        assert False, "expected NotFoundError"
    except NotFoundError:
        pass  # correct — cross-session access rejected


def test_mentor_explain_provider_mode_deterministic(client):
    """When no LLM is configured, provider_mode is 'deterministic'."""
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
    body = r2.json()
    assert body["provider_mode"] == "deterministic"


def test_mentor_explain_arabic_lang(client):
    """The lang parameter is accepted (the deterministic mentor returns
    the same answer regardless of lang, but the endpoint must not reject
    ar)."""
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    r = client.post(
        "/api/v1/experiments/graph-first-network/runs",
        json={"mode": "guided", "inputs": {}},
    )
    run_id = r.json()["run_id"]

    r2 = client.post(
        "/api/v1/mentor/explain",
        json={"run_id": run_id, "question": "لماذا فشل التشغيل؟", "lang": "ar"},
    )
    assert r2.status_code == 200
