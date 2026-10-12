"""Allowlisted validators for E01–E03 (G02/T08).

Each validator receives the `OperationResult` outputs and a dict of
expected values (drawn from the fixture's `expected` block). The verdict
is binary: passed True/False, with `details` for the report and mentor.
"""
from __future__ import annotations

from typing import Any, Dict

from app.lab.registry import ValidationResult, register_validator


# ---- E01 ----

@register_validator("seed_five_nodes_v1")
def validate_seed_five_nodes(
    outputs: Dict[str, Any],
    expected: Dict[str, Any],
) -> ValidationResult:
    """E01 validator — per G02 reviewer note #3, this validator checks
    edge endpoint integrity, NOT just counts.

    Two assertion modes:

    Mode A — counts only (legacy contract, still supported for parity):
        expected = {"node_count": int, "edge_count": int}
        Validates that outputs match both counts.

    Mode B — counts + endpoint integrity (preferred, per note #3):
        expected = {
            "node_count": int,
            "edge_count": int,
            "node_refs":   list[str],   # all node_refs that must be present
            "edges":       list[(source_ref, target_ref, relation)],
                                       # every edge that must be present,
                                       # with both endpoints in node_refs
        }
        Validates:
          1. counts match;
          2. every expected node_ref is in the seeded node_refs;
          3. every expected edge is present (as a set — order-independent);
          4. no edge in the seeded set has a dangling endpoint (i.e., the
             source and target of every seeded edge are both in the seeded
             node_refs set).

    The fixture declares its own `expected` block with both fields, so a
    single seed-then-validate call exercises all four assertions.
    """
    expected_nodes = expected.get("node_count")
    expected_edges = expected.get("edge_count")
    actual_nodes = outputs.get("node_count")
    actual_edges = outputs.get("edge_count")
    expected_refs = expected.get("node_refs") or []
    expected_edges_list = expected.get("edges") or []
    actual_refs = set(outputs.get("node_refs") or [])
    actual_edges_set = set(
        (e[0], e[1], e[2]) for e in (outputs.get("edges") or [])
    )

    # Counts check.
    counts_ok = (
        expected_nodes is not None
        and expected_edges is not None
        and actual_nodes == expected_nodes
        and actual_edges == expected_edges
    )

    if not expected_refs and not expected_edges_list:
        # Mode A — counts only.
        return ValidationResult(
            validator_key="seed_five_nodes_v1",
            passed=counts_ok,
            expected={"node_count": expected_nodes, "edge_count": expected_edges},
            actual={"node_count": actual_nodes, "edge_count": actual_edges},
            message="seed produced expected node/edge counts"
            if counts_ok
            else "seed produced wrong counts",
        )

    # Mode B — counts + endpoint integrity.
    expected_refs_set = set(expected_refs)
    expected_edges_set = set(
        (s, t, r) for (s, t, r) in expected_edges_list
    )

    # 1. All expected node_refs are present.
    missing_refs = expected_refs_set - actual_refs
    # 2. All expected edges are present.
    missing_edges = expected_edges_set - actual_edges_set
    # 3. Unexpected edges (extras) — strict equality on the edge set.
    extra_edges = actual_edges_set - expected_edges_set
    # 4. Endpoint integrity: every actual edge has both endpoints in
    #    actual_refs. This is the assertion the old validator missed.
    dangling_edges = sorted(
        {(s, t, r) for (s, t, r) in actual_edges_set
         if s not in actual_refs or t not in actual_refs}
    )

    integrity_ok = (
        not missing_refs
        and not missing_edges
        and not extra_edges
        and not dangling_edges
    )
    passed = counts_ok and integrity_ok

    # Build a single human-readable message.
    problems: list[str] = []
    if not counts_ok:
        problems.append(
            f"counts mismatch (expected nodes={expected_nodes}/edges={expected_edges}, "
            f"actual nodes={actual_nodes}/edges={actual_edges})"
        )
    if missing_refs:
        problems.append(f"missing node_refs: {sorted(missing_refs)}")
    if missing_edges:
        problems.append(f"missing edges: {sorted(missing_edges)}")
    if extra_edges:
        problems.append(f"unexpected edges: {sorted(extra_edges)}")
    if dangling_edges:
        problems.append(f"dangling edges (endpoint not in node set): {dangling_edges}")

    return ValidationResult(
        validator_key="seed_five_nodes_v1",
        passed=passed,
        expected={
            "node_count": expected_nodes,
            "edge_count": expected_edges,
            "node_refs": sorted(expected_refs_set),
            "edges": sorted(expected_edges_set),
        },
        actual={
            "node_count": actual_nodes,
            "edge_count": actual_edges,
            "node_refs": sorted(actual_refs),
            "edges": sorted(actual_edges_set),
            "dangling_edges": dangling_edges,
        },
        message=(
            "seed matches expected counts and all edge endpoints are valid"
            if passed
            else "; ".join(problems) if problems else "validation failed"
        ),
    )


# ---- E02 ----

@register_validator("shortest_path_directed_v1")
def validate_shortest_path(
    outputs: Dict[str, Any],
    expected: Dict[str, Any],
) -> ValidationResult:
    """Assert the computed path equals the expected ordered node list, or
    that an unreachable pair returns None as expected.
    """
    expected_path = expected.get("path")
    actual_path = outputs.get("path")

    if expected_path is None:
        passed = actual_path is None
        return ValidationResult(
            validator_key="shortest_path_directed_v1",
            passed=passed,
            expected={"path": None},
            actual={"path": actual_path},
            message="unreachable pair correctly returned None"
            if passed
            else "expected unreachable, got a path",
        )

    passed = actual_path == expected_path
    return ValidationResult(
        validator_key="shortest_path_directed_v1",
        passed=passed,
        expected={"path": expected_path},
        actual={"path": actual_path},
        message="path matches expected ordered list"
        if passed
        else "path does not match expected",
    )


# ---- E03 ----

@register_validator("filter_by_kind_v1")
def validate_filter_by_kind(
    outputs: Dict[str, Any],
    expected: Dict[str, Any],
) -> ValidationResult:
    """Assert the matched node_refs equal the expected set (as a sorted
    list, so ordering does not affect the verdict).
    """
    expected_refs = expected.get("matched_node_refs") or []
    actual_refs = outputs.get("matched_node_refs") or []

    expected_set = sorted(set(expected_refs))
    actual_set = sorted(set(actual_refs))
    passed = expected_set == actual_set

    return ValidationResult(
        validator_key="filter_by_kind_v1",
        passed=passed,
        expected={"matched_node_refs": expected_set},
        actual={"matched_node_refs": actual_set},
        message="filtered subset matches expected"
        if passed
        else "filtered subset does not match expected",
    )


# ---- E07 — Trace One Request ----

@register_validator("trace_demo_v1")
def validate_trace_demo(
    outputs: Dict[str, Any],
    expected: Dict[str, Any],
) -> ValidationResult:
    """E07 validator: the trace must contain ≥3 spans (fetch → transform →
    persist) with status and timing. The run_id must be present in outputs.

    Per ADR-0003 step 4 (G05 wiring): the validator also asserts that
    `run.trace_id` is populated (not None). When the wiring is incomplete
    (the run record has no trace_id), the validator fails honestly so the
    reviewer can detect a wiring gap. The expected block can override this
    by setting `run_trace_id: false` for a deliberate "wiring not required"
    test (used by the legacy G04 tests).
    """
    spans = outputs.get("spans") or []
    span_count = outputs.get("span_count", len(spans))
    expected_count = expected.get("min_spans", 3)
    # G05 wiring: assert run.trace_id is present. The expected block can
    # opt-out via `run_trace_id: false` for backwards compatibility with
    # the G04 tests (which run before the runs endpoint is wired).
    require_trace_id = expected.get("run_trace_id", True)
    run_trace_id = outputs.get("run_trace_id")

    problems: list[str] = []
    if span_count < expected_count:
        problems.append(f"span_count {span_count} < {expected_count}")
    if require_trace_id and not run_trace_id:
        problems.append("run.trace_id is None (run_id↔trace_id wiring incomplete)")

    passed = not problems
    return ValidationResult(
        validator_key="trace_demo_v1",
        passed=passed,
        expected={
            "min_spans": expected_count,
            "run_trace_id_present": require_trace_id,
        },
        actual={
            "span_count": span_count,
            "spans": spans,
            "run_trace_id": run_trace_id,
        },
        message=(
            f"trace has {span_count} spans and run.trace_id is populated"
            if passed
            else "; ".join(problems) if problems
            else "validation failed"
        ),
    )


# ---- E08 — Build Monitoring Dashboard ----

@register_validator("metrics_demo_v1")
def validate_metrics_demo(
    outputs: Dict[str, Any],
    expected: Dict[str, Any],
) -> ValidationResult:
    """E08 validator: nonzero request count + bounded latency.

    G06-PRE-03: the `lab_runs_total >= 1` check is OPTIONAL. During a
    run's own execution, lab_runs_total is 0 because the run hasn't
    been counted yet (record_lab_run is called at run finalization,
    AFTER all steps). The validator would always fail during the run
    itself if we required lab_runs_total >= 1. The check is now gated
    by `expected.require_lab_runs` (default false) so callers who want
    to verify post-run that lab_runs_total is nonzero can opt in.
    """
    http_total = outputs.get("http_requests_total", 0)
    p95 = outputs.get("http_request_duration_seconds_p95")
    lab_total = outputs.get("lab_runs_total", 0)
    min_requests = expected.get("min_http_requests", 1)
    max_p95 = expected.get("max_p95_seconds", 10.0)
    require_lab_runs = expected.get("require_lab_runs", False)

    problems = []
    if http_total < min_requests:
        problems.append(f"http_requests_total {http_total} < {min_requests}")
    if p95 is not None and p95 > max_p95:
        problems.append(f"p95 latency {p95}s > {max_p95}s bound")
    if require_lab_runs and lab_total < 1:
        problems.append("lab_runs_total is zero")

    passed = not problems
    return ValidationResult(
        validator_key="metrics_demo_v1",
        passed=passed,
        expected={
            "min_http_requests": min_requests,
            "max_p95_seconds": max_p95,
        },
        actual={
            "http_requests_total": http_total,
            "http_request_duration_seconds_p95": p95,
            "lab_runs_total": lab_total,
        },
        message="nonzero request count + bounded latency + nonzero lab runs"
        if passed
        else "; ".join(problems),
    )


# ---- E09 — Diagnose a Hidden Failure ----

@register_validator("failure_diagnosis_v1")
def validate_failure_diagnosis(
    outputs: Dict[str, Any],
    expected: Dict[str, Any],
) -> ValidationResult:
    """E09 validator: the failed run must pinpoint the configured fail_step;
    the corrected (re-run without injection) must pass.

    Per ADR-0003 step 5 (G05 wiring): the validator also asserts the failed
    run has a non-null `trace_id` so the user can locate the failing span in
    Grafana Tempo. The expected block can opt out via
    `failed_run.trace_id_present: false` for backwards compatibility with
    the G04 tests.

    G06-PRE-02: the validator now supports TWO call shapes:

    Shape A — failed-run step (operation_key=inject_failure):
        The validator checks the `failed_run` block that the runner
        synthesizes from the operation's outputs. The `corrected_run`
        block is OPTIONAL here — when absent, the validator skips the
        corrected-run check. This is the typical case: the corrected
        rerun is a SEPARATE step in the manifest, not the same step.

    Shape B — corrected-rerun step (operation_key=run_trace_demo,
    no fail_step):
        The validator sees operation outputs WITHOUT a `failed_run`
        block. When `expected.corrected_run_only: true`, the validator
        checks only that the operation status is `ok` (i.e., the
        corrected rerun actually passed). This is the "fix and compare"
        step of E09.

    Shape C — combined (legacy G05 contract):
        Both `failed_run` and `corrected_run` are present. The validator
        checks both. This is the original G05 shape, kept for backwards
        compatibility with the G04-era tests.

    Expected shape (Shape A — failed-run step):
        expected = {
            "failed_run": {"fail_step": "transform", "trace_id_present": true},
        }

    Expected shape (Shape B — corrected-rerun step):
        expected = {
            "corrected_run_only": true,
            "corrected_run": {"status": "ok"},
        }

    Expected shape (Shape C — combined):
        expected = {
            "failed_run": {"fail_step": "transform", "trace_id_present": true},
            "corrected_run": {"status": "ok"},
        }
    """
    failed = outputs.get("failed_run", {})
    corrected = outputs.get("corrected_run", {})
    expected_fail = expected.get("failed_run", {}).get("fail_step")
    actual_fail = failed.get("fail_step")
    corrected_status = corrected.get("status")
    require_failed_trace_id = expected.get("failed_run", {}).get("trace_id_present", True)
    failed_trace_id = failed.get("trace_id")
    corrected_run_only = expected.get("corrected_run_only", False)

    problems = []

    if corrected_run_only:
        # Shape B — corrected-rerun step. The "operation status" comes
        # from the operation's own `status` field (the runner passes it
        # through to the validator via `outputs.status`).
        op_status = outputs.get("status", "ok")
        expected_corrected_status = expected.get("corrected_run", {}).get("status", "ok")
        if op_status != expected_corrected_status:
            problems.append(
                f"corrected rerun status={op_status} != expected {expected_corrected_status}"
            )
    else:
        # Shape A or C — there must be a failed_run block.
        if not failed:
            problems.append("failed_run block missing")
        else:
            if actual_fail != expected_fail:
                problems.append(
                    f"failed_run.fail_step={actual_fail} != expected {expected_fail}"
                )
            if failed.get("status") != "failed":
                problems.append("failed_run.status is not 'failed'")
            if require_failed_trace_id and not failed_trace_id:
                problems.append(
                    "failed_run.trace_id is None — user cannot locate the failing span in Grafana"
                )
        # Shape C — also check the corrected run when present in expected.
        if expected.get("corrected_run"):
            if corrected_status != expected.get("corrected_run", {}).get("status", "ok"):
                problems.append(
                    f"corrected_run.status={corrected_status} != 'ok'"
                )

    passed = not problems
    return ValidationResult(
        validator_key="failure_diagnosis_v1",
        passed=passed,
        expected={
            "failed_run": {
                "fail_step": expected_fail,
                "status": "failed",
                "trace_id_present": require_failed_trace_id,
            } if not corrected_run_only else None,
            "corrected_run": expected.get("corrected_run"),
            "corrected_run_only": corrected_run_only,
        },
        actual={
            "failed_run": {
                "fail_step": actual_fail,
                "status": failed.get("status"),
                "trace_id": failed_trace_id,
            } if failed else None,
            "corrected_run": {"status": corrected_status},
            "operation_status": outputs.get("status"),
        },
        message=(
            (
                "corrected rerun passed"
                if corrected_run_only
                else "diagnosis matches injected fail_step + trace_id present"
                + (" + corrected rerun passes" if expected.get("corrected_run") else "")
            )
            if passed
            else "; ".join(problems)
        ),
    )
