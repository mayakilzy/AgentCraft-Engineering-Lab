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
    """Assert exact node/edge counts and that the seed produced no dangling
    edges. Used by E01.
    """
    expected_nodes = expected.get("node_count")
    expected_edges = expected.get("edge_count")
    actual_nodes = outputs.get("node_count")
    actual_edges = outputs.get("edge_count")

    passed = (
        expected_nodes is not None
        and expected_edges is not None
        and actual_nodes == expected_nodes
        and actual_edges == expected_edges
    )
    return ValidationResult(
        validator_key="seed_five_nodes_v1",
        passed=passed,
        expected={"node_count": expected_nodes, "edge_count": expected_edges},
        actual={"node_count": actual_nodes, "edge_count": actual_edges},
        message="seed produced expected node/edge counts"
        if passed
        else "seed produced wrong counts",
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
