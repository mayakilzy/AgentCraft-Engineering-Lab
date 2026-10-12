"""Run lifecycle service — T18 (G05).

Per the architecture contract §5 + §2:
- Run state machine: CREATED → RUNNING → PASSED|FAILED|BLOCKED; terminal
  states are immutable.
- A rerun creates a new run row (does not mutate the prior run).
- Reset recreates a clean dataset snapshot without erasing reports; it
  produces an auditable reset record but does not mutate the terminal run.
- All session read/writes scoped server-side by cookie; no
  client-provided session_id is trusted.
- IDs are UUIDs (GUID, dialect-independent).

Per ADR-0003 Part A step 1 (G05): when a run is created, the handler
captures the current span's `trace_id` from the OpenTelemetry context
and stores it on the `runs.trace_id` column. This closes step 1 of the
run_id↔trace_id↔Grafana wiring plan.

The service is also the boundary the API uses for:
- listing runs (session-scoped, paginated)
- exporting a run as Markdown / JSON (with provenance + expected/actual)
- comparing two scoped runs (neutral relative comparison)
- resetting (recreating a clean fixture snapshot)
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.errors import AppError, InvalidStateError, NotFoundError, UnauthorizedError
from app.core.logging import get_logger
from app.core.telemetry import get_tracer, set_run_id_on_current_span
from app.lab.registry import (
    OperationResult,
    ValidationResult,
    get_operation,
    get_validator,
)
from app.models.experiment import Experiment
from app.models.graph import GraphEdge, GraphNode
from app.models.guest_session import GuestSession
from app.models.run import Run, RunEvent

log = get_logger(__name__)
tracer = get_tracer("agentcraft.runs")


# ---- State machine ----

TERMINAL_STATES = frozenset({"PASSED", "FAILED", "BLOCKED"})
INITIAL_STATE = "CREATED"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _capture_trace_id() -> Optional[str]:
    """Capture the current OTEL span's trace_id. Returns None when OTEL
    is not configured or the span is invalid (graceful degradation).

    Per ADR-0003 step 1 (G05): the run record's trace_id column is
    populated from the active span context at run creation time.
    """
    try:
        from opentelemetry import trace
        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx and ctx.is_valid:
            return format(ctx.trace_id, "032x")
    except Exception:
        pass
    return None


# ---- Run creation + execution ----

@dataclass
class RunOutcome:
    """Result of executing a run end-to-end. Returned to the API."""
    run_id: uuid.UUID
    status: str
    trace_id: Optional[str]
    error_code: Optional[str]
    step_verdicts: List[Dict[str, Any]] = field(default_factory=list)
    outputs: Dict[str, Any] = field(default_factory=dict)


def create_and_execute_run(
    db: Session,
    settings: Settings,
    session: GuestSession,
    experiment_id: str,
    mode: str,
    inputs: Dict[str, Any],
) -> RunOutcome:
    """Create a Run row, capture the trace_id, then execute each step
    in the manifest against the operation handler + validator. The
    final run status is one of PASSED, FAILED, BLOCKED.

    The run is persisted with all step verdicts so the export + mentor
    can read the diagnostic evidence later.

    Per ADR-0003 step 1: trace_id is captured from the current OTEL span.
    The whole run is wrapped in a tracer span named "lab.run" so the
    run_id is attached to every nested operation span.

    G06-PRE-01: each step may declare its own `inputs` block in the
    manifest. The runner merges them on top of the run-level inputs
    (step-level wins) before invoking the operation handler. This lets
    a multi-step experiment use the same operation with different
    parameters (e.g., E02's shortest_path with two different source/
    target pairs) without requiring the API caller to know the manifest.

    G06-PRE-02: the previous `_wrap_inject_failure_outputs` helper
    fabricated a `corrected_run.status="ok"` placeholder whenever an
    `inject_failure` operation was invoked. This was dishonest — the
    corrected rerun never actually ran. We now execute the corrected
    step as a real operation (the manifest's "rerun" step uses
    `run_trace_demo` with no `fail_step` input) and the validator reads
    the actual operation outputs. The `inject_failure` validator now
    sees the failed step's outputs directly (failed_step + status +
    trace_id) without a wrapper.
    """
    if mode not in ("guided", "challenge"):
        raise InvalidStateError(
            "mode must be one of guided|challenge",
            details={"mode": mode},
        )

    # Look up the manifest. The manifest is required to have been
    # persisted to the experiments table at boot time.
    exp = _get_experiment(db, experiment_id)
    if exp is None:
        raise NotFoundError(
            f"experiment not found: {experiment_id}",
            details={"experiment_id": experiment_id},
        )

    manifest = _decode_manifest(exp)
    run_id = uuid.uuid4()

    # Capture the trace_id from the current OTEL span (ADR-0003 step 1).
    # The run is wrapped in a "lab.run" span so the trace_id is shared
    # with all nested operation spans.
    with tracer.start_as_current_span("lab.run") as run_span:
        set_run_id_on_current_span(str(run_id))
        run_span.set_attribute("agentcraft.run_id", str(run_id))
        run_span.set_attribute("agentcraft.experiment_id", experiment_id)
        run_span.set_attribute("agentcraft.mode", mode)
        trace_id = _capture_trace_id()

        run = Run(
            id=run_id,
            session_id=session.id,
            experiment_id=experiment_id,
            mode=mode,
            status="RUNNING",
            started_at=_now(),
            inputs_json=_redact_inputs(inputs),
            trace_id=trace_id,
        )
        db.add(run)
        db.flush()  # assign PK without committing yet

        step_verdicts: list[dict[str, Any]] = []
        final_status = "PASSED"
        error_code: Optional[str] = None
        last_outputs: Dict[str, Any] = {}

        for step in manifest["steps"]:
            step_id = step["id"]
            operation_key = step["operation_key"]
            validator_key = step["validator_key"]
            expected = step.get("expected", {})

            # G06-PRE-01: build per-step inputs from run-level + step-level.
            # step.inputs (from the manifest) takes priority on key conflicts.
            step_inputs = _build_step_inputs(step, inputs)

            # Run the operation handler.
            try:
                op = get_operation(operation_key)
                op_result: OperationResult = op(db, settings, session, step_inputs)
            except Exception as exc:  # noqa: BLE001
                op_result = OperationResult(
                    operation_key=operation_key,
                    status="failed",
                    error_code=type(exc).__name__,
                    error_message=str(exc),
                )

            # Run the validator. The expected block from the manifest
            # is augmented with the run_id + trace_id so E07/E09 validators
            # can assert trace_id presence (ADR-0003 steps 4 + 5).
            #
            # G06-PRE-02: we no longer fabricate a `corrected_run`
            # placeholder. The validator sees the operation's actual
            # outputs. For E09 inject_failure steps, the validator
            # `failure_diagnosis_v1` reads `fail_step`, `status`, and
            # `trace_id` directly from `outputs`. The corrected rerun is
            # a separate step in the manifest that uses `run_trace_demo`
            # without `fail_step`; its validator reads `status: ok` from
            # that step's actual outputs.
            val_kwargs_expected = dict(expected)
            augmented_outputs = dict(op_result.outputs or {})
            augmented_outputs["run_trace_id"] = trace_id
            augmented_outputs["run_id"] = str(run_id)
            # G06-PRE-02: surface the operation's own status so the
            # failure_diagnosis_v1 validator (Shape B — corrected_run_only)
            # can read `outputs.status` to verify the corrected rerun
            # actually passed. The OperationResult.status is the
            # authoritative operation outcome; the outputs dict may not
            # carry it (e.g., run_trace_demo doesn't add a `status` key
            # to its outputs).
            augmented_outputs["status"] = op_result.status
            # For inject_failure steps: surface the failed step + status
            # + trace_id at the top level so the validator can read them
            # without a wrapper. The validator's expected shape is:
            #   {failed_run: {fail_step, status, trace_id}, corrected_run: {status}}
            # When this is an inject_failure step, the manifest's
            # validator (failure_diagnosis_v1) is invoked on the
            # single-step outputs; the "corrected_run" block is supplied
            # by the manifest's NEXT step (the rerun). The validator on
            # the inject_failure step itself only checks the failed_run
            # block, so we synthesize a minimal failed_run view from
            # the operation outputs.
            if operation_key == "inject_failure":
                augmented_outputs["failed_run"] = {
                    "fail_step": augmented_outputs.get("fail_step"),
                    "status": op_result.status,
                    "trace_id": trace_id,
                    "error_code": op_result.error_code,
                }

            try:
                validator = get_validator(validator_key)
                verdict: ValidationResult = validator(augmented_outputs, val_kwargs_expected)
            except Exception as exc:  # noqa: BLE001
                # Validator blew up — record as a hard failure, not a crash.
                verdict = ValidationResult(
                    validator_key=validator_key,
                    passed=False,
                    expected=val_kwargs_expected,
                    actual={"exception": str(exc)},
                    message=f"validator raised: {type(exc).__name__}: {exc}",
                )

            # Persist the step event.
            event = RunEvent(
                run_id=run_id,
                step=step_id,
                status=verdict.passed and op_result.status == "ok" and "ok" or (
                    "blocked" if op_result.status == "blocked" else "failed"
                ),
                record_json={
                    "operation_key": operation_key,
                    "operation_status": op_result.status,
                    "operation_error_code": op_result.error_code,
                    "operation_error_message": op_result.error_message,
                    "validator_key": validator_key,
                    "validator_passed": verdict.passed,
                    "validator_message": verdict.message,
                    "expected": verdict.expected,
                    "actual": verdict.actual,
                    # G06-PRE-01: record the effective inputs (after merge)
                    # so the diagnostic trail shows what the operation
                    # actually received. Redacted at rest (no secrets).
                    "effective_inputs": _redact_inputs(step_inputs),
                },
            )
            db.add(event)

            step_verdicts.append({
                "step_id": step_id,
                "operation_key": operation_key,
                "operation_status": op_result.status,
                "operation_error_code": op_result.error_code,
                "validator_key": validator_key,
                "validator_passed": verdict.passed,
                "validator_message": verdict.message,
                "expected": verdict.expected,
                "actual": verdict.actual,
            })

            last_outputs = augmented_outputs

            # G06-PRE-03 state transition: the run's final status is
            # determined by the VALIDATOR verdicts, NOT the operation
            # statuses. This preserves the distinction between:
            #   - an educational experiment that includes an INTENTIONAL
            #     failure (e.g., E09 inject_failure) — the operation
            #     status is "failed" but the validator passes because
            #     the failure was expected; the run stays PASSED.
            #   - a real failure (validator fails) — the run is FAILED.
            #   - a missing service (operation is BLOCKED) — the run is
            #     BLOCKED, which takes priority over FAILED.
            #
            # The op_result.status is still recorded in the RunEvent for
            # diagnostic purposes; it just doesn't drive the run status
            # directly.
            if op_result.status == "blocked":
                # G06-PRE-03: BLOCKED has priority over FAILED — a missing
                # service is an environmental condition, not a logic error.
                # The first BLOCKED step sets the run status; subsequent
                # FAILED steps don't downgrade it back.
                if final_status == "PASSED":
                    final_status = "BLOCKED"
                error_code = error_code or op_result.error_code
            elif not verdict.passed:
                # Validator failed — this is a real failure, not an
                # intentional one. The run is FAILED.
                if final_status == "PASSED":
                    final_status = "FAILED"
                    error_code = op_result.error_code or "validation_failed"
            # If verdict.passed is True, the step passes regardless of
            # op_result.status (the operation may have "failed" by design,
            # but the validator confirmed the expected outcome).

        # Finalize the run.
        run.status = final_status
        run.ended_at = _now()
        run.outputs_json = {
            "step_verdicts": step_verdicts,
            "last_outputs": _truncate_outputs(last_outputs, settings.max_output_bytes),
        }
        run.verification_json = {
            "step_verdicts": step_verdicts,
        }
        run.error_code = error_code
        db.commit()

        # G06-PRE-03: record the run outcome in the Prometheus metrics
        # registry so the E08 validator (metrics_demo_v1) can see nonzero
        # lab_runs_total. The labels are bounded (operation, status) —
        # no PII, no run_id, no session_id.
        try:
            from app.core.metrics import record_lab_run
            record_lab_run(operation=experiment_id, status=final_status)
        except Exception:
            # Metrics recording is best-effort; don't fail the run if
            # the metrics registry is unavailable.
            pass

        return RunOutcome(
            run_id=run_id,
            status=final_status,
            trace_id=trace_id,
            error_code=error_code,
            step_verdicts=step_verdicts,
            outputs=run.outputs_json,
        )


# ---- Read endpoints ----

def get_run(
    db: Session, session: GuestSession, run_id: uuid.UUID
) -> dict:
    """Return a bounded run state. 403 on cross-session access.

    Per A08: two sessions cannot read each other's runs.
    """
    run = _get_run(db, run_id)
    if run is None:
        raise NotFoundError(f"run not found: {run_id}")
    if run.session_id != session.id:
        # Per the contract: never reveal whether the run exists across
        # sessions — return 404 to avoid leaking the run's presence.
        raise NotFoundError(f"run not found: {run_id}")
    return _serialize_run(run)


def list_runs(
    db: Session,
    session: GuestSession,
    experiment_id: Optional[str] = None,
    limit: int = 50,
) -> List[dict]:
    """Return session-scoped run history, newest first."""
    if limit < 1 or limit > 200:
        limit = max(1, min(200, limit))
    stmt = (
        select(Run)
        .where(Run.session_id == session.id)
        .order_by(desc(Run.started_at))
        .limit(limit)
    )
    if experiment_id:
        stmt = stmt.where(Run.experiment_id == experiment_id)
    rows = db.execute(stmt).scalars().all()
    return [_serialize_run(r) for r in rows]


# ---- Reset ----

def reset_run(
    db: Session,
    settings: Settings,
    session: GuestSession,
    run_id: uuid.UUID,
) -> dict:
    """Recreate a clean fixture snapshot for the run's experiment.

    Per the contract §2 + §5: reset does NOT mutate the prior terminal
    run. Instead, it:
    1. Looks up the run (session-scoped — 404 on cross-session).
    2. Collects the dataset_ids that were actually used by the run's
       steps. G06-PRE-01: each step may have its own `inputs.dataset_id`
       (merged on top of run-level inputs), so the reset must look at
       the effective per-step inputs stored in RunEvents, not just the
       run-level inputs_json. This ensures we delete the graph rows
       that were actually seeded, even when the user passed a different
       dataset_id at the run level (which was overridden by step.inputs).
    3. Deletes all graph_nodes + graph_edges for each (session, dataset_id).
    4. Records a reset event (audit trail).
    5. Returns the reset record so the user can start fresh.
    """
    run = _get_run(db, run_id)
    if run is None:
        raise NotFoundError(f"run not found: {run_id}")
    if run.session_id != session.id:
        raise NotFoundError(f"run not found: {run_id}")

    # G06-PRE-01: collect the dataset_ids that were ACTUALLY used by the
    # run's steps. Each RunEvent's record_json carries `effective_inputs`
    # (the merged run-level + step-level inputs). We read those to find
    # all dataset_ids that may have seeded graph rows.
    events = db.execute(
        select(RunEvent).where(RunEvent.run_id == run.id)
    ).scalars().all()
    dataset_ids: set[str] = set()
    for ev in events:
        rec = ev.record_json or {}
        eff = rec.get("effective_inputs") or {}
        ds = eff.get("dataset_id")
        if ds:
            dataset_ids.add(str(ds))

    # Also consider the run-level inputs_json (for runs created before
    # G06-PRE-01 that don't have effective_inputs in their events).
    run_inputs = run.inputs_json or {}
    if run_inputs.get("dataset_id"):
        dataset_ids.add(str(run_inputs["dataset_id"]))

    # Fallback: the manifest's dataset_key when no dataset_id is found
    # (e.g., for observability experiments that don't seed graph data).
    if not dataset_ids:
        exp = _get_experiment(db, run.experiment_id)
        if exp is not None:
            manifest = _decode_manifest(exp)
            dk = manifest.get("dataset_key")
            if dk:
                dataset_ids.add(str(dk))

    # Delete graph rows for each (session, dataset_id) used.
    deleted_nodes: list[GraphNode] = []
    deleted_edges: list[GraphEdge] = []
    for ds_id in dataset_ids:
        nodes = db.execute(
            select(GraphNode)
            .where(GraphNode.session_id == session.id)
            .where(GraphNode.dataset_id == ds_id)
        ).scalars().all()
        for n in nodes:
            db.delete(n)
        deleted_nodes.extend(nodes)
        edges = db.execute(
            select(GraphEdge)
            .where(GraphEdge.session_id == session.id)
            .where(GraphEdge.dataset_id == ds_id)
        ).scalars().all()
        for e in edges:
            db.delete(e)
        deleted_edges.extend(edges)

    # Audit record: a RunEvent on the original run with step="reset".
    reset_event = RunEvent(
        run_id=run.id,
        step="reset",
        status="ok",
        record_json={
            "deleted_nodes": len(deleted_nodes),
            "deleted_edges": len(deleted_edges),
            "dataset_ids": sorted(dataset_ids),
            "timestamp": _now().isoformat(),
        },
    )
    db.add(reset_event)
    db.commit()

    return {
        "run_id": str(run.id),
        "experiment_id": run.experiment_id,
        # G06-PRE-01: return the list of dataset_ids that were reset
        # (a run may have used multiple datasets across its steps).
        "dataset_ids": sorted(dataset_ids),
        # Keep the singular field for backwards compatibility with the
        # G05 API schema (the API returns a single dataset_id; we send
        # the first one or the manifest's dataset_key).
        "dataset_id": sorted(dataset_ids)[0] if dataset_ids else None,
        "deleted_nodes": len(deleted_nodes),
        "deleted_edges": len(deleted_edges),
        "reset_event_id": str(reset_event.id),
    }


# ---- Compare ----

@dataclass
class CompareResult:
    run_a_id: uuid.UUID
    run_b_id: uuid.UUID
    same_experiment: bool
    same_final_status: bool
    same_step_count: bool
    step_diffs: List[Dict[str, Any]]
    note: str


def compare_runs(
    db: Session,
    session: GuestSession,
    run_a_id: uuid.UUID,
    run_b_id: uuid.UUID,
) -> CompareResult:
    """Compare two session-scoped runs (neutral relative comparison).

    Per the contract §4: `POST /api/v1/runs/compare` two scoped run IDs;
    neutral relative comparisons with runtime/context warnings.

    Both run IDs must belong to the caller's session (404 on cross-session
    or unknown).
    """
    a = _get_run(db, run_a_id)
    b = _get_run(db, run_b_id)
    if a is None or b is None:
        raise NotFoundError("one or both runs not found")
    if a.session_id != session.id or b.session_id != session.id:
        raise NotFoundError("one or both runs not found")

    a_verdicts = (a.verification_json or {}).get("step_verdicts", [])
    b_verdicts = (b.verification_json or {}).get("step_verdicts", [])

    step_diffs: list[dict[str, Any]] = []
    max_len = max(len(a_verdicts), len(b_verdicts))
    for i in range(max_len):
        a_step = a_verdicts[i] if i < len(a_verdicts) else None
        b_step = b_verdicts[i] if i < len(b_verdicts) else None
        if a_step is None or b_step is None:
            step_diffs.append({
                "step_index": i,
                "a_present": a_step is not None,
                "b_present": b_step is not None,
            })
            continue
        diff = {
            "step_index": i,
            "step_id": a_step.get("step_id"),
            "a_passed": a_step.get("validator_passed"),
            "b_passed": b_step.get("validator_passed"),
            "same_verdict": a_step.get("validator_passed") == b_step.get("validator_passed"),
        }
        if a_step.get("validator_passed") != b_step.get("validator_passed"):
            diff["a_message"] = a_step.get("validator_message")
            diff["b_message"] = b_step.get("validator_message")
        step_diffs.append(diff)

    same_experiment = a.experiment_id == b.experiment_id
    same_final_status = a.status == b.status
    same_step_count = len(a_verdicts) == len(b_verdicts)

    notes: list[str] = []
    if not same_experiment:
        notes.append("runs are from different experiments — comparison is informational only")
    if a.trace_id and b.trace_id and a.trace_id == b.trace_id:
        notes.append("runs share the same trace_id (rerun of the same request)")

    return CompareResult(
        run_a_id=a.id,
        run_b_id=b.id,
        same_experiment=same_experiment,
        same_final_status=same_final_status,
        same_step_count=same_step_count,
        step_diffs=step_diffs,
        note="; ".join(notes) if notes else "neutral relative comparison",
    )


# ---- Export ----

def export_run(
    db: Session,
    session: GuestSession,
    run_id: uuid.UUID,
    fmt: str,
) -> dict:
    """Export a run as Markdown or JSON.

    Per the contract §4: `GET /api/v1/runs/{id}/export?format=md|json`
    report including provenance, expected/actual, metric definitions.

    Inputs are redacted (no secrets, no PII).
    """
    if fmt not in ("md", "json"):
        raise InvalidStateError(
            "format must be 'md' or 'json'",
            details={"format": fmt},
        )

    run = _get_run(db, run_id)
    if run is None:
        raise NotFoundError(f"run not found: {run_id}")
    if run.session_id != session.id:
        raise NotFoundError(f"run not found: {run_id}")

    exp = _get_experiment(db, run.experiment_id)
    manifest = _decode_manifest(exp) if exp else {}

    common = {
        "run_id": str(run.id),
        "experiment_id": run.experiment_id,
        "experiment_title_en": manifest.get("title", {}).get("en", ""),
        "experiment_title_ar": manifest.get("title", {}).get("ar", ""),
        "mode": run.mode,
        "status": run.status,
        "trace_id": run.trace_id,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "ended_at": run.ended_at.isoformat() if run.ended_at else None,
        "error_code": run.error_code,
        "inputs_redacted": run.inputs_json,
        "step_verdicts": (run.verification_json or {}).get("step_verdicts", []),
        "provenance": {
            "manifest_digest": exp.manifest_digest if exp else None,
            "manifest_version": manifest.get("version"),
            "module_id": manifest.get("module_id"),
        },
    }

    if fmt == "json":
        return {"format": "json", "report": common}

    # Markdown report — human-readable.
    lines: list[str] = []
    lines.append(f"# Run Report — {run.experiment_id}")
    lines.append("")
    lines.append(f"- **Run ID:** `{run.id}`")
    lines.append(f"- **Status:** `{run.status}`")
    lines.append(f"- **Mode:** `{run.mode}`")
    if run.trace_id:
        lines.append(f"- **Trace ID:** `{run.trace_id}`")
    if run.error_code:
        lines.append(f"- **Error code:** `{run.error_code}`")
    if run.started_at:
        lines.append(f"- **Started:** {run.started_at.isoformat()}")
    if run.ended_at:
        lines.append(f"- **Ended:** {run.ended_at.isoformat()}")
    if exp:
        lines.append(f"- **Manifest digest:** `{exp.manifest_digest}`")
    lines.append("")
    lines.append("## Experiment")
    lines.append("")
    lines.append(f"**{manifest.get('title', {}).get('en', run.experiment_id)}**")
    lines.append("")
    desc = manifest.get("description", {}).get("en")
    if desc:
        lines.append(desc)
        lines.append("")
    lines.append("## Steps")
    lines.append("")
    verdicts = (run.verification_json or {}).get("step_verdicts", [])
    for i, v in enumerate(verdicts, start=1):
        marker = "[PASS]" if v.get("validator_passed") else "[FAIL]"
        lines.append(f"### Step {i}: {v.get('step_id', '')} {marker}")
        lines.append("")
        lines.append(f"- operation: `{v.get('operation_key')}` → status `{v.get('operation_status')}`")
        lines.append(f"- validator: `{v.get('validator_key')}` → passed `{v.get('validator_passed')}`")
        if v.get("operation_error_code"):
            lines.append(f"- operation error: `{v.get('operation_error_code')}` — {v.get('operation_error_message')}")
        lines.append(f"- message: {v.get('validator_message')}")
        lines.append("")
    lines.append("## Inputs (redacted)")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(run.inputs_json, indent=2, default=str))
    lines.append("```")
    lines.append("")
    lines.append("## Provenance")
    lines.append("")
    lines.append(f"- manifest_version: `{manifest.get('version')}`")
    lines.append(f"- module_id: `{manifest.get('module_id')}`")
    if exp:
        lines.append(f"- manifest_digest: `{exp.manifest_digest}`")

    return {"format": "md", "report": "\n".join(lines)}


# ---- Helpers ----

def _get_run(db: Session, run_id: uuid.UUID) -> Run | None:
    return db.execute(select(Run).where(Run.id == run_id)).scalar_one_or_none()


def _get_experiment(db: Session, experiment_id: str) -> Experiment | None:
    # The experiments table has unique (id, version); we return the latest
    # version for the given id (max(version)).
    stmt = (
        select(Experiment)
        .where(Experiment.id == experiment_id)
        .order_by(desc(Experiment.version))
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def _decode_manifest(exp: Experiment) -> dict:
    """Decode the manifest YAML stored on the experiment row."""
    import yaml
    return yaml.safe_load(exp.manifest_yaml) or {}


def _redact_inputs(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Strip any value whose key looks like a secret. Bounded by the
    contract §9 — no secrets stored in run records."""
    if not isinstance(inputs, dict):
        return {"_raw": str(inputs)[:200]}
    redacted: dict[str, Any] = {}
    for k, v in inputs.items():
        key_lower = str(k).lower()
        if any(s in key_lower for s in ("token", "password", "secret", "cookie", "api_key")):
            redacted[k] = "[REDACTED]"
        else:
            redacted[k] = v
    return redacted


def _truncate_outputs(outputs: Dict[str, Any], max_bytes: int) -> Dict[str, Any]:
    """Best-effort size cap on stored outputs. Drops verbose keys when
    the serialized size exceeds the limit."""
    try:
        s = json.dumps(outputs, default=str)
        if len(s.encode("utf-8")) <= max_bytes:
            return outputs
    except Exception:
        return {"_error": "outputs not serializable"}
    # Too big — return a trimmed version with counts only.
    trimmed: dict[str, Any] = {}
    for k, v in outputs.items():
        if isinstance(v, list):
            trimmed[k] = {"_len": len(v), "_truncated": True}
        elif isinstance(v, dict):
            trimmed[k] = {"_keys": sorted(v.keys())[:5], "_truncated": True}
        else:
            trimmed[k] = v
    return trimmed


def _build_step_inputs(step: dict, run_inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Build the inputs dict for a single step.

    G06-PRE-01: effective inputs are computed by merging the run-level
    inputs with the step-level `inputs` block (when present in the
    manifest). Step-level inputs take priority on key conflicts:
        effective_inputs = {**run_inputs, **step.inputs}

    The merge is read-only: the original `run_inputs` dict is NOT
    mutated. The result is a fresh dict per step.

    Security: the loader has already rejected `step.inputs` that contain
    security-critical keys (run_id, session_id, cookie_token, id). This
    function trusts that pre-check and does not re-verify it — but it
    does NOT mutate `run_inputs` either, so a step's override cannot
    leak back into the run-level record.

    Backwards compatibility: when `step.inputs` is absent (the G05
    manifest format), the function returns a copy of `run_inputs` —
    identical to the G05 behaviour.
    """
    merged = dict(run_inputs)
    step_inputs = step.get("inputs")
    if step_inputs and isinstance(step_inputs, dict):
        merged.update(step_inputs)
    return merged


def _serialize_run(run: Run) -> dict:
    return {
        "run_id": str(run.id),
        "experiment_id": run.experiment_id,
        "mode": run.mode,
        "status": run.status,
        "trace_id": run.trace_id,
        "error_code": run.error_code,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "ended_at": run.ended_at.isoformat() if run.ended_at else None,
        "inputs_redacted": run.inputs_json,
        "verification": run.verification_json,
        "outputs": run.outputs_json,
    }


# ---- Manifest persistence on boot ----

def persist_manifests_on_boot(db: Session, manifests: list) -> int:
    """Persist (idempotently) the loaded manifests to the experiments table.

    For each manifest: if a row with the same (id, version) exists and the
    digest matches, no-op. Otherwise, insert a new row.

    Returns the number of manifests persisted (newly inserted or updated).
    """
    inserted = 0
    for lm in manifests:
        manifest = lm.manifest  # LoadedManifest
        digest = lm.digest
        yaml_text = lm.yaml_text

        # Look up by (id, version) — the unique constraint.
        existing = db.execute(
            select(Experiment)
            .where(Experiment.id == manifest.id)
            .where(Experiment.version == manifest.version)
        ).scalar_one_or_none()

        if existing is not None and existing.manifest_digest == digest:
            continue  # idempotent — no update

        if existing is not None:
            # Digest changed: update the row.
            existing.manifest_digest = digest
            existing.manifest_yaml = yaml_text
            existing.module_id = manifest.module_id
        else:
            row = Experiment(
                id=manifest.id,
                module_id=manifest.module_id,
                version=manifest.version,
                manifest_digest=digest,
                manifest_yaml=yaml_text,
            )
            db.add(row)
        inserted += 1
    db.commit()
    return inserted
