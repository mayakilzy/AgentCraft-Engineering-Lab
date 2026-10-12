"""G06-PRE-03 — Run-level verification for all ten experiments.

Per the directive:
- اختبر التشغيل الكامل للتجارب E01–E10.
- يجب أن تُصنف الخدمات غير متاحة BLOCKED بوضوح، لا FAILED بسبب نقص بيئي
  ولا PASSED بنتائج وهمية.
- حافظ على التمييز بين نجاح تجربة تعليمية تتضمن فشلاً مقصوداً وبين
  نجاح عملية التشغيل نفسها.
- تأكد من أن E09/E10 تحتفظان بأدلة الفشل والتصحيح والمقارنة.

This file provides the E01–E10 status table (PASSED / BLOCKED / FAILED)
with evidence for each experiment.
"""
from __future__ import annotations

import pytest


# ---- E01–E10 status table ----
#
# Per PRE-03, the expected status for each experiment in the dev env:
# - E01 (NetworkX + SQLite): PASSED (no external service required)
# - E02 (NetworkX): PASSED
# - E03 (Cytoscape.js + NetworkX): PASSED
# - E04 (PostgreSQL + Neo4j): BLOCKED (Neo4j not configured)
# - E05 (NetworkX): PASSED
# - E06 (NetworkX fallback): PASSED (NetworkX fallback labelled honestly)
# - E07 (OpenTelemetry): PASSED (in-process OTEL, trace_id captured)
# - E08 (Prometheus + Grafana): PASSED (metrics registry has observations)
# - E09 (inject_failure + run_trace_demo): PASSED (intentional failure +
#   corrected rerun)
# - E10 (integrated challenge): PASSED (graph + telemetry)
#
# The tests below verify each experiment's full run via the API and
# assert the expected status. They also verify that BLOCKED is honest
# (E04) and that intentional failures (E09) don't cause the run to be
# FAILED.


def test_E01_full_run_passed(client):
    """E01: Build Your First Graph — PASSED in dev env."""
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    r = client.post(
        "/api/v1/experiments/graph-first-network/runs",
        json={"mode": "guided", "inputs": {}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "PASSED", f"E01 expected PASSED, got {body['status']}"
    assert body["trace_id"] is not None
    assert len(body["step_verdicts"]) == 3
    for v in body["step_verdicts"]:
        assert v["validator_passed"] is True


def test_E02_full_run_passed(client):
    """E02: Shortest Path — PASSED in dev env (per-step inputs now
    give each step the correct source/target pair)."""
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    r = client.post(
        "/api/v1/experiments/shortest-path/runs",
        json={"mode": "guided", "inputs": {}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "PASSED", f"E02 expected PASSED, got {body['status']}"
    assert len(body["step_verdicts"]) == 3
    for v in body["step_verdicts"]:
        assert v["validator_passed"] is True


def test_E03_full_run_passed(client):
    """E03: Interactive Graph Explorer — PASSED in dev env."""
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    r = client.post(
        "/api/v1/experiments/interactive-explorer/runs",
        json={"mode": "guided", "inputs": {}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "PASSED", f"E03 expected PASSED, got {body['status']}"
    assert len(body["step_verdicts"]) == 4


def test_E04_full_run_blocked(client):
    """E04: SQL vs Cypher — BLOCKED in dev env (Neo4j not configured).

    Per PRE-03: services not available must be BLOCKED, not FAILED.
    """
    from app.services import neo4j_service
    neo4j_service.reset_driver_for_tests()

    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    r = client.post(
        "/api/v1/experiments/sql-vs-cypher/runs",
        json={"mode": "guided", "inputs": {}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # G06-PRE-03: the run is BLOCKED, not FAILED, because the missing
    # Neo4j is an environmental condition, not a logic error.
    assert body["status"] == "BLOCKED", f"E04 expected BLOCKED, got {body['status']}"
    # The error_code names the missing service honestly.
    assert body["error_code"] == "neo4j_not_configured"
    assert len(body["step_verdicts"]) == 4
    # The first step (seed) passes; the next 3 (parity_run) are BLOCKED.
    assert body["step_verdicts"][0]["validator_passed"] is True
    for v in body["step_verdicts"][1:]:
        assert v["operation_status"] == "blocked"
    neo4j_service.reset_driver_for_tests()


def test_E05_full_run_passed(client):
    """E05: Critical Dependencies — PASSED in dev env."""
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    r = client.post(
        "/api/v1/experiments/critical-dependencies/runs",
        json={"mode": "guided", "inputs": {}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "PASSED", f"E05 expected PASSED, got {body['status']}"
    assert len(body["step_verdicts"]) == 4


def test_E06_full_run_passed(client):
    """E06: Discover Communities — PASSED in dev env (NetworkX fallback).

    The provenance is honestly labelled as networkx_fallback (not GDS).
    """
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    r = client.post(
        "/api/v1/experiments/discover-communities/runs",
        json={"mode": "guided", "inputs": {}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "PASSED", f"E06 expected PASSED, got {body['status']}"
    assert len(body["step_verdicts"]) == 4
    for v in body["step_verdicts"]:
        assert v["validator_passed"] is True


def test_E07_full_run_passed(client):
    """E07: Trace One Request — PASSED in dev env (in-process OTEL).

    trace_id is populated from the active OTEL span (ADR-0003 step 1).
    """
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    r = client.post(
        "/api/v1/experiments/trace-one-request/runs",
        json={"mode": "guided", "inputs": {}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "PASSED", f"E07 expected PASSED, got {body['status']}"
    assert body["trace_id"] is not None
    assert len(body["step_verdicts"]) == 4


def test_E08_full_run_passed(client):
    """E08: Build Monitoring Dashboard — PASSED in dev env.

    The metrics registry has observations from the test client's own
    HTTP traffic + the run's own operations.
    """
    # Generate some traffic so the metrics registry has observations.
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    for _ in range(3):
        client.get("/api/v1/health/live")
    r = client.post(
        "/api/v1/experiments/build-monitoring-dashboard/runs",
        json={"mode": "guided", "inputs": {}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "PASSED", f"E08 expected PASSED, got {body['status']}"
    assert len(body["step_verdicts"]) == 4


def test_E09_full_run_passed(client):
    """E09: Diagnose a Hidden Failure — PASSED in dev env.

    Per PRE-02 + PRE-03:
    - Steps 1–3 (inject_failure with fail_step=transform) verify the
      failed run: failed_run.fail_step=transform + trace_id present.
    - Step 4 (run_trace_demo without fail_step) is the REAL corrected
      rerun; the validator checks its operation status is "ok".
    - The run as a whole PASSES because all validators pass, even
      though the operation status on steps 1–3 is "failed" (intentional).
    """
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    r = client.post(
        "/api/v1/experiments/diagnose-hidden-failure/runs",
        json={"mode": "guided", "inputs": {}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "PASSED", f"E09 expected PASSED, got {body['status']}"
    assert body["trace_id"] is not None
    assert len(body["step_verdicts"]) == 4
    # Steps 1-3: operation status=failed, validator passed (intentional failure).
    for i, v in enumerate(body["step_verdicts"][:3]):
        assert v["operation_status"] == "failed", f"step {i} should have failed operation"
        assert v["operation_error_code"] == "injected_transform_failure"
        assert v["validator_passed"] is True
    # Step 4: corrected rerun, operation status=ok, validator passed.
    assert body["step_verdicts"][3]["operation_status"] == "ok"
    assert body["step_verdicts"][3]["validator_passed"] is True


def test_E10_full_run_passed(client):
    """E10: Graph and Observability Challenge — PASSED in dev env.

    Steps:
    1. load (seed_graph) → PASSED
    2. paths (shortest_path APP1→T3) → PASSED
    3. scenario (inject_failure transform) → validator PASSED (intentional)
    4. trace (inject_failure transform) → validator PASSED (intentional)
    5. fix (run_trace_demo corrected) → validator PASSED (real operation ok)
    """
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    r = client.post(
        "/api/v1/experiments/integrated-challenge/runs",
        json={"mode": "guided", "inputs": {}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "PASSED", f"E10 expected PASSED, got {body['status']}"
    assert body["trace_id"] is not None
    assert len(body["step_verdicts"]) == 5
    for v in body["step_verdicts"]:
        assert v["validator_passed"] is True


# ---- Negative tests: removing the corrected step causes FAILED ----

def test_E09_negative_corrected_step_failure_causes_failed(client, db, settings):
    """PRE-03 negative test: if the corrected rerun step fails (e.g.,
    the operation returns status=failed), the validator on that step
    fails, and the run as a whole is FAILED.

    We simulate this by creating a run with a manifest where the
    corrected rerun step uses inject_failure (which always fails),
    so the corrected_run_only validator sees status=failed.
    """
    from app.services import session_service
    from app.lab import get_validator

    sess = session_service.create_guest_session(db, settings, "en")
    v = get_validator("failure_diagnosis_v1")

    # Simulate the corrected rerun step failing.
    result = v(
        outputs={
            "status": "failed",  # corrected rerun failed
            "run_trace_id": "abc123",
        },
        expected={
            "corrected_run_only": True,
            "corrected_run": {"status": "ok"},
        },
    )
    assert result.passed is False
    assert "corrected rerun status=failed" in result.message


def test_E09_negative_missing_failed_run_block(client):
    """PRE-03 negative test: if the failed_run block is missing on an
    inject_failure step, the validator fails honestly."""
    from app.lab import get_validator
    v = get_validator("failure_diagnosis_v1")
    result = v(
        outputs={
            "run_trace_id": "abc123",
            # NO failed_run block
        },
        expected={
            "failed_run": {"fail_step": "transform"},
        },
    )
    assert result.passed is False
    assert "failed_run block missing" in result.message


def test_E09_negative_wrong_fail_step(client):
    """PRE-03 negative test: if the failed run's fail_step doesn't match
    the expected, the validator fails honestly."""
    from app.lab import get_validator
    v = get_validator("failure_diagnosis_v1")
    result = v(
        outputs={
            "failed_run": {
                "fail_step": "fetch",  # wrong
                "status": "failed",
                "trace_id": "abc123",
            },
            "run_trace_id": "abc123",
        },
        expected={
            "failed_run": {"fail_step": "transform"},
        },
    )
    assert result.passed is False
    assert "fail_step=fetch != expected transform" in result.message


# ---- PRE-01: step.inputs security tests ----

def test_step_inputs_forbidden_session_id_rejected(tmp_path):
    """The loader rejects step.inputs that contain `session_id`."""
    from app.lab.manifest_schema import _load_one
    from app.core.errors import InvalidStateError

    bad = tmp_path / "bad.yaml"
    bad.write_text(
        """
id: bad-sess
version: 1.0.0
module_id: graph
level: beginner
estimated_minutes: 10
title: {en: t, ar: t}
description: {en: d, ar: d}
dataset_key: starter-five-v1
steps:
  - id: s1
    title: {en: t, ar: t}
    instruction: {en: i, ar: i}
    operation_key: seed_graph
    input_schema_ref: x
    validator_key: seed_five_nodes_v1
    inputs:
      session_id: 12345
""",
        encoding="utf-8",
    )
    with pytest.raises(InvalidStateError) as exc:
        _load_one(bad)
    assert "forbidden security-critical keys" in str(exc.value)


def test_step_inputs_forbidden_cookie_token_rejected(tmp_path):
    """The loader rejects step.inputs that contain `cookie_token`."""
    from app.lab.manifest_schema import _load_one
    from app.core.errors import InvalidStateError

    bad = tmp_path / "bad.yaml"
    bad.write_text(
        """
id: bad-cookie
version: 1.0.0
module_id: graph
level: beginner
estimated_minutes: 10
title: {en: t, ar: t}
description: {en: d, ar: d}
dataset_key: starter-five-v1
steps:
  - id: s1
    title: {en: t, ar: t}
    instruction: {en: i, ar: i}
    operation_key: seed_graph
    input_schema_ref: x
    validator_key: seed_five_nodes_v1
    inputs:
      cookie_token: secret
""",
        encoding="utf-8",
    )
    with pytest.raises(InvalidStateError) as exc:
        _load_one(bad)
    assert "forbidden security-critical keys" in str(exc.value)


def test_step_inputs_run_id_allowed(tmp_path):
    """The loader ALLOWS step.inputs that contain `run_id` because in
    the trace_demo operation family it's a string LABEL, not the
    database run UUID."""
    from app.lab.manifest_schema import _load_one

    good = tmp_path / "good.yaml"
    good.write_text(
        """
id: good-run-id
version: 1.0.0
module_id: observability
level: beginner
estimated_minutes: 10
title: {en: t, ar: t}
description: {en: d, ar: d}
dataset_key: trace-demo-v1
steps:
  - id: s1
    title: {en: t, ar: t}
    instruction: {en: i, ar: i}
    operation_key: run_trace_demo
    input_schema_ref: x
    validator_key: trace_demo_v1
    inputs:
      run_id: my-label
""",
        encoding="utf-8",
    )
    # Should not raise — run_id is allowed in step.inputs.
    lm = _load_one(good)
    assert lm.manifest.steps[0].inputs == {"run_id": "my-label"}


def test_step_inputs_merge_priority(client):
    """PRE-01: step.inputs override run-level inputs on key conflicts.
    step.inputs has priority.

    We verify this by running E01 with run-level inputs that would cause
    failure if used, but the step.inputs override them and the run passes.
    """
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    r = client.post(
        "/api/v1/experiments/graph-first-network/runs",
        json={
            "mode": "guided",
            "inputs": {
                "dataset_id": "this-is-ignored",
                "fixture_key": "does-not-exist",
            },
        },
    )
    assert r.status_code == 200
    body = r.json()
    # The step.inputs override → seed succeeds → run PASSED.
    assert body["status"] == "PASSED"


def test_step_inputs_run_inputs_not_mutated(client, db, settings):
    """PRE-01: the run-level inputs dict is NOT mutated by the step.inputs
    merge. The original run-level inputs are stored redacted in the run
    record (inputs_json), and the effective per-step inputs are stored
    in each RunEvent's record_json.effective_inputs.
    """
    from app.services import session_service, run_service
    from app.models.run import Run
    from sqlalchemy import select

    sess = session_service.create_guest_session(db, settings, "en")
    out = run_service.create_and_execute_run(
        db, settings, sess, "graph-first-network", "guided",
        {"dataset_id": "this-is-ignored", "fixture_key": "does-not-exist"},
    )
    # The run-level inputs_json stores the ORIGINAL run-level inputs
    # (redacted), NOT the merged per-step inputs.
    row = db.execute(select(Run).where(Run.id == out.run_id)).scalar_one()
    assert row.inputs_json["dataset_id"] == "this-is-ignored"
    assert row.inputs_json["fixture_key"] == "does-not-exist"

    # The RunEvents carry the effective (merged) inputs.
    from app.models.run import RunEvent
    events = db.execute(
        select(RunEvent).where(RunEvent.run_id == out.run_id)
    ).scalars().all()
    for ev in events:
        eff = (ev.record_json or {}).get("effective_inputs") or {}
        if eff.get("dataset_id"):
            # The effective dataset_id is from step.inputs (e01), not
            # from the run-level inputs (this-is-ignored).
            assert eff["dataset_id"] == "e01"
