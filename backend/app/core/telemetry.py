"""Telemetry hook (placeholder). Wired in G04.

Until G04 lands, this module exposes a no-op `instrument_app(app)` so the
rest of the codebase can call it now without depending on OpenTelemetry.
The real implementation will attach OTEL FastAPI instrumentation and an
OTLP exporter to the configured collector.
"""
from __future__ import annotations

from typing import Any


def instrument_app(app: Any) -> None:
    """No-op in G01. G04 will register FastAPI instrumentation + OTLP export.

    Kept as a stable hook so `app/main.py` does not need to change later.
    """
    return None


def is_instrumented() -> bool:
    """True once the real OTEL SDK is active. Always False until G04."""
    return False
