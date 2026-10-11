"""T18 — Run lifecycle tests.

Per the architecture contract §5 + §4:
- Run state machine: CREATED → RUNNING → PASSED|FAILED|BLOCKED; terminal
  states immutable.
- A rerun creates a new run row.
- Reset recreates a clean fixture snapshot without mutating the prior run.
- All session read/writes scoped server-side; cross-session access → 404.
- POST /experiments/{id}/runs returns {run_id, status, trace_id}.
- GET /runs/{id} returns bounded run state.
- GET /runs?experiment_id=&limit= paginated.
- POST /runs/{id}/reset recreates fixture; does not mutate terminal run.
- GET /runs/{id}/export?format=md|json.
- POST /runs/compare.

Per ADR-0003 step 1: trace_id is captured from the active OTEL span at
run creation.
"""
from __future__ import annotations

import uuid

import pytest

from app.core.errors import NotFoundError


# ---- POST /api/v1/experiments/{id}/runs ----

def test_create_run_e01_passes_via_api(client):
    """POST /experiments/graph-first-network/runs with the right inputs
    produces a PASSED run with a populated trace_id."""
    # Create a guest session.
    r = client.post("/api/v1/sessions/guest", json={"locale": "en"})
    assert r.status_code == 201

    r = client.post(
        "/api/v1/experiments/graph-first-network/runs",
        json={
            "mode": "guided",
            "inputs": {
                "dataset_id": "e01-test",
                "fixture_key": "starter-five-v1",
            },
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "PASSED"
    assert body["trace_id"] is not None  # ADR-0003 step 1
    assert body["error_code"] is None
    assert len(body["step_verdicts"]) == 3  # E01 has 3 steps
    for v in body["step_verdicts"]:
        assert v["validator_passed"] is True


def test_create_run_e01_fails_with_bad_fixture(client):
    """POST /experiments/graph-first-network/runs with a bad fixture key
    produces a FAILED run (honest negative)."""
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    r = client.post(
        "/api/v1/experiments/graph-first-network/runs",
        json={
            "mode": "guided",
            "inputs": {
                "dataset_id": "e01-bad",
                "fixture_key": "does-not-exist",
            },
        },
    )
    assert r.status_code == 200
    body = r.json()
    # The seed operation fails → the validator fails → run status = FAILED.
    assert body["status"] == "FAILED"


def test_create_run_unknown_experiment_returns_404(client):
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    r = client.post(
        "/api/v1/experiments/does-not-exist/runs",
        json={"mode": "guided", "inputs": {}},
    )
    assert r.status_code == 404


def test_create_run_requires_session(client):
    """POST /experiments/.../runs without a guest cookie → 401."""
    r = client.post(
        "/api/v1/experiments/graph-first-network/runs",
        json={"mode": "guided", "inputs": {}},
    )
    assert r.status_code == 401


def test_create_run_invalid_mode_rejected(client):
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    r = client.post(
        "/api/v1/experiments/graph-first-network/runs",
        json={"mode": "invalid-mode", "inputs": {}},
    )
    assert r.status_code == 422


# ---- GET /api/v1/runs/{id} ----

def test_get_run_returns_run_state(client):
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    r = client.post(
        "/api/v1/experiments/graph-first-network/runs",
        json={"mode": "guided", "inputs": {
            "dataset_id": "e01-get",
            "fixture_key": "starter-five-v1",
        }},
    )
    run_id = r.json()["run_id"]

    r2 = client.get(f"/api/v1/runs/{run_id}")
    assert r2.status_code == 200
    body = r2.json()
    assert body["run_id"] == run_id
    assert body["status"] == "PASSED"
    assert body["experiment_id"] == "graph-first-network"
    assert body["trace_id"] is not None


def test_get_run_with_invalid_uuid_returns_404(client):
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    r = client.get("/api/v1/runs/not-a-uuid")
    assert r.status_code == 404


def test_get_run_unknown_returns_404(client):
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    r = client.get(
        "/api/v1/runs/00000000-0000-0000-0000-000000000000"
    )
    assert r.status_code == 404


# ---- GET /api/v1/runs ----

def test_list_runs_returns_session_scoped_history(client):
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    # Create two runs.
    for ds in ["e01-list-1", "e01-list-2"]:
        client.post(
            "/api/v1/experiments/graph-first-network/runs",
            json={"mode": "guided", "inputs": {
                "dataset_id": ds,
                "fixture_key": "starter-five-v1",
            }},
        )
    r = client.get("/api/v1/runs")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 2
    assert all("run_id" in run for run in body["runs"])


def test_list_runs_filter_by_experiment(client):
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    # Create a run for E01.
    client.post(
        "/api/v1/experiments/graph-first-network/runs",
        json={"mode": "guided", "inputs": {
            "dataset_id": "e01-filter",
            "fixture_key": "starter-five-v1",
        }},
    )
    r = client.get("/api/v1/runs?experiment_id=graph-first-network")
    assert r.status_code == 200
    body = r.json()
    assert all(run["experiment_id"] == "graph-first-network" for run in body["runs"])


# ---- POST /api/v1/runs/{id}/reset ----

def test_reset_run_deletes_graph_data(client):
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    r = client.post(
        "/api/v1/experiments/graph-first-network/runs",
        json={"mode": "guided", "inputs": {
            "dataset_id": "e01-reset",
            "fixture_key": "starter-five-v1",
        }},
    )
    run_id = r.json()["run_id"]

    r2 = client.post(f"/api/v1/runs/{run_id}/reset")
    assert r2.status_code == 200
    body = r2.json()
    assert body["deleted_nodes"] == 5
    assert body["deleted_edges"] == 4
    assert body["dataset_id"] == "e01-reset"

    # The original run record is NOT mutated (terminal immutability).
    r3 = client.get(f"/api/v1/runs/{run_id}")
    assert r3.status_code == 200
    assert r3.json()["status"] == "PASSED"  # unchanged


# ---- GET /api/v1/runs/{id}/export ----

def test_export_run_markdown(client):
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    r = client.post(
        "/api/v1/experiments/graph-first-network/runs",
        json={"mode": "guided", "inputs": {
            "dataset_id": "e01-export",
            "fixture_key": "starter-five-v1",
        }},
    )
    run_id = r.json()["run_id"]
    r2 = client.get(f"/api/v1/runs/{run_id}/export?format=md")
    assert r2.status_code == 200
    body = r2.json()
    assert body["format"] == "md"
    assert "Run Report" in body["report"]
    assert "graph-first-network" in body["report"]
    assert "[PASS]" in body["report"]


def test_export_run_json(client):
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    r = client.post(
        "/api/v1/experiments/graph-first-network/runs",
        json={"mode": "guided", "inputs": {
            "dataset_id": "e01-export-json",
            "fixture_key": "starter-five-v1",
        }},
    )
    run_id = r.json()["run_id"]
    r2 = client.get(f"/api/v1/runs/{run_id}/export?format=json")
    assert r2.status_code == 200
    body = r2.json()
    assert body["format"] == "json"
    report = body["report"]
    assert report["experiment_id"] == "graph-first-network"
    assert report["status"] == "PASSED"
    assert report["trace_id"] is not None
    assert "step_verdicts" in report
    assert "provenance" in report
    assert "manifest_digest" in report["provenance"]


def test_export_run_invalid_format_rejected(client):
    """The service-layer export_run rejects an invalid format with
    InvalidStateError (the API param uses Literal so FastAPI also rejects)."""
    from app.services import run_service
    from app.core.errors import InvalidStateError
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    r = client.post(
        "/api/v1/experiments/graph-first-network/runs",
        json={"mode": "guided", "inputs": {
            "dataset_id": "e01-export-bad",
            "fixture_key": "starter-five-v1",
        }},
    )
    run_id = r.json()["run_id"]
    # Service-level: InvalidStateError.
    import uuid as _uuid
    from app.db.session import SessionLocal
    from app.services import session_service
    db = SessionLocal()
    try:
        from app.config import get_settings
        sess = session_service.create_guest_session(db, get_settings(), "en")
        with pytest.raises(InvalidStateError):
            run_service.export_run(db, sess, _uuid.UUID(run_id), "xml")
    finally:
        db.close()
    # API-level: FastAPI's Literal validation rejects unknown values with 422.
    r2 = client.get(f"/api/v1/runs/{run_id}/export?format=xml")
    assert r2.status_code == 422


# ---- POST /api/v1/runs/compare ----

def test_compare_two_runs_same_experiment(client):
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    # Two runs of the same experiment.
    r1 = client.post(
        "/api/v1/experiments/graph-first-network/runs",
        json={"mode": "guided", "inputs": {
            "dataset_id": "e01-cmp-1",
            "fixture_key": "starter-five-v1",
        }},
    )
    r2 = client.post(
        "/api/v1/experiments/graph-first-network/runs",
        json={"mode": "guided", "inputs": {
            "dataset_id": "e01-cmp-2",
            "fixture_key": "starter-five-v1",
        }},
    )
    a_id = r1.json()["run_id"]
    b_id = r2.json()["run_id"]

    r3 = client.post(
        "/api/v1/runs/compare",
        json={"run_a_id": a_id, "run_b_id": b_id},
    )
    assert r3.status_code == 200
    body = r3.json()
    assert body["same_experiment"] is True
    assert body["same_final_status"] is True
    assert body["same_step_count"] is True
    assert all(d["same_verdict"] for d in body["step_diffs"])


def test_compare_run_to_itself(client):
    """Comparing a run to itself returns same_experiment=True etc."""
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    r1 = client.post(
        "/api/v1/experiments/graph-first-network/runs",
        json={"mode": "guided", "inputs": {
            "dataset_id": "e01-cmp-self",
            "fixture_key": "starter-five-v1",
        }},
    )
    rid = r1.json()["run_id"]
    r2 = client.post(
        "/api/v1/runs/compare",
        json={"run_a_id": rid, "run_b_id": rid},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["same_experiment"] is True
    assert body["same_final_status"] is True


def test_compare_invalid_run_id_rejected(client):
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    r = client.post(
        "/api/v1/runs/compare",
        json={"run_a_id": "not-a-uuid", "run_b_id": "also-not-a-uuid"},
    )
    assert r.status_code == 404


# ---- Cross-session isolation (A08) ----

def test_cross_session_get_run_rejected(client, db, settings):
    """G05 (A08): session B cannot read session A's run via GET /runs/{id}."""
    from app.services import session_service, run_service

    sess_a = session_service.create_guest_session(db, settings, "en")
    outcome = run_service.create_and_execute_run(
        db, settings, sess_a, "graph-first-network", "guided",
        {"dataset_id": "e01-cross", "fixture_key": "starter-five-v1"},
    )
    run_id = outcome.run_id

    sess_b = session_service.create_guest_session(db, settings, "en")
    with pytest.raises(NotFoundError):
        run_service.get_run(db, sess_b, run_id)


# ---- ADR-0003 step 1: trace_id is populated at run creation ----

def test_run_record_has_populated_trace_id(client, db, settings):
    """The trace_id column on the runs table must be populated from the
    active OTEL span at run creation (ADR-0003 step 1).
    """
    from app.services import session_service, run_service
    from app.models.run import Run
    from sqlalchemy import select

    sess = session_service.create_guest_session(db, settings, "en")
    outcome = run_service.create_and_execute_run(
        db, settings, sess, "graph-first-network", "guided",
        {"dataset_id": "e01-trace", "fixture_key": "starter-five-v1"},
    )
    # Read the run row from the DB and assert the trace_id column is set.
    row = db.execute(select(Run).where(Run.id == outcome.run_id)).scalar_one()
    assert row.trace_id is not None
    assert len(row.trace_id) == 32  # OTel trace_id is 128-bit hex (32 chars)
    assert all(c in "0123456789abcdef" for c in row.trace_id)


# ---- ADR-0003 step 2: /observability/links/{run_id} reads trace_id from DB ----

def test_observability_links_reads_trace_id_from_db(client):
    """The /observability/links endpoint now reads the trace_id from the
    persisted run record (was null in G04)."""
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    r = client.post(
        "/api/v1/experiments/graph-first-network/runs",
        json={"mode": "guided", "inputs": {
            "dataset_id": "e01-links",
            "fixture_key": "starter-five-v1",
        }},
    )
    assert r.status_code == 200
    run_id = r.json()["run_id"]
    trace_id_from_run = r.json()["trace_id"]
    assert trace_id_from_run is not None

    r2 = client.get(f"/api/v1/observability/links/{run_id}")
    assert r2.status_code == 200
    body = r2.json()
    # The /links endpoint must return the same trace_id as the run record.
    assert body["trace_id"] == trace_id_from_run


# ---- Terminal immutability ----

def test_terminal_run_status_not_mutated_by_reset(client, db, settings):
    """A reset does NOT mutate the prior terminal run's status. The
    original run record remains unchanged (terminal immutability per §5)."""
    from app.services import session_service, run_service
    from app.models.run import Run
    from sqlalchemy import select

    sess = session_service.create_guest_session(db, settings, "en")
    outcome = run_service.create_and_execute_run(
        db, settings, sess, "graph-first-network", "guided",
        {"dataset_id": "e01-imm", "fixture_key": "starter-five-v1"},
    )
    assert outcome.status == "PASSED"

    # Reset the run.
    run_service.reset_run(db, settings, sess, outcome.run_id)

    # The original run record's status must still be PASSED.
    row = db.execute(select(Run).where(Run.id == outcome.run_id)).scalar_one()
    assert row.status == "PASSED"


# ---- Rerun creates a new run row ----

def test_rerun_creates_new_run_row(client, db, settings):
    """A rerun creates a new run row (does not mutate the prior run)."""
    from app.services import session_service, run_service
    from app.models.run import Run
    from sqlalchemy import select

    sess = session_service.create_guest_session(db, settings, "en")
    out1 = run_service.create_and_execute_run(
        db, settings, sess, "graph-first-network", "guided",
        {"dataset_id": "e01-rerun-1", "fixture_key": "starter-five-v1"},
    )
    out2 = run_service.create_and_execute_run(
        db, settings, sess, "graph-first-network", "guided",
        {"dataset_id": "e01-rerun-2", "fixture_key": "starter-five-v1"},
    )
    assert out1.run_id != out2.run_id
    # Both runs must be in the DB.
    rows = db.execute(
        select(Run).where(Run.session_id == sess.id)
    ).scalars().all()
    run_ids = {r.id for r in rows}
    assert out1.run_id in run_ids
    assert out2.run_id in run_ids


# ---- Inputs redaction ----

def test_run_inputs_redact_secrets(client, db, settings):
    """Inputs with secret-like keys are redacted before storage."""
    from app.services import session_service, run_service
    from app.models.run import Run
    from sqlalchemy import select

    sess = session_service.create_guest_session(db, settings, "en")
    out = run_service.create_and_execute_run(
        db, settings, sess, "graph-first-network", "guided",
        {
            "dataset_id": "e01-redact",
            "fixture_key": "starter-five-v1",
            "api_token": "super-secret-value",
            "password": "should-not-be-stored",
        },
    )
    row = db.execute(select(Run).where(Run.id == out.run_id)).scalar_one()
    assert row.inputs_json["api_token"] == "[REDACTED]"
    assert row.inputs_json["password"] == "[REDACTED]"
    assert row.inputs_json["dataset_id"] == "e01-redact"  # not redacted
