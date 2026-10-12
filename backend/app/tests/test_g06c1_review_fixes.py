"""G06-C1 reviewer fixes — tests.

Per the G06 review directive:
1. `mentor.provider_mode` must reflect the ACTUAL code path taken, not
   the CONFIGURED provider. The deterministic path is the only path;
   provider_mode must be 'deterministic' even when settings claim
   'openai' is configured.
2. The E09/E10 "recovery_demo" step runs `run_trace_demo` (operation_key
   = run_trace_demo), which is a DIFFERENT operation from the failed
   step's `inject_failure` (operation_key = inject_failure). The step
   is named "recovery_demo" (not "rerun_corrected" / "fix") and its
   instruction explicitly states this is a recovery demonstration, not
   a re-execution of the failed operation. This test proves the
   description is honest by verifying the operation_keys differ.
"""
from __future__ import annotations

import pytest


# ---- Fix #1: mentor.provider_mode always reflects the actual path ----

def test_mentor_provider_mode_deterministic_when_openai_configured(
    client, db, settings
):
    """G06-C1: provider_mode is 'deterministic' even when settings claim
    OpenAI is configured, because the actual code path is deterministic
    (no OpenAI call is wired).
    """
    from app.services import session_service, run_service, mentor_service
    from app.config import get_settings

    s = get_settings()
    original_provider = s.mentor_provider
    original_key = s.mentor_openai_api_key
    s.mentor_provider = "openai"
    s.mentor_openai_api_key = "fake-key-for-testing"

    try:
        sess = session_service.create_guest_session(db, s, "en")
        out = run_service.create_and_execute_run(
            db, s, sess, "graph-first-network", "guided", {},
        )
        answer = mentor_service.explain_run(
            db, s, sess, out.run_id, "why?", "en",
        )
        assert answer.provider_mode == "deterministic", (
            f"expected 'deterministic', got {answer.provider_mode!r}"
        )
    finally:
        s.mentor_provider = original_provider
        s.mentor_openai_api_key = original_key


def test_mentor_provider_mode_deterministic_via_api(client):
    """The API endpoint also reports 'deterministic' (the only path)."""
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
    assert r2.json()["provider_mode"] == "deterministic"


# ---- Fix #2: recovery_demo step is a DIFFERENT operation ----

def test_E09_recovery_step_uses_different_operation_than_failed_step():
    """G06-C1: the E09 recovery_demo step (operation_key=run_trace_demo)
    is a DIFFERENT operation from the failed step (operation_key=
    inject_failure). The manifest's description is honest: this is a
    recovery demonstration, NOT a re-execution of the failed operation.
    """
    from app.lab.manifest_schema import load_all_manifests

    loaded = load_all_manifests()
    by_id = {lm.manifest.id: lm for lm in loaded}
    e09 = by_id["diagnose-hidden-failure"].manifest

    # Find the failed step and the recovery step.
    failed_steps = [s for s in e09.steps if s.operation_key == "inject_failure"]
    recovery_steps = [s for s in e09.steps if s.operation_key == "run_trace_demo"]

    assert len(failed_steps) >= 1, "E09 must have at least one inject_failure step"
    assert len(recovery_steps) == 1, "E09 must have exactly one recovery step"

    # The recovery step's operation_key MUST differ from the failed step's.
    failed_op = failed_steps[0].operation_key
    recovery_op = recovery_steps[0].operation_key
    assert failed_op != recovery_op, (
        f"recovery step must use a DIFFERENT operation than the failed step; "
        f"both use {failed_op!r}"
    )
    assert recovery_op == "run_trace_demo"
    assert failed_op == "inject_failure"

    # The recovery step must be named "recovery_demo" (not "rerun_corrected").
    assert recovery_steps[0].id == "recovery_demo", (
        f"recovery step id must be 'recovery_demo', got {recovery_steps[0].id!r}"
    )

    # The instruction must mention that this is a DIFFERENT operation.
    instruction_en = recovery_steps[0].instruction.en
    assert "DIFFERENT operation" in instruction_en or "different operation" in instruction_en.lower(), (
        "recovery instruction must explicitly state it is a different operation"
    )


def test_E10_recovery_step_uses_different_operation_than_failed_step():
    """G06-C1: the E10 recovery_demo step (operation_key=run_trace_demo)
    is a DIFFERENT operation from the failed step (operation_key=
    inject_failure). Same assertion as E09.
    """
    from app.lab.manifest_schema import load_all_manifests

    loaded = load_all_manifests()
    by_id = {lm.manifest.id: lm for lm in loaded}
    e10 = by_id["integrated-challenge"].manifest

    failed_steps = [s for s in e10.steps if s.operation_key == "inject_failure"]
    recovery_steps = [s for s in e10.steps if s.operation_key == "run_trace_demo"]

    assert len(failed_steps) >= 1
    assert len(recovery_steps) == 1

    failed_op = failed_steps[0].operation_key
    recovery_op = recovery_steps[0].operation_key
    assert failed_op != recovery_op
    assert recovery_op == "run_trace_demo"
    assert failed_op == "inject_failure"

    assert recovery_steps[0].id == "recovery_demo"

    instruction_en = recovery_steps[0].instruction.en
    assert "DIFFERENT operation" in instruction_en or "different operation" in instruction_en.lower()


def test_E09_E10_descriptions_say_recovery_not_rerun():
    """G06-C1: the experiment descriptions must say 'recovery' or
    'demonstrate recovery', not 'rerun the corrected case' (which
    implies re-execution of the same operation).
    """
    from app.lab.manifest_schema import load_all_manifests

    loaded = load_all_manifests()
    by_id = {lm.manifest.id: lm for lm in loaded}

    e09_desc = by_id["diagnose-hidden-failure"].manifest.description.en.lower()
    e10_desc = by_id["integrated-challenge"].manifest.description.en.lower()

    assert "recovery" in e09_desc or "demonstrate recovery" in e09_desc, (
        f"E09 description must mention 'recovery'; got: {e09_desc!r}"
    )
    assert "recovery" in e10_desc or "demonstrate recovery" in e10_desc, (
        f"E10 description must mention 'recovery'; got: {e10_desc!r}"
    )


def test_E09_full_run_still_passes_after_rename(client):
    """G06-C1: the E09 full run still passes after the step rename to
    recovery_demo. The operation_key didn't change, only the step id
    and instruction did.
    """
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    r = client.post(
        "/api/v1/experiments/diagnose-hidden-failure/runs",
        json={"mode": "guided", "inputs": {}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "PASSED", f"E09 expected PASSED, got {body['status']}"
    # The last step must be "recovery_demo" (not "rerun_corrected").
    last_step = body["step_verdicts"][-1]
    assert last_step["step_id"] == "recovery_demo", (
        f"last step id must be 'recovery_demo', got {last_step['step_id']!r}"
    )
    assert last_step["operation_key"] == "run_trace_demo"


def test_E10_full_run_still_passes_after_rename(client):
    """G06-C1: the E10 full run still passes after the step rename to
    recovery_demo.
    """
    client.post("/api/v1/sessions/guest", json={"locale": "en"})
    r = client.post(
        "/api/v1/experiments/integrated-challenge/runs",
        json={"mode": "guided", "inputs": {}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "PASSED", f"E10 expected PASSED, got {body['status']}"
    last_step = body["step_verdicts"][-1]
    assert last_step["step_id"] == "recovery_demo"
    assert last_step["operation_key"] == "run_trace_demo"
