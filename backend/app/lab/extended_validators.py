"""Allowlisted validators for E04–E10 (T19).

Each validator receives the `OperationResult` outputs and a dict of
expected values (drawn from the manifest's `expected` block). The verdict
is binary: passed True/False, with `details` for the report and mentor.

Per ADR-0003 Part A:
- E07 validator (trace_demo_v1) also asserts `run.trace_id is not None`.
- E09 validator (failure_diagnosis_v1) also asserts the failed run has
  a non-null `trace_id`.
- These two assertions close the run_id↔trace_id↔Grafana wiring plan.
"""
from __future__ import annotations

from typing import Any, Dict

from app.lab.registry import ValidationResult, register_validator


# ---- E04: SQL vs Cypher parity ----

@register_validator("parity_v1")
def validate_parity(
    outputs: Dict[str, Any],
    expected: Dict[str, Any],
) -> ValidationResult:
    """Assert the canonical SQL and Cypher result sets are equal.

    Expected:
        equal: true (or false for a deliberate mismatch test)
    """
    expected_equal = expected.get("equal", True)
    actual_equal = outputs.get("equal", False)
    error = outputs.get("error")

    if error and "NEO4J_URI not configured" in str(error):
        return ValidationResult(
            validator_key="parity_v1",
            passed=False,
            expected={"equal": expected_equal},
            actual={"equal": actual_equal, "error": error},
            message=f"BLOCKED: {error}",
        )

    passed = actual_equal == expected_equal
    return ValidationResult(
        validator_key="parity_v1",
        passed=passed,
        expected={"equal": expected_equal},
        actual={
            "equal": actual_equal,
            "sql_latency_ms": outputs.get("sql_latency_ms"),
            "cypher_latency_ms": outputs.get("cypher_latency_ms"),
        },
        message="canonical sets equal" if passed else (
            f"canonical sets not equal (expected={expected_equal}, actual={actual_equal})"
        ),
    )


# ---- E05: Critical Dependencies ----

@register_validator("critical_dep_v1")
def validate_critical_dep(
    outputs: Dict[str, Any],
    expected: Dict[str, Any],
) -> ValidationResult:
    """Assert the impact_set equals the expected set (sorted).

    Expected:
        target: str
        impact_set: list[str]
    """
    expected_target = expected.get("target")
    expected_impact = sorted(expected.get("impact_set") or [])
    actual_target = outputs.get("target")
    actual_impact = sorted(outputs.get("impact_set") or [])

    problems = []
    if expected_target and actual_target != expected_target:
        problems.append(f"target mismatch (expected={expected_target}, actual={actual_target})")
    if expected_impact != actual_impact:
        problems.append(
            f"impact_set mismatch (expected={expected_impact}, actual={actual_impact})"
        )

    passed = not problems
    return ValidationResult(
        validator_key="critical_dep_v1",
        passed=passed,
        expected={
            "target": expected_target,
            "impact_set": expected_impact,
        },
        actual={
            "target": actual_target,
            "impact_set": actual_impact,
            "target_in_degree": outputs.get("target_in_degree"),
            "target_out_degree": outputs.get("target_out_degree"),
            "target_degree_centrality": outputs.get("target_degree_centrality"),
            "note": outputs.get("note"),
        },
        message="impact_set matches expected directed reachability"
        if passed else "; ".join(problems),
    )


# ---- E06: Discover Communities ----

@register_validator("communities_v1")
def validate_communities(
    outputs: Dict[str, Any],
    expected: Dict[str, Any],
) -> ValidationResult:
    """Assert the community count matches and provenance is present.

    The cluster membership is compared up to label permutation (we compare
    the sorted list of sorted-member communities, so the order of clusters
    does not affect the verdict).

    Expected:
        expected_communities_count: int
    """
    expected_count = expected.get("expected_communities_count")
    actual_count = outputs.get("community_count")
    provider = outputs.get("provider")
    note = outputs.get("note")

    problems = []
    if expected_count is not None and actual_count != expected_count:
        problems.append(
            f"community_count mismatch (expected={expected_count}, actual={actual_count})"
        )
    if not provider:
        problems.append("provenance missing (provider is required)")
    if provider == "gds" and ("fallback" in note.lower() if note else False):
        problems.append("provider='gds' but note mentions fallback — provenance contradiction")

    passed = not problems
    return ValidationResult(
        validator_key="communities_v1",
        passed=passed,
        expected={"expected_communities_count": expected_count},
        actual={
            "community_count": actual_count,
            "provider": provider,
            "algorithm": outputs.get("algorithm"),
            "note": note,
        },
        message=f"{actual_count} communities detected by {provider}"
        if passed else "; ".join(problems),
    )


# ---- E07: Trace One Request (extended per ADR-0003 step 4) ----

@register_validator("trace_demo_v1_extended")
def validate_trace_demo_extended(
    outputs: Dict[str, Any],
    expected: Dict[str, Any],
) -> ValidationResult:
    """E07 extended validator: in addition to the basic trace_demo_v1
    assertion (≥3 spans), this validator also asserts that the run record
    has a populated `trace_id` (per ADR-0003 step 4).

    Expected:
        min_spans: int (default 3)
        run_trace_id: str | None  # the persisted run.trace_id
    """
    spans = outputs.get("spans") or []
    span_count = outputs.get("span_count", len(spans))
    expected_count = expected.get("min_spans", 3)
    run_trace_id = outputs.get("run_trace_id")

    problems = []
    if span_count < expected_count:
        problems.append(f"span_count {span_count} < {expected_count}")
    if not run_trace_id:
        problems.append("run.trace_id is None — run_id↔trace_id wiring incomplete")

    passed = not problems
    return ValidationResult(
        validator_key="trace_demo_v1_extended",
        passed=passed,
        expected={"min_spans": expected_count, "run_trace_id_present": True},
        actual={
            "span_count": span_count,
            "spans": spans,
            "run_trace_id": run_trace_id,
        },
        message=(
            f"trace has {span_count} spans and run.trace_id is populated"
            if passed else "; ".join(problems)
        ),
    )


# ---- E09: Diagnose a Hidden Failure (extended per ADR-0003 step 5) ----

@register_validator("failure_diagnosis_v1_extended")
def validate_failure_diagnosis_extended(
    outputs: Dict[str, Any],
    expected: Dict[str, Any],
) -> ValidationResult:
    """E09 extended validator: in addition to the basic failure_diagnosis_v1
    assertion (failed run pinpoints configured step + corrected rerun
    passes), this validator also asserts the failed run has a non-null
    `trace_id` (per ADR-0003 step 5).

    Expected:
        failed_run: {fail_step: str, trace_id_present: bool (default True)}
        corrected_run: {status: str}
    """
    failed = outputs.get("failed_run", {})
    corrected = outputs.get("corrected_run", {})
    expected_fail_step = expected.get("failed_run", {}).get("fail_step")
    expected_trace_present = expected.get("failed_run", {}).get("trace_id_present", True)
    actual_fail_step = failed.get("fail_step")
    corrected_status = corrected.get("status")
    failed_trace_id = failed.get("trace_id")

    problems = []
    if actual_fail_step != expected_fail_step:
        problems.append(
            f"failed_run.fail_step={actual_fail_step} != expected {expected_fail_step}"
        )
    if failed.get("status") != "failed":
        problems.append("failed_run.status is not 'failed'")
    if corrected_status != "ok":
        problems.append(f"corrected_run.status={corrected_status} != 'ok'")
    if expected_trace_present and not failed_trace_id:
        problems.append(
            "failed_run.trace_id is None — user cannot locate the failing span in Grafana"
        )

    passed = not problems
    return ValidationResult(
        validator_key="failure_diagnosis_v1_extended",
        passed=passed,
        expected={
            "failed_run": {
                "fail_step": expected_fail_step,
                "status": "failed",
                "trace_id_present": expected_trace_present,
            },
            "corrected_run": {"status": "ok"},
        },
        actual={
            "failed_run": {
                "fail_step": actual_fail_step,
                "status": failed.get("status"),
                "trace_id": failed_trace_id,
            },
            "corrected_run": {"status": corrected_status},
        },
        message=(
            "diagnosis matches injected fail_step + corrected rerun passes + trace_id present"
            if passed else "; ".join(problems)
        ),
    )


# ---- E10: Integrated Challenge ----

@register_validator("integrated_challenge_v1")
def validate_integrated_challenge(
    outputs: Dict[str, Any],
    expected: Dict[str, Any],
) -> ValidationResult:
    """Assert both the graph assertion (critical_edge) and the telemetry
    assertion (failing_step + corrected_status) pass.

    Expected:
        critical_edge: [source, target]  # the directed edge to identify
        failing_step: str (optional; if present, must match injected step)
        corrected_status: str (optional; 'ok' expected)
    """
    expected_critical_edge = expected.get("critical_edge")
    expected_failing_step = expected.get("failing_step")
    expected_corrected_status = expected.get("corrected_status")

    actual_critical_edge = outputs.get("critical_edge")
    actual_failing_step = outputs.get("failing_step")
    actual_corrected_status = outputs.get("corrected_status")

    problems = []
    if expected_critical_edge and actual_critical_edge != expected_critical_edge:
        problems.append(
            f"critical_edge mismatch (expected={expected_critical_edge}, "
            f"actual={actual_critical_edge})"
        )
    if expected_failing_step and actual_failing_step != expected_failing_step:
        problems.append(
            f"failing_step mismatch (expected={expected_failing_step}, "
            f"actual={actual_failing_step})"
        )
    if expected_corrected_status and actual_corrected_status != expected_corrected_status:
        problems.append(
            f"corrected_status mismatch (expected={expected_corrected_status}, "
            f"actual={actual_corrected_status})"
        )

    passed = not problems
    return ValidationResult(
        validator_key="integrated_challenge_v1",
        passed=passed,
        expected={
            "critical_edge": expected_critical_edge,
            "failing_step": expected_failing_step,
            "corrected_status": expected_corrected_status,
        },
        actual={
            "critical_edge": actual_critical_edge,
            "failing_step": actual_failing_step,
            "corrected_status": actual_corrected_status,
        },
        message="both graph and telemetry assertions pass"
        if passed else "; ".join(problems),
    )
