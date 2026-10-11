"""Lab operations — allowlisted handlers + validators.

Per the architecture contract §3: only allowlisted operation handlers
implemented in Python, no dynamic Python import from user submissions.
Manifests (full schema) land in G05; G02/T08 wires the three foundational
operation handlers + validators needed for E01-E03.

The `OPERATIONS` registry maps `operation_key` -> handler function.
The `VALIDATORS` registry maps `validator_key` -> validator function.
Both are fail-closed: unknown keys raise.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict

from app.core.errors import InvalidStateError


@dataclass
class OperationResult:
    """Output of running an operation. Validators consume this shape."""
    operation_key: str
    status: str  # ok | failed | blocked
    outputs: Dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None


@dataclass
class ValidationResult:
    """Output of running a validator. The verdict is binary: pass/fail,
    with a `details` dict for the report and mentor."""
    validator_key: str
    passed: bool
    expected: Dict[str, Any] = field(default_factory=dict)
    actual: Dict[str, Any] = field(default_factory=dict)
    message: str = ""


# Registries populated below. Lookups use these dicts; unknown keys raise.
_OPERATIONS: Dict[str, Callable[..., OperationResult]] = {}
_VALIDATORS: Dict[str, Callable[..., ValidationResult]] = {}


def register_operation(key: str) -> Callable[[Callable[..., OperationResult]], Callable[..., OperationResult]]:
    def deco(fn: Callable[..., OperationResult]) -> Callable[..., OperationResult]:
        if key in _OPERATIONS:
            raise InvalidStateError(
                f"operation_key already registered: {key}",
                details={"existing": _OPERATIONS[key].__name__},
            )
        _OPERATIONS[key] = fn
        return fn
    return deco


def register_validator(key: str) -> Callable[[Callable[..., ValidationResult]], Callable[..., ValidationResult]]:
    def deco(fn: Callable[..., ValidationResult]) -> Callable[..., ValidationResult]:
        if key in _VALIDATORS:
            raise InvalidStateError(
                f"validator_key already registered: {key}",
                details={"existing": _VALIDATORS[key].__name__},
            )
        _VALIDATORS[key] = fn
        return fn
    return deco


def get_operation(key: str) -> Callable[..., OperationResult]:
    if key not in _OPERATIONS:
        raise InvalidStateError(f"unknown operation_key: {key}", details={"requested": key})
    return _OPERATIONS[key]


def get_validator(key: str) -> Callable[..., ValidationResult]:
    if key not in _VALIDATORS:
        raise InvalidStateError(f"unknown validator_key: {key}", details={"requested": key})
    return _VALIDATORS[key]


def registered_operations() -> list[str]:
    return sorted(_OPERATIONS.keys())


def registered_validators() -> list[str]:
    return sorted(_VALIDATORS.keys())


# ---- Import all allowlisted handlers so they self-register ----
# These imports must come AFTER the registration decorators are defined.
from app.lab import operations as _ops  # noqa: E402,F401
from app.lab import validators as _vals  # noqa: E402,F401
from app.lab import observability_operations as _obs_ops  # noqa: E402,F401
# G05: E04–E10 operation handlers and validators (extended set).
from app.lab import extended_operations as _ext_ops  # noqa: E402,F401
from app.lab import extended_validators as _ext_vals  # noqa: E402,F401
