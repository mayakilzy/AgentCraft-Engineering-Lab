"""T08 — Exercise foundations E01–E03.

For each exercise: a deterministic passing case AND a deterministic
failing case. Operations + validators are exercised through the
lab registry; the actual session-scoped storage is exercised through the
graph service + a real migrated DB.
"""
from __future__ import annotations

import pytest

from app.lab import (
    get_operation,
    get_validator,
    registered_operations,
    registered_validators,
)
from app.lab.registry import InvalidStateError  # type: ignore[attr-defined]


# ---- Registry shape ----

def test_registry_lists_known_keys():
    assert "seed_graph" in registered_operations()
    assert "shortest_path" in registered_operations()
    assert "filter_by_kind" in registered_operations()
    assert "graph_metrics" in registered_operations()

    assert "seed_five_nodes_v1" in registered_validators()
    assert "shortest_path_directed_v1" in registered_validators()
    assert "filter_by_kind_v1" in registered_validators()


def test_unknown_operation_rejected():
    with pytest.raises(InvalidStateError):
        get_operation("does-not-exist")


def test_unknown_validator_rejected():
    with pytest.raises(InvalidStateError):
        get_validator("does-not-exist")


# ---- E01: Build Your First Graph ----

def test_E01_pass(client, db, settings):
    """Seed starter-five-v1; validator asserts 5 nodes / 4 edges."""
    from app.services import session_service
    session = session_service.create_guest_session(db, settings, "en")

    op = get_operation("seed_graph")
    result = op(db, settings, session, {
        "dataset_id": "e01-ds",
        "fixture_key": "starter-five-v1",
    })
    assert result.status == "ok"
    assert result.outputs["node_count"] == 5
    assert result.outputs["edge_count"] == 4

    val = get_validator("seed_five_nodes_v1")
    verdict = val(result.outputs, {"node_count": 5, "edge_count": 4})
    assert verdict.passed is True


def test_E01_fail_wrong_fixture(client, db, settings):
    """Seeding an unknown fixture must produce a `failed` OperationResult;
    the validator then asserts the wrong counts and fails honestly.
    """
    from app.services import session_service
    session = session_service.create_guest_session(db, settings, "en")

    op = get_operation("seed_graph")
    result = op(db, settings, session, {
        "dataset_id": "e01-ds-fail",
        "fixture_key": "does-not-exist",
    })
    assert result.status == "failed"
    assert result.error_code is not None

    val = get_validator("seed_five_nodes_v1")
    verdict = val(result.outputs or {}, {"node_count": 5, "edge_count": 4})
    assert verdict.passed is False
    assert verdict.actual.get("node_count") != 5


def test_E01_fail_missing_input(client, db, settings):
    from app.services import session_service
    session = session_service.create_guest_session(db, settings, "en")
    op = get_operation("seed_graph")
    result = op(db, settings, session, {"dataset_id": "e01"})
    assert result.status == "failed"
    assert result.error_code == "bad_input"


# ---- E02: Shortest Path ----

def test_E02_pass_known_directed_path(client, db, settings):
    """Seed directed-path-v1; shortest_path A -> T3 = [A, T1, T2, T3]."""
    from app.services import session_service
    session = session_service.create_guest_session(db, settings, "en")

    # Seed first
    seed_op = get_operation("seed_graph")
    seed_op(db, settings, session, {
        "dataset_id": "e02-ds",
        "fixture_key": "directed-path-v1",
    })

    op = get_operation("shortest_path")
    result = op(db, settings, session, {
        "dataset_id": "e02-ds",
        "source": "A",
        "target": "T3",
    })
    assert result.status == "ok"
    assert result.outputs["path"] == ["A", "T1", "T2", "T3"]
    assert result.outputs["length"] == 3

    val = get_validator("shortest_path_directed_v1")
    verdict = val(result.outputs, {"path": ["A", "T1", "T2", "T3"]})
    assert verdict.passed is True


def test_E02_pass_unreachable_returns_none(client, db, settings):
    """A -> ISO is unreachable; the path must be None and the validator
    must accept that as expected behaviour (the test asserts honest
    negative-result handling, not a fake PASS).
    """
    from app.services import session_service
    session = session_service.create_guest_session(db, settings, "en")
    seed_op = get_operation("seed_graph")
    seed_op(db, settings, session, {
        "dataset_id": "e02-unreach",
        "fixture_key": "directed-path-v1",
    })

    op = get_operation("shortest_path")
    result = op(db, settings, session, {
        "dataset_id": "e02-unreach",
        "source": "A",
        "target": "ISO",
    })
    assert result.status == "ok"
    assert result.outputs["path"] is None
    assert result.outputs["unreachable"] is True

    val = get_validator("shortest_path_directed_v1")
    verdict = val(result.outputs, {"path": None})
    assert verdict.passed is True


def test_E02_fail_missing_node(client, db, settings):
    """Asking for a path to a node that doesn't exist in the dataset must
    produce a `failed` OperationResult with a deterministic error code.
    """
    from app.services import session_service
    session = session_service.create_guest_session(db, settings, "en")
    seed_op = get_operation("seed_graph")
    seed_op(db, settings, session, {
        "dataset_id": "e02-missing",
        "fixture_key": "directed-path-v1",
    })

    op = get_operation("shortest_path")
    result = op(db, settings, session, {
        "dataset_id": "e02-missing",
        "source": "A",
        "target": "GHOST",
    })
    assert result.status == "failed"
    assert result.error_code == "node_not_found"


def test_E02_fail_wrong_expected_path(client, db, settings):
    """If the validator is given the wrong expected path, it must fail
    honestly even when the operation succeeded."""
    from app.services import session_service
    session = session_service.create_guest_session(db, settings, "en")
    seed_op = get_operation("seed_graph")
    seed_op(db, settings, session, {
        "dataset_id": "e02-wrong",
        "fixture_key": "directed-path-v1",
    })

    op = get_operation("shortest_path")
    result = op(db, settings, session, {
        "dataset_id": "e02-wrong",
        "source": "A",
        "target": "T3",
    })
    assert result.status == "ok"

    val = get_validator("shortest_path_directed_v1")
    # Wrong expected path: validator must NOT silently pass.
    verdict = val(result.outputs, {"path": ["A", "B", "T3"]})
    assert verdict.passed is False
    assert "does not match expected" in verdict.message


# ---- E03: Interactive Graph Explorer (filter probe) ----

def test_E03_pass_filter_skills(client, db, settings):
    """Filter mixed-kind-v1 by kind='skill'; validator asserts the matched
    refs equal {SKILL1, SKILL2}.
    """
    from app.services import session_service
    session = session_service.create_guest_session(db, settings, "en")
    seed_op = get_operation("seed_graph")
    seed_op(db, settings, session, {
        "dataset_id": "e03-ds",
        "fixture_key": "mixed-kind-v1",
    })

    op = get_operation("filter_by_kind")
    result = op(db, settings, session, {
        "dataset_id": "e03-ds",
        "kinds": ["skill"],
    })
    assert result.status == "ok"
    assert result.outputs["matched_node_refs"] == ["SKILL1", "SKILL2"]
    assert result.outputs["match_count"] == 2
    assert result.outputs["total_nodes"] == 6

    val = get_validator("filter_by_kind_v1")
    verdict = val(result.outputs, {"matched_node_refs": ["SKILL1", "SKILL2"]})
    assert verdict.passed is True


def test_E03_pass_filter_apps(client, db, settings):
    from app.services import session_service
    session = session_service.create_guest_session(db, settings, "en")
    seed_op = get_operation("seed_graph")
    seed_op(db, settings, session, {
        "dataset_id": "e03-apps",
        "fixture_key": "mixed-kind-v1",
    })

    op = get_operation("filter_by_kind")
    result = op(db, settings, session, {
        "dataset_id": "e03-apps",
        "kinds": ["app"],
    })
    assert result.outputs["matched_node_refs"] == ["APP1", "APP2"]

    val = get_validator("filter_by_kind_v1")
    verdict = val(result.outputs, {"matched_node_refs": ["APP1", "APP2"]})
    assert verdict.passed is True


def test_E03_fail_wrong_subset(client, db, settings):
    """Validator must fail when expected subset doesn't match actual."""
    from app.services import session_service
    session = session_service.create_guest_session(db, settings, "en")
    seed_op = get_operation("seed_graph")
    seed_op(db, settings, session, {
        "dataset_id": "e03-fail",
        "fixture_key": "mixed-kind-v1",
    })

    op = get_operation("filter_by_kind")
    result = op(db, settings, session, {
        "dataset_id": "e03-fail",
        "kinds": ["skill"],
    })
    val = get_validator("filter_by_kind_v1")
    verdict = val(result.outputs, {"matched_node_refs": ["APP1", "APP2"]})
    assert verdict.passed is False


def test_E03_pass_no_filter_returns_all(client, db, settings):
    """Empty kinds filter returns all nodes — deterministic."""
    from app.services import session_service
    session = session_service.create_guest_session(db, settings, "en")
    seed_op = get_operation("seed_graph")
    seed_op(db, settings, session, {
        "dataset_id": "e03-all",
        "fixture_key": "mixed-kind-v1",
    })

    op = get_operation("filter_by_kind")
    result = op(db, settings, session, {
        "dataset_id": "e03-all",
        "kinds": [],
    })
    assert result.outputs["match_count"] == 6
    assert result.outputs["matched_node_refs"] == sorted(["APP1", "APP2", "TOOL1", "TOOL2", "SKILL1", "SKILL2"])
