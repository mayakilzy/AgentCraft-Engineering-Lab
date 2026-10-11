"""Health endpoints: `/health/live` and `/health/ready`.

- `live` returns 200 if the process is alive.
- `ready` reports each backing service. Required DB `up` → overall `ready`.
  Optional services may be `degraded` without flipping the overall status;
  any required service `down` → overall `not_ready` (503).

Optional services are probed defensively: any failure is mapped to `down`
or `unknown`, never raised. The contract says readiness must not mask
optional failures as healthy.
"""
from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import SettingsDep
from app.config import Settings
from app.schemas.health import (
    LiveResponse,
    ReadyResponse,
    ServiceState,
    ServiceStatus,
)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=LiveResponse)
def live(settings: SettingsDep) -> LiveResponse:
    """Liveness probe. Always 200 if the process can route here."""
    return LiveResponse(app=settings.app_name)


def _probe_db(settings: Settings) -> ServiceStatus:
    """Probe the configured database with a trivial SELECT 1.

    Returns `down` (with the message category, never the raw exception) on
    failure. SQLite path uses an in-process connection; PostgreSQL uses the
    configured driver.
    """
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(settings.database_url, pool_pre_ping=True)
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        finally:
            engine.dispose()
        return ServiceStatus(state="up", detail="select 1 ok")
    except Exception as exc:  # noqa: BLE001 — readiness must not crash
        return ServiceStatus(
            state="down",
            detail=f"{type(exc).__name__}: database unreachable",
        )


def _probe_optional(settings: Settings) -> dict[str, ServiceStatus]:
    """Probe optional services. Always returns `unknown` until wired (G03+)."""
    optional: dict[str, ServiceStatus] = {}
    # Neo4j — wired in G03
    if settings.neo4j_uri:
        optional["neo4j"] = ServiceStatus(state="unknown", detail="not yet wired")
    # OTEL collector — wired in G04
    if settings.otel_exporter_otlp_endpoint:
        optional["otel_collector"] = ServiceStatus(
            state="unknown", detail="not yet wired"
        )
    # Mentor provider — `up` if explicitly configured, else `unknown`
    if settings.mentor_provider == "openai":
        optional["mentor_provider"] = ServiceStatus(
            state="up" if settings.mentor_openai_api_key else "degraded",
            detail="openai configured" if settings.mentor_openai_api_key
            else "openai selected but key missing",
        )
    return optional


@router.get(
    "/ready",
    response_model=ReadyResponse,
    status_code=status.HTTP_200_OK,
    responses={
        503: {"description": "Required service unavailable"},
    },
)
def ready(
    settings: SettingsDep,
) -> Response:
    """Readiness probe. 200 if required services are up; 503 otherwise.

    Optional services reported but do not flip overall to `not_ready` unless
    explicitly required by contract (none in V1).
    """
    services: dict[str, ServiceStatus] = {"database": _probe_db(settings)}
    services.update(_probe_optional(settings))

    db_state: ServiceState = services["database"].state
    optional_degraded = any(
        s.state == "down" for s in services.values() if s is not services["database"]
    )

    if db_state == "up":
        overall = "degraded" if optional_degraded else "ready"
        code = 200
    else:
        overall = "not_ready"
        code = 503

    body = ReadyResponse(
        status=overall,
        services=services,
        app_env=settings.app_env,
    )
    return Response(
        status_code=code,
        content=body.model_dump_json(),
        media_type="application/json",
    )
