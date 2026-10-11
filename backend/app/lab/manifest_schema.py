"""Lab module manifest schema + loader (T17).

Per the architecture contract §3:
- Manifest schema: id, version, title.{en,ar}, description.{en,ar},
  technology[], difficulty, estimated_minutes, prerequisites[],
  dataset_key, steps[] (each with id, title.{en,ar}, instruction.{en,ar},
  operation_key, input_schema_ref, expected_result, validator_key),
  capabilities[], public_demo_enabled, required_services[].
- Validate on app boot against schema and duplicated IDs; fail closed
  on unknown operation/validator.
- Only allowlisted operation handlers implemented in Python, no dynamic
  Python import from user submissions.
- Manifests bundled as trusted repository files in `lab-modules/`.

This module:
1. Defines a Pydantic schema for the manifest.
2. Loads YAML files from `lab-modules/` at app startup.
3. Validates each manifest against the schema.
4. Rejects duplicate IDs.
5. Rejects unknown operation_key / validator_key references against
   the static registries in `app.lab.registry`.
6. Persists each manifest to the `experiments` table (idempotent: if the
   manifest digest matches an existing row, no update is made).

The loader is fail-closed: if any manifest is malformed or references an
unknown operation/validator, app boot aborts with a clear log line.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.core.errors import InvalidStateError
from app.core.logging import get_logger
from app.lab.registry import registered_operations, registered_validators

log = get_logger(__name__)


# ---- Pydantic schema for the manifest ----

class LocalizedText(BaseModel):
    """A bilingual string. Technical symbols stay untranslated per A12."""
    model_config = ConfigDict(extra="forbid")
    en: str = Field(..., min_length=1, max_length=400)
    ar: str = Field(..., min_length=1, max_length=400)


class ManifestStep(BaseModel):
    """A single step in a guided/challenge flow.

    Each step references one allowlisted operation handler and one
    allowlisted validator. The loader fails the boot if either is unknown.
    """
    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., min_length=1, max_length=64)
    title: LocalizedText
    instruction: LocalizedText
    operation_key: str = Field(..., min_length=1, max_length=64)
    input_schema_ref: str = Field(..., min_length=1, max_length=64)
    validator_key: str = Field(..., min_length=1, max_length=64)
    expected: Dict[str, Any] = Field(default_factory=dict)


class Manifest(BaseModel):
    """Full manifest schema. Validates the structure; the loader then
    cross-checks operation_key / validator_key against the static registry.
    """
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, max_length=128)
    version: str = Field(..., min_length=1, max_length=32)
    module_id: str = Field(..., min_length=1, max_length=64)
    level: str = Field(..., min_length=1, max_length=32)
    estimated_minutes: int = Field(..., ge=1, le=240)
    title: LocalizedText
    description: LocalizedText
    technology: List[str] = Field(default_factory=list)
    prerequisites: List[str] = Field(default_factory=list)
    dataset_key: str = Field(..., min_length=1, max_length=128)
    required_services: List[str] = Field(default_factory=list)
    capabilities: List[str] = Field(default_factory=list)
    public_demo_enabled: bool = True
    steps: List[ManifestStep] = Field(..., min_length=1)
    failure_mode: Optional[str] = None

    @field_validator("level")
    @classmethod
    def _validate_level(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in {"beginner", "intermediate", "advanced"}:
            raise ValueError(f"level must be beginner|intermediate|advanced, got {v!r}")
        return v

    @field_validator("id", "module_id", "dataset_key")
    @classmethod
    def _validate_id_shape(cls, v: str) -> str:
        # Lower snake/kebab only; no whitespace, no path segments.
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError(
                f"id must be lower snake/kebab alphanumeric (got {v!r})"
            )
        return v


# ---- Loader result ----

@dataclass(frozen=True)
class LoadedManifest:
    """A parsed + validated manifest, plus its content digest for the DB."""
    manifest: Manifest
    digest: str  # sha256 hex of the canonical YAML text
    yaml_text: str


# ---- Loader ----

def _repo_root() -> Path:
    """Return the absolute path to the repository root.

    The manifest loader lives in `backend/app/lab/`; the lab-modules
    directory lives at the repository root (per the architecture contract
    §1: `lab-modules/` is a sibling of `backend/` and `frontend/`).
    """
    here = Path(__file__).resolve()
    # backend/app/lab/manifest_schema.py -> ../../.. = repo root.
    return here.parents[3]


def lab_modules_dir() -> Path:
    """The directory containing trusted manifest YAML files."""
    return _repo_root() / "lab-modules"


def _canonical_yaml_text(path: Path) -> str:
    """Read the YAML file as UTF-8 text. The digest is computed on the
    raw bytes so it changes if anyone edits the file."""
    return path.read_text(encoding="utf-8")


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_one(path: Path) -> LoadedManifest:
    """Parse + validate a single manifest file. Raises InvalidStateError
    on schema violation, unknown operation_key, or unknown validator_key."""
    text = _canonical_yaml_text(path)
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise InvalidStateError(
            f"manifest YAML parse failed: {path.name}",
            details={"error": str(exc)},
        ) from exc

    if not isinstance(raw, dict):
        raise InvalidStateError(
            f"manifest root must be a mapping: {path.name}",
            details={"got_type": type(raw).__name__},
        )

    try:
        manifest = Manifest.model_validate(raw)
    except ValidationError as exc:
        raise InvalidStateError(
            f"manifest schema validation failed: {path.name}",
            details={"errors": exc.errors()},
        ) from exc

    # Cross-check operation_key + validator_key against the static
    # registries. The registries are populated at import time by the
    # @register_operation / @register_validator decorators in
    # app/lab/operations.py and app/lab/validators.py.
    allowed_ops = set(registered_operations())
    allowed_vals = set(registered_validators())

    for step in manifest.steps:
        if step.operation_key not in allowed_ops:
            raise InvalidStateError(
                f"manifest {manifest.id} step {step.id} references unknown operation_key "
                f"{step.operation_key!r} (allowed: {sorted(allowed_ops)})",
                details={"step_id": step.id, "operation_key": step.operation_key},
            )
        if step.validator_key not in allowed_vals:
            raise InvalidStateError(
                f"manifest {manifest.id} step {step.id} references unknown validator_key "
                f"{step.validator_key!r} (allowed: {sorted(allowed_vals)})",
                details={"step_id": step.id, "validator_key": step.validator_key},
            )

    return LoadedManifest(
        manifest=manifest,
        digest=_digest(text),
        yaml_text=text,
    )


def load_all_manifests(directory: Path | None = None) -> List[LoadedManifest]:
    """Load every `*.yaml` file in `directory` (default `lab-modules/`).

    Fail-closed semantics:
    - The directory must exist.
    - Every YAML file must parse + validate.
    - IDs must be unique across all manifests.
    - All operation_key / validator_key references must resolve.

    On any failure, raises InvalidStateError with a precise message so the
    app boot aborts (A02 acceptance gate).
    """
    directory = directory or lab_modules_dir()
    if not directory.is_dir():
        raise InvalidStateError(
            f"lab-modules directory not found: {directory}",
            details={"resolved": str(directory)},
        )

    yaml_files = sorted(directory.glob("*.yaml"))
    if not yaml_files:
        raise InvalidStateError(
            f"no manifest YAML files found in {directory}",
            details={"resolved": str(directory)},
        )

    loaded: list[LoadedManifest] = []
    seen_ids: dict[str, str] = {}
    for path in yaml_files:
        lm = _load_one(path)
        if lm.manifest.id in seen_ids:
            raise InvalidStateError(
                f"duplicate manifest id {lm.manifest.id!r} (also defined in "
                f"{seen_ids[lm.manifest.id]})",
                details={
                    "manifest_id": lm.manifest.id,
                    "first_file": seen_ids[lm.manifest.id],
                    "second_file": path.name,
                },
            )
        seen_ids[lm.manifest.id] = path.name
        loaded.append(lm)
        log.info(
            "manifest loaded",
            extra={
                "manifest_id": lm.manifest.id,
                "version": lm.manifest.version,
                "file": path.name,
                "steps": len(lm.manifest.steps),
            },
        )

    return loaded


def manifest_count(directory: Path | None = None) -> int:
    """Number of manifests in the directory (after validation). Mainly
    used by the `/api/v1/modules` listing endpoint."""
    return len(load_all_manifests(directory))
