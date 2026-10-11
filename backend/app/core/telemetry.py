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

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    except ImportError:
        log.warning("opentelemetry packages not installed; instrumentation skipped")
        _instrumented = True
        return

    from app.config import get_settings
    settings = get_settings()

    resource = Resource.create({
        "service.name": settings.otel_service_name,
        "service.env": settings.app_env,
    })
    provider = TracerProvider(resource=resource)

    # Wire the OTLP exporter only if the endpoint is configured. This
    # keeps the app fully functional without a Collector (graceful
    # degradation); spans are still created and testable in-process.
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

    # Instrument FastAPI (auto request spans).
    FastAPIInstrumentor.instrument_app(app)

    # Instrument SQLAlchemy (auto DB spans). The engine is built lazily
    # in app.db.session; we instrument the engine after it's first used.
    try:
        from app.db.session import get_engine
        engine = get_engine()
        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            enable_commenter=False,  # avoid extra round-trips
        )
    except Exception as exc:
        log.warning(
            "sqlalchemy instrumentation skipped",
            extra={"error": f"{type(exc).__name__}: {exc}"},
        )

    _instrumented = True
    log.info("otel instrumentation complete", extra={"service": settings.otel_service_name})


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
