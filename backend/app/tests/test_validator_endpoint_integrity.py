"""G02 reviewer note #3 — E01 validator endpoint integrity tests.

The validator must verify that every seeded edge has both endpoints in the
seeded node set; it must NOT pass on counts alone if a dangling edge exists.
"""
from __future__ import annotations

import pytest

from app.lab import get_validator


# ---- Mode A: counts only (legacy contract; still supported) ----

def test_validator_mode_a_counts_only_pass():
    v = get_validator("seed_five_nodes_v1")
    result = v(
        outputs={"node_count": 5, "edge_count": 4},
        expected={"node_count": 5, "edge_count": 4},
    )
    assert result.passed is True
    assert "counts" in result.message.lower()


def test_validator_mode_a_counts_only_fail():
    v = get_validator("seed_five_nodes_v1")
    result = v(
        outputs={"node_count": 5, "edge_count": 3},
        expected={"node_count": 5, "edge_count": 4},
    )
    assert result.passed is False
    assert "wrong counts" in result.message.lower()


# ---- Mode B: counts + endpoint integrity (preferred) ----

def test_validator_mode_b_pass_with_full_integrity():
    """Seed matches expected node_refs, edges, AND every edge endpoint is
    in the node set."""
    v = get_validator("seed_five_nodes_v1")
    result = v(
        outputs={
            "node_count": 5,
            "edge_count": 4,
            "node_refs": ["T1", "T2", "T3", "T4", "T5"],
            "edges": [
                ("T4", "T3", "APP_USES_TOOL"),
                ("T4", "T1", "APP_USES_TOOL"),
                ("T4", "T5", "APP_USES_TOOL"),
                ("T2", "T1", "TOOL_DEPENDS_ON_TOOL"),
            ],
        },
        expected={
            "node_count": 5,
            "edge_count": 4,
            "node_refs": ["T1", "T2", "T3", "T4", "T5"],
            "edges": [
                ("T4", "T3", "APP_USES_TOOL"),
                ("T4", "T1", "APP_USES_TOOL"),
                ("T4", "T5", "APP_USES_TOOL"),
                ("T2", "T1", "TOOL_DEPENDS_ON_TOOL"),
            ],
        },
    )
    assert result.passed is True
    assert "all edge endpoints are valid" in result.message


def test_validator_mode_b_fail_on_dangling_edge():
    """Seed produces an edge whose target node is NOT in the node_refs set.
    Counts would match if we only checked counts; the integrity check must
    catch the dangling edge.
    """
    v = get_validator("seed_five_nodes_v1")
    result = v(
        outputs={
            "node_count": 5,
            "edge_count": 4,
            "node_refs": ["T1", "T2", "T3", "T4", "T5"],
            # GHOST is not in node_refs — dangling edge.
            "edges": [
                ("T4", "T3", "APP_USES_TOOL"),
                ("T4", "T1", "APP_USES_TOOL"),
                ("T4", "GHOST", "APP_USES_TOOL"),
                ("T2", "T1", "TOOL_DEPENDS_ON_TOOL"),
            ],
        },
        expected={
            "node_count": 5,
            "edge_count": 4,
            "node_refs": ["T1", "T2", "T3", "T4", "T5"],
            "edges": [
                ("T4", "T3", "APP_USES_TOOL"),
                ("T4", "T1", "APP_USES_TOOL"),
                ("T4", "T5", "APP_USES_TOOL"),
                ("T2", "T1", "TOOL_DEPENDS_ON_TOOL"),
            ],
        },
    )
    assert result.passed is False
    # The verdict message must mention the dangling edge AND the missing/
    # unexpected edge discrepancies.
    msg = result.message
    assert "dangling edges" in msg
    assert "unexpected edges" in msg or "missing edges" in msg
    # The actual block must record the dangling edge.
    assert "dangling_edges" in result.actual
    assert len(result.actual["dangling_edges"]) == 1
    assert ("T4", "GHOST", "APP_USES_TOOL") in result.actual["dangling_edges"]


def test_validator_mode_b_fail_on_missing_node_ref():
    """Seed is missing one expected node_ref. Integrity must fail."""
    v = get_validator("seed_five_nodes_v1")
    result = v(
        outputs={
            "node_count": 4,  # also wrong count
            "edge_count": 4,
            "node_refs": ["T1", "T2", "T3", "T4"],  # missing T5
            "edges": [
                ("T4", "T3", "APP_USES_TOOL"),
                ("T4", "T1", "APP_USES_TOOL"),
                ("T4", "T5", "APP_USES_TOOL"),  # T5 not in node_refs → dangling
                ("T2", "T1", "TOOL_DEPENDS_ON_TOOL"),
            ],
        },
        expected={
            "node_count": 5,
            "edge_count": 4,
            "node_refs": ["T1", "T2", "T3", "T4", "T5"],
            "edges": [
                ("T4", "T3", "APP_USES_TOOL"),
                ("T4", "T1", "APP_USES_TOOL"),
                ("T4", "T5", "APP_USES_TOOL"),
                ("T2", "T1", "TOOL_DEPENDS_ON_TOOL"),
            ],
        },
    )
    assert result.passed is False
    assert "missing node_refs" in result.message
    assert "T5" in result.message or "T5" in str(result.actual["node_refs"])


def test_validator_mode_b_fail_on_extra_edge():
    """Seed has an extra edge not in the expected set; must fail even if
    counts happened to match."""
    v = get_validator("seed_five_nodes_v1")
    result = v(
        outputs={
            "node_count": 5,
            "edge_count": 5,  # extra edge
            "node_refs": ["T1", "T2", "T3", "T4", "T5"],
            "edges": [
                ("T4", "T3", "APP_USES_TOOL"),
                ("T4", "T1", "APP_USES_TOOL"),
                ("T4", "T5", "APP_USES_TOOL"),
                ("T2", "T1", "TOOL_DEPENDS_ON_TOOL"),
                ("T1", "T3", "EXTRA_EDGE"),  # extra
            ],
        },
        expected={
            "node_count": 5,
            "edge_count": 4,
            "node_refs": ["T1", "T2", "T3", "T4", "T5"],
            "edges": [
                ("T4", "T3", "APP_USES_TOOL"),
                ("T4", "T1", "APP_USES_TOOL"),
                ("T4", "T5", "APP_USES_TOOL"),
                ("T2", "T1", "TOOL_DEPENDS_ON_TOOL"),
            ],
        },
    )
    assert result.passed is False
    assert "unexpected edges" in result.message


def test_validator_mode_b_pass_through_full_seed_operation(client, db, settings):
    """End-to-end: seed starter-five-v1 via the operation, then run the
    validator against the operation's actual outputs and the fixture's
    declared expected block. Must pass.
    """
    from app.lab import get_operation
    from app.fixtures.graph_seed import STARTER_FIVE_V1
    from app.services import session_service

    session = session_service.create_guest_session(db, settings, "en")
    op = get_operation("seed_graph")
    result = op(db, settings, session, {
        "dataset_id": "e01-validator-e2e",
        "fixture_key": "starter-five-v1",
    })
    assert result.status == "ok"

    v = get_validator("seed_five_nodes_v1")
    verdict = v(result.outputs, dict(STARTER_FIVE_V1.expected))
    assert verdict.passed is True, verdict.message


def test_validator_mode_b_catches_dangling_via_operation(client, db, settings):
    """If we sneak in a dangling edge by manually adding an edge whose
    target doesn't exist, the validator (Mode B) must catch it even when
    counts would otherwise match.
    """
    from app.lab import get_operation
    from app.fixtures.graph_seed import STARTER_FIVE_V1
    from app.services import session_service, graph_service

    session = session_service.create_guest_session(db, settings, "en")
    op = get_operation("seed_graph")
    result = op(db, settings, session, {
        "dataset_id": "e01-validator-dangling",
        "fixture_key": "starter-five-v1",
    })
    assert result.status == "ok"

    # Sabotage: remove one node_ref from outputs but keep the edge list,
    # simulating a seed that left a dangling edge (this is what the
    # validator is supposed to catch).
    sabotaged_outputs = dict(result.outputs)
    sabotaged_outputs["node_refs"] = [
        n for n in sabotaged_outputs["node_refs"] if n != "T3"
    ]
    # Now the edge ("T4", "T3", "APP_USES_TOOL") is dangling.

    v = get_validator("seed_five_nodes_v1")
    verdict = v(sabotaged_outputs, dict(STARTER_FIVE_V1.expected))
    assert verdict.passed is False
    assert "dangling edges" in verdict.message
    assert ("T4", "T3", "APP_USES_TOOL") in verdict.actual["dangling_edges"]
