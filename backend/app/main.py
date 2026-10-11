"""FastAPI application entry point.

G01 wires only the `health` router and the modules registry listing. Later
groups add `sessions`, `experiments`, `runs`, `mentor`, `graph`, and
`observability` routers without restructuring this file.
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import request_id_dep
from app.api.v1 import health as health_router
from app.api.v1 import sessions as sessions_router
from app.api.v1 import graph as graph_router
from app.api.v1 import graph_analysis as graph_analysis_router
from app.api.v1 import seed as seed_router
from app.api.v1 import lab as lab_router
from app.config import Settings, get_settings
from app.core.errors import (
    AppError,
    app_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.logging import configure_logging, get_logger, set_request_id
from app.core.telemetry import instrument_app
from app.schemas.common import ErrorDetail
from app.services.modules_registry import get_registry

from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: configure logging, instrument, register manifests.

    Manifests are validated against the schema on boot; failures are
    fail-closed per the contract. For G01 the registry is intentionally
    empty so the listing endpoint honestly reports zero modules.
    """
    settings = get_settings()
    configure_logging(settings.log_level)
    log = get_logger("app.lifespan")
    log.info(
        "starting",
        extra={
            "app_env": settings.app_env,
            "db_is_sqlite": settings.is_test_like,
        },
    )
    instrument_app(app)  # no-op until G04
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
    async def _attach_request_id(request, call_next):
        """Stamp every response with `x-request-id` for client correlation."""
        rid = request.headers.get("x-request-id") or str(uuid.uuid4())
        set_request_id(rid)
        response = await call_next(request)
        response.headers["x-request-id"] = rid
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
