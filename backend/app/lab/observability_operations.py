"""T16 — Bounded failure-injection operation for E07-E09.

Per the architecture contract §7:
'Failure injection only predefined parameterized simulation e.g.
`sleep_ms ≤ 1500`, `fail_step=fetch|transform|persist`, inside synthetic
operation; never kill real DB/containers.'

This module defines the `trace_demo` operation family:
- `run_trace_demo` — E07: produces a trace with ≥3 spans (fetch → transform → persist)
- `inject_failure` — E09: same as run_trace_demo but injects a bounded
  failure at a named step, so the run FAILED with a specific error_code.

The spans carry run_id (non-PII) as an attribute. No secrets or guest
cookies are ever attached to spans (per contract §7).
"""
from __future__ import annotations

import time
from typing import Any, Dict

from sqlalchemy.orm import Session

from app.config import Settings
from app.core.logging import get_logger
from app.lab.registry import OperationResult, register_operation
from app.core.telemetry import get_tracer, set_run_id_on_current_span

log = get_logger(__name__)
tracer = get_tracer("agentcraft.lab.observability")


# Bounded failure-injection parameters (per contract §7).
ALLOWED_FAIL_STEPS = {"fetch", "transform", "persist"}
MAX_SLEEP_MS = 1500


def _run_trace_demo(
    db: Session,
    settings: Settings,
    session,
    inputs: Dict[str, Any],
    *,
    fail_step: str | None = None,
    sleep_ms: int = 0,
) -> OperationResult:
    """Synthetic operation: fetch → transform → persist, each as a span.

    When `fail_step` is set, the named step raises a bounded exception so
    the run FAILED with a specific error_code. When `sleep_ms` > 0, the
    fetch step sleeps for that many ms (bounded ≤ 1500 per contract).

    The run_id is attached to every span so traces are correlated with
    run records (wired in G05+; for G04 we use a synthetic run_id).
    """
    if sleep_ms > MAX_SLEEP_MS:
        return OperationResult(
            operation_key="run_trace_demo",
            status="failed",
            error_code="bad_input",
            error_message=f"sleep_ms {sleep_ms} exceeds bound {MAX_SLEEP_MS}",
        )
    if fail_step is not None and fail_step not in ALLOWED_FAIL_STEPS:
        return OperationResult(
            operation_key="run_trace_demo",
            status="failed",
            error_code="bad_input",
            error_message=f"fail_step must be one of {sorted(ALLOWED_FAIL_STEPS)}",
        )

    run_id = inputs.get("run_id", "demo-run")
    spans: list[dict] = []

    try:
        with tracer.start_as_current_span("lab.fetch") as fetch_span:
            set_run_id_on_current_span(run_id)
            fetch_span.set_attribute("agentcraft.step", "fetch")
            if sleep_ms > 0:
                time.sleep(sleep_ms / 1000.0)
            if fail_step == "fetch":
                raise RuntimeError("injected failure at fetch step")
            spans.append({"step": "fetch", "status": "ok"})

        with tracer.start_as_current_span("lab.transform") as transform_span:
            set_run_id_on_current_span(run_id)
            transform_span.set_attribute("agentcraft.step", "transform")
            if fail_step == "transform":
                raise RuntimeError("injected failure at transform step")
            spans.append({"step": "transform", "status": "ok"})

        with tracer.start_as_current_span("lab.persist") as persist_span:
            set_run_id_on_current_span(run_id)
            persist_span.set_attribute("agentcraft.step", "persist")
            if fail_step == "persist":
                raise RuntimeError("injected failure at persist step")
            spans.append({"step": "persist", "status": "ok"})

        return OperationResult(
            operation_key="run_trace_demo",
            status="ok",
            outputs={
                "run_id": run_id,
                "spans": spans,
                "span_count": len(spans),
                "fail_step": None,
                "sleep_ms": sleep_ms,
            },
        )
    except RuntimeError as exc:
        # Identify which step failed (from the fail_step parameter or the
        # span context).
        failed_step = fail_step or "unknown"
        return OperationResult(
            operation_key="run_trace_demo",
            status="failed",
            error_code=f"injected_{failed_step}_failure",
            error_message=str(exc),
            outputs={
                "run_id": run_id,
                "spans": spans,
                "span_count": len(spans),
                "fail_step": failed_step,
                "sleep_ms": sleep_ms,
            },
        )


@register_operation("run_trace_demo")
def run_trace_demo_op(
    db: Session,
    settings: Settings,
    session,
    inputs: Dict[str, Any],
) -> OperationResult:
    """E07: produce a trace with ≥3 spans (fetch → transform → persist)."""
    return _run_trace_demo(db, settings, session, inputs)


@register_operation("inject_failure")
def inject_failure_op(
    db: Session,
    settings: Settings,
    session,
    inputs: Dict[str, Any],
) -> OperationResult:
    """E09: inject a bounded failure at a named step. The run FAILED with
    a specific error_code; the trace shows which step failed."""
    fail_step = inputs.get("fail_step")
    sleep_ms = int(inputs.get("sleep_ms", 0))
    return _run_trace_demo(
        db, settings, session, inputs,
        fail_step=fail_step, sleep_ms=sleep_ms,
    )
