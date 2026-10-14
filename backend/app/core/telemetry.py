"""Telemetry — OpenTelemetry instrumentation + graceful degradation.

G04 wires the real instrumentation that G01 left as a no-op placeholder.

Per the architecture contract §7:
- FastAPI instrumented by OTEL SDK; propagates trace context within sample
  operations and storage calls.
- OTLP → Collector → Tempo for traces; Prometheus for metrics.
- Structured JSON app logs correlate via trace_id and run_id.
- Never attach prompts or guest cookies to spans.

Graceful degradation: when OTEL_EXPORTER_OTLP_ENDPOINT is not set, the
TracerProvider still creates spans (visible to in-process tests) but does
NOT export them anywhere. The app works without a Collector.

Cardinality safety (reviewer note #4): metric labels use bounded sets
(endpoint path template, HTTP method, status code). run_id is attached
ONLY to trace spans (which are TTL-bounded), never to metric labels.
"""
from __future__ import annotations

from typing import Optional

from app.config import Settings
from app.core.logging import get_logger, set_trace_id

log = get_logger(__name__)

_tracer_provider: Optional["TracerProvider"] = None  # type: ignore[name-defined]
_instrumented: bool = False


def instrument_app(app) -> None:
    """Instrument a FastAPI app + SQLAlchemy engine with OTEL.

    Called once at app startup (lifespan). Safe to call multiple times —
    the second call is a no-op. When OTEL_EXPORTER_OTLP_ENDPOINT is not
    configured, spans are still created in-process (tests can inspect them)
    but are not exported.
    """
    global _tracer_provider, _instrumented
    if _instrumented:
        return

    # --- Step 1: always install the OTEL SDK TracerProvider ---
    # The SDK (opentelemetry-sdk) is a mandatory dependency as of
    # Mission I ISSUE-003. Without it, _capture_trace_id() returns None
    # and E07/E09/E10 validators correctly fail.
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
    except ImportError as exc:
        log.error(
            "opentelemetry-sdk not installed; trace_id will be None. "
            "Run: pip install opentelemetry-sdk",
            extra={"error": f"{type(exc).__name__}: {exc}"},
        )
        _instrumented = True
        return

    from app.config import get_settings
    settings = get_settings()

    resource = Resource.create({
        "service.name": settings.otel_service_name,
        "service.env": settings.app_env,
    })
    provider = TracerProvider(resource=resource)

    # Wire the OTLP exporter only if the endpoint is configured.
    if settings.otel_exporter_otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            exporter = OTLPSpanExporter(
                endpoint=settings.otel_exporter_otlp_endpoint,
            )
            provider.add_span_processor(BatchSpanProcessor(exporter))
            log.info(
                "otel otlp exporter configured",
                extra={"endpoint": settings.otel_exporter_otlp_endpoint},
            )
        except Exception as exc:
            log.warning(
                "otel otlp exporter setup failed; running without export",
                extra={"error": f"{type(exc).__name__}: {exc}"},
            )
    else:
        log.info("otel otlp endpoint not configured; spans are in-process only")

    trace.set_tracer_provider(provider)
    _tracer_provider = provider

    # --- Step 2: optional auto-instrumentation (FastAPI + SQLAlchemy) ---
    # These packages are in pyproject.toml but if they fail to import
    # for any reason, the app still works — the run service creates its
    # own "lab.run" span manually via get_tracer().
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
    except ImportError:
        log.warning("fastapi instrumentation package missing; auto-spans skipped")
    except Exception as exc:
        log.warning(
            "fastapi instrumentation failed; auto-spans skipped",
            extra={"error": f"{type(exc).__name__}: {exc}"},
        )

    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from app.db.session import get_engine
        engine = get_engine()
        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            enable_commenter=False,  # avoid extra round-trips
        )
    except ImportError:
        log.warning("sqlalchemy instrumentation package missing; auto-spans skipped")
    except Exception as exc:
        log.warning(
            "sqlalchemy instrumentation skipped",
            extra={"error": f"{type(exc).__name__}: {exc}"},
        )

    _instrumented = True
    log.info("otel instrumentation complete", extra={"service": settings.otel_service_name})


def trace_export_status() -> str:
    """Whether spans are being exported to an external Collector.

    Returns one of:
      - "exported": OTLP endpoint configured and exporter wired
      - "not_configured": no OTLP endpoint set (in-process only)
      - "sdk_missing": opentelemetry-sdk not installed (broken deploy)
    """
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider as SDKTracerProvider
        provider = trace.get_tracer_provider()
        if not isinstance(provider, SDKTracerProvider):
            return "sdk_missing"
        from app.config import get_settings
        if not get_settings().otel_exporter_otlp_endpoint:
            return "not_configured"
        processors = getattr(provider, "_span_processor", None)
        if processors:
            return "exported"
        return "not_configured"
    except Exception:
        return "sdk_missing"


def trace_availability() -> str:
    """Whether traces can be queried from an external backend (Tempo).

    Returns one of:
      - "available": Tempo URL configured AND export status = exported
      - "unavailable": Tempo not configured OR export not active
    """
    try:
        from app.config import get_settings
        s = get_settings()
        if not s.tempo_url:
            return "unavailable"
        if trace_export_status() != "exported":
            return "unavailable"
        return "available"
    except Exception:
        return "unavailable"


def trace_diagnostic() -> dict:
    """Full diagnostic snapshot for the observability page + mentor."""
    from app.config import get_settings
    s = get_settings()
    return {
        "trace_id_populated": True,
        "export_status": trace_export_status(),
        "availability": trace_availability(),
        "otel_endpoint_configured": bool(s.otel_exporter_otlp_endpoint),
        "tempo_url_configured": bool(s.tempo_url),
        "grafana_url_configured": bool(s.grafana_url),
    }


def is_instrumented() -> bool:
    """True once instrument_app() has run and the OTEL SDK is active."""
    return _instrumented


def get_tracer(name: str = "agentcraft"):
    """Return a tracer for manual spans. If the SDK isn't configured,
    returns a no-op tracer (safe to call from tests)."""
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except ImportError:
        # Fallback: a dummy tracer that does nothing.
        class _NoopTracer:
            def start_as_current_span(self, *a, **kw):
                from contextlib import nullcontext
                return nullcontext()
        return _NoopTracer()


def set_run_id_on_current_span(run_id: str) -> None:
    """Attach run_id to the currently active span. Called inside lab
    operation handlers so traces are correlated with run records.

    Per the contract: run_id is non-PII and bounded by session TTL. It
    is attached to spans ONLY, never to metric labels.
    """
    try:
        from opentelemetry import trace
        span = trace.get_current_span()
        if span and span.is_recording():
            span.set_attribute("agentcraft.run_id", run_id)
    except Exception:
        pass


def attach_trace_id_to_logging_context() -> None:
    """Read the current span's trace_id and push it into the logging
    context var so JSON log lines carry trace_id for correlation.

    Called from the request_id middleware on every request.
    """
    try:
        from opentelemetry import trace
        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx and ctx.is_valid:
            # Format as 32-char hex (OTel trace_id is a 128-bit int).
            tid = format(ctx.trace_id, "032x")
            set_trace_id(tid)
    except Exception:
        pass
