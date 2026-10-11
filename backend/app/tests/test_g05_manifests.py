"""T17 / A02 — Manifest schema + loader tests.

Per the acceptance gate A02: 10 unique manifests validate; malformed and
unsafe operations rejected. The loader is fail-closed against duplicate
IDs and unknown operation/validator keys.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.core.errors import InvalidStateError
from app.lab.manifest_schema import (
    LoadedManifest,
    load_all_manifests,
    lab_modules_dir,
    _load_one,
)


# ---- A02: 10 unique manifests validate ----

def test_loads_exactly_ten_manifests():
    loaded = load_all_manifests()
    assert len(loaded) == 10


def test_all_manifest_ids_unique():
    loaded = load_all_manifests()
    ids = [lm.manifest.id for lm in loaded]
    assert len(ids) == len(set(ids))


def test_all_manifests_have_required_localized_fields():
    """Every manifest must have title + description + step titles +
    instructions in BOTH en and ar (per A12 localization gate)."""
    loaded = load_all_manifests()
    for lm in loaded:
        m = lm.manifest
        assert m.title.en and m.title.ar, f"{m.id}: title missing locale"
        assert m.description.en and m.description.ar, f"{m.id}: description missing locale"
        for i, step in enumerate(m.steps):
            assert step.title.en and step.title.ar, (
                f"{m.id} step[{i}] title missing locale"
            )
            assert step.instruction.en and step.instruction.ar, (
                f"{m.id} step[{i}] instruction missing locale"
            )


def test_all_manifests_reference_known_operations_and_validators():
    """A02 core: every operation_key + validator_key reference must resolve
    against the static registries. The loader already enforces this, but
    we test it explicitly so the gate is documented.
    """
    from app.lab.registry import registered_operations, registered_validators

    allowed_ops = set(registered_operations())
    allowed_vals = set(registered_validators())
    loaded = load_all_manifests()
    for lm in loaded:
        for step in lm.manifest.steps:
            assert step.operation_key in allowed_ops, (
                f"{lm.manifest.id} step {step.id}: unknown operation {step.operation_key}"
            )
            assert step.validator_key in allowed_vals, (
                f"{lm.manifest.id} step {step.id}: unknown validator {step.validator_key}"
            )


def test_expected_experiment_ids_present():
    """The 10 manifests must match the canonical experiment catalog
    (E01–E10) — no more, no less."""
    loaded = load_all_manifests()
    ids = {lm.manifest.id for lm in loaded}
    expected = {
        "graph-first-network",          # E01
        "shortest-path",                # E02
        "interactive-explorer",         # E03
        "sql-vs-cypher",                # E04
        "critical-dependencies",        # E05
        "discover-communities",         # E06
        "trace-one-request",            # E07
        "build-monitoring-dashboard",    # E08
        "diagnose-hidden-failure",      # E09
        "integrated-challenge",         # E10
    }
    assert ids == expected


def test_levels_are_valid():
    loaded = load_all_manifests()
    valid_levels = {"beginner", "intermediate", "advanced"}
    for lm in loaded:
        assert lm.manifest.level in valid_levels


def test_manifest_digests_are_stable():
    """The same manifest file always produces the same digest (so the
    DB upsert is idempotent across reboots)."""
    loaded = load_all_manifests()
    by_id = {lm.manifest.id: lm for lm in loaded}
    # Reload and compare
    loaded2 = load_all_manifests()
    by_id2 = {lm.manifest.id: lm for lm in loaded2}
    for mid in by_id:
        assert by_id[mid].digest == by_id2[mid].digest


# ---- A02 fail-closed: malformed manifests are rejected ----

def test_malformed_yaml_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("id: [unclosed\n  list", encoding="utf-8")
    with pytest.raises(InvalidStateError) as exc:
        _load_one(bad)
    assert "YAML parse failed" in str(exc.value)


def test_unknown_operation_key_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        """
id: bad-op
version: 1.0.0
module_id: graph
level: beginner
estimated_minutes: 10
title: {en: t, ar: t}
description: {en: d, ar: d}
dataset_key: starter-five-v1
steps:
  - id: s1
    title: {en: t, ar: t}
    instruction: {en: i, ar: i}
    operation_key: does_not_exist
    input_schema_ref: x
    validator_key: seed_five_nodes_v1
""",
        encoding="utf-8",
    )
    with pytest.raises(InvalidStateError) as exc:
        _load_one(bad)
    assert "unknown operation_key" in str(exc.value)


def test_unknown_validator_key_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        """
id: bad-val
version: 1.0.0
module_id: graph
level: beginner
estimated_minutes: 10
title: {en: t, ar: t}
description: {en: d, ar: d}
dataset_key: starter-five-v1
steps:
  - id: s1
    title: {en: t, ar: t}
    instruction: {en: i, ar: i}
    operation_key: seed_graph
    input_schema_ref: x
    validator_key: does_not_exist
""",
        encoding="utf-8",
    )
    with pytest.raises(InvalidStateError) as exc:
        _load_one(bad)
    assert "unknown validator_key" in str(exc.value)


def test_missing_required_field_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        """
id: missing-field
version: 1.0.0
module_id: graph
level: beginner
estimated_minutes: 10
title: {en: t, ar: t}
description: {en: d, ar: d}
# dataset_key missing
steps:
  - id: s1
    title: {en: t, ar: t}
    instruction: {en: i, ar: i}
    operation_key: seed_graph
    input_schema_ref: x
    validator_key: seed_five_nodes_v1
""",
        encoding="utf-8",
    )
    with pytest.raises(InvalidStateError) as exc:
        _load_one(bad)
    assert "schema validation failed" in str(exc.value)


def test_duplicate_id_rejected(tmp_path):
    """Two manifest files with the same id must fail the load."""
    a = tmp_path / "E01-a.yaml"
    a.write_text(
        """
id: dup-id
version: 1.0.0
module_id: graph
level: beginner
estimated_minutes: 10
title: {en: t, ar: t}
description: {en: d, ar: d}
dataset_key: starter-five-v1
steps:
  - id: s1
    title: {en: t, ar: t}
    instruction: {en: i, ar: i}
    operation_key: seed_graph
    input_schema_ref: x
    validator_key: seed_five_nodes_v1
""",
        encoding="utf-8",
    )
    b = tmp_path / "E01-b.yaml"
    b.write_text(
        """
id: dup-id
version: 1.0.0
module_id: graph
level: beginner
estimated_minutes: 10
title: {en: t, ar: t}
description: {en: d, ar: d}
dataset_key: starter-five-v1
steps:
  - id: s1
    title: {en: t, ar: t}
    instruction: {en: i, ar: i}
    operation_key: seed_graph
    input_schema_ref: x
    validator_key: seed_five_nodes_v1
""",
        encoding="utf-8",
    )
    with pytest.raises(InvalidStateError) as exc:
        load_all_manifests(tmp_path)
    assert "duplicate manifest id" in str(exc.value)


def test_empty_directory_rejected(tmp_path):
    """A directory with no YAML files fails the load (fail-closed)."""
    with pytest.raises(InvalidStateError) as exc:
        load_all_manifests(tmp_path)
    assert "no manifest YAML files" in str(exc.value)


def test_missing_directory_rejected(tmp_path):
    """A non-existent directory fails the load."""
    with pytest.raises(InvalidStateError) as exc:
        load_all_manifests(tmp_path / "does-not-exist")
    assert "lab-modules directory not found" in str(exc.value)


# ---- A09: gallery metadata (levels, prereqs, modes) ----

def test_manifests_have_levels_and_prerequisites():
    """A09 gate: full EN/AR objective/prereqs/steps/expectations,
    guided and challenge modes."""
    loaded = load_all_manifests()
    by_id = {lm.manifest.id: lm for lm in loaded}
    # Beginner experiments have no prereqs.
    assert by_id["graph-first-network"].manifest.prerequisites == []
    # E05 depends on E02 (shortest-path) per the catalog.
    assert "shortest-path" in by_id["critical-dependencies"].manifest.prerequisites
    # E10 depends on E05 + E07 + E08 per the catalog.
    prereqs_e10 = by_id["integrated-challenge"].manifest.prerequisites
    assert "critical-dependencies" in prereqs_e10
    assert "trace-one-request" in prereqs_e10
    assert "build-monitoring-dashboard" in prereqs_e10


def test_manifests_have_expected_outputs_in_steps():
    """A10 gate: expected results are assertions, not just prose. Each
    step's `expected` block must be a non-empty dict."""
    loaded = load_all_manifests()
    for lm in loaded:
        for step in lm.manifest.steps:
            assert isinstance(step.expected, dict), (
                f"{lm.manifest.id} step {step.id}: expected must be a dict"
            )
            assert len(step.expected) > 0, (
                f"{lm.manifest.id} step {step.id}: expected must be non-empty"
            )
