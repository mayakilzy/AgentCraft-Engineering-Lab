"""FastAPI application entry point.

G01 wires the `health` router + modules registry. G02-G03 add sessions,
graph, graph-analysis, seed, lab routers. G04 wires the observability
surface (metrics endpoint, telemetry instrumentation, observability links).
"""
from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import request_id_dep
from app.api.v1 import health as health_router
from app.api.v1 import sessions as sessions_router
from app.api.v1 import graph as graph_router
from app.api.v1 import graph_analysis as graph_analysis_router
from app.api.v1 import seed as seed_router
from app.api.v1 import lab as lab_router
from app.api.v1 import observability as observability_router
from app.config import Settings, get_settings
from app.core.errors import (
    AppError,
    app_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.logging import configure_logging, get_logger, set_request_id
from app.core.metrics import record_http_request, render_metrics
from app.core.telemetry import attach_trace_id_to_logging_context, instrument_app
from app.schemas.common import ErrorDetail
from app.services.modules_registry import get_registry

from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: configure logging, instrument OTEL, mount routers.

    G04: instrument_app() now wires the real FastAPI + SQLAlchemy
    instrumentation and an OTLP exporter (graceful no-op when no endpoint
    is configured). Manifests remain empty until G05.
    """
    settings = get_settings()
    configure_logging(settings.log_level)
    log = get_logger("app.lifespan")
    log.info(
        "starting",
        extra={
            "app_env": settings.app_env,
            "db_is_sqlite": settings.is_test_like,
            "otel_endpoint": settings.otel_exporter_otlp_endpoint or "(none)",
        },
    )
    instrument_app(app)
    yield
    log.info("shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Middleware: CORS to trusted origins only.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-Id"],
        allow_credentials=True,  # guest cookie is HttpOnly SameSite=Lax
    )

    @app.middleware("http")
    async def _attach_request_id_and_metrics(request: Request, call_next):
        """Stamp x-request-id, push trace_id into logging context, record
        Prometheus metrics. Bounded labels: method, path_template, status."""
        rid = request.headers.get("x-request-id") or str(uuid.uuid4())
        set_request_id(rid)
        attach_trace_id_to_logging_context()
        t0 = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # Record the metric even on unhandled exceptions (status=500).
            duration = time.perf_counter() - t0
            record_http_request(
                request.method,
                request.url.path,
                500,
                duration,
            )
            raise
        duration = time.perf_counter() - t0
        response.headers["x-request-id"] = rid
        # Use the matched route's path template (e.g. "/api/v1/graph/{id}")
        # for bounded cardinality; fall back to the raw path if no route
        # was matched (e.g. 404 on a typo'd URL).
        route = request.scope.get("route")
        path_template = getattr(route, "path", None) or request.url.path
        record_http_request(
            request.method,
            path_template,
            response.status_code,
            duration,
        )
        return response

    # Exception handlers → contract error body.
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # Routers
    app.include_router(health_router.router, prefix="/api/v1")
    app.include_router(sessions_router.router, prefix="/api/v1")
    app.include_router(graph_router.router, prefix="/api/v1")
    app.include_router(graph_analysis_router.router, prefix="/api/v1")
    app.include_router(seed_router.router, prefix="/api/v1")
    app.include_router(lab_router.router, prefix="/api/v1")
    app.include_router(observability_router.router, prefix="/api/v1")

    # Prometheus scrape endpoint. Public (Prometheus needs to scrape it)
    # but exposes only bounded-aggregate counters/histograms — no PII.
    @app.get("/metrics", tags=["metrics"])
    def metrics() -> Response:
        return Response(
            content=render_metrics(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    @app.get(
        "/api/v1/modules",
        tags=["modules"],
        response_model_exclude_none=True,
    )
    def list_modules():
        """List registered module manifests. Empty until G05 seeds manifests."""
        reg = get_registry()
        return {
            "count": reg.count(),
            "ids": [m.id for m in reg.all()],
        }

    @app.get(
        "/api/v1/experiments",
        tags=["experiments"],
        response_model_exclude_none=True,
    )
    def list_experiments():
        """List experiment manifests. Empty until G05 wires the catalog."""
        return {"count": 0, "ids": []}

    return app


app = create_app()
