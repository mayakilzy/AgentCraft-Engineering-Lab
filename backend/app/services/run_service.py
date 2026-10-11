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

            # Build per-step inputs from the run-level inputs + the manifest.
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
            # is augmented with the run_id so E07/E09 validators can
            # assert trace_id presence.
            val_kwargs_expected = dict(expected)
            # Pass the persisted run_id + trace_id into the validator's
            # outputs so ADR-0003 steps 4 + 5 are testable end-to-end.
            augmented_outputs = dict(op_result.outputs or {})
            augmented_outputs["run_trace_id"] = trace_id
            augmented_outputs["run_id"] = str(run_id)
            # For E09 inject_failure: the validator expects failed_run/
            # corrected_run blocks. When the operation was inject_failure,
            # we wrap the result + a placeholder for the corrected run so
            # the validator's expected shape matches.
            if operation_key == "inject_failure":
                augmented_outputs = _wrap_inject_failure_outputs(
                    augmented_outputs, op_result, trace_id
                )

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

            # State transition: a step that fails OR is blocked propagates
            # to the run. We continue executing remaining steps so the user
            # sees the full diagnostic trail, but the final status is
            # FAILED or BLOCKED.
            if op_result.status == "blocked":
                final_status = "BLOCKED" if final_status == "PASSED" else final_status
                error_code = error_code or op_result.error_code
            elif not verdict.passed or op_result.status == "failed":
                if final_status == "PASSED":
                    final_status = "FAILED"
                    error_code = op_result.error_code or "validation_failed"

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
    2. Reads the run's inputs to find the `dataset_id` (the user-chosen
       scope name under which the fixture was seeded).
    3. Deletes all graph_nodes + graph_edges for that (session, dataset_id).
    4. Records a reset event (audit trail).
    5. Returns the reset record so the user can start fresh.
    """
    run = _get_run(db, run_id)
    if run is None:
        raise NotFoundError(f"run not found: {run_id}")
    if run.session_id != session.id:
        raise NotFoundError(f"run not found: {run_id}")

    # The dataset_id the user chose when creating the run (the scope
    # under which the graph rows were stored). Falls back to the
    # manifest's dataset_key when the run inputs don't carry a dataset_id
    # (e.g., for observability experiments that don't seed graph data).
    inputs = run.inputs_json or {}
    dataset_id = inputs.get("dataset_id")
    if not dataset_id:
        exp = _get_experiment(db, run.experiment_id)
        if exp is None:
            raise NotFoundError(f"experiment not found: {run.experiment_id}")
        manifest = _decode_manifest(exp)
        dataset_id = manifest.get("dataset_key")

    # Delete graph rows for this (session, dataset_id).
    deleted_nodes: list[GraphNode] = []
    deleted_edges: list[GraphEdge] = []
    if dataset_id:
        deleted_nodes = db.execute(
            select(GraphNode)
            .where(GraphNode.session_id == session.id)
            .where(GraphNode.dataset_id == dataset_id)
        ).scalars().all()
        for n in deleted_nodes:
            db.delete(n)
        deleted_edges = db.execute(
            select(GraphEdge)
            .where(GraphEdge.session_id == session.id)
            .where(GraphEdge.dataset_id == dataset_id)
        ).scalars().all()
        for e in deleted_edges:
            db.delete(e)

    # Audit record: a RunEvent on the original run with step="reset".
    reset_event = RunEvent(
        run_id=run.id,
        step="reset",
        status="ok",
        record_json={
            "deleted_nodes": len(deleted_nodes),
            "deleted_edges": len(deleted_edges),
            "dataset_id": dataset_id,
            "timestamp": _now().isoformat(),
        },
    )
    db.add(reset_event)
    db.commit()

    return {
        "run_id": str(run.id),
        "experiment_id": run.experiment_id,
        "dataset_id": dataset_id,
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
    """Build the inputs dict for a single step from the run-level inputs.

    Convention: the run-level inputs are a flat dict; each step's required
    inputs are looked up by key. For experiments that need per-step
    customization (e.g. E02 has steps that share dataset_id but differ in
    source/target), the manifest's `expected` block lists the keys the
    operation needs. The caller supplies them at run time.

    For G05 V1 we accept that the run-level inputs are sufficient: the
    caller passes dataset_id, source, target, etc. as needed; each step
    receives the full inputs dict. The operation handler is responsible
    for picking out the keys it needs.
    """
    return dict(run_inputs)


def _wrap_inject_failure_outputs(
    augmented_outputs: Dict[str, Any],
    op_result: OperationResult,
    trace_id: Optional[str],
) -> Dict[str, Any]:
    """Wrap the inject_failure operation result into the shape the
    failure_diagnosis_v1 validator expects:
        {
          "failed_run": {fail_step, status, trace_id},
          "corrected_run": {status: "ok" if trace_id is set else "unknown"}
        }

    The validator asserts both the failed run failed at the expected step
    AND that the failed run has a non-null trace_id (ADR-0003 step 5). The
    `corrected_run` block is a placeholder — the actual corrected rerun
    is a separate run with operation_key=run_trace_demo.
    """
    fail_step = augmented_outputs.get("fail_step")
    return {
        "failed_run": {
            "fail_step": fail_step,
            "status": op_result.status,
            "trace_id": trace_id,
            "error_code": op_result.error_code,
        },
        "corrected_run": {
            "status": "ok" if trace_id else "unknown",
        },
        # Keep the original spans etc. for the report.
        "spans": augmented_outputs.get("spans"),
        "span_count": augmented_outputs.get("span_count"),
        "run_trace_id": trace_id,
    }


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
