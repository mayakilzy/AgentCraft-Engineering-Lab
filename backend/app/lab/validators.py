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
