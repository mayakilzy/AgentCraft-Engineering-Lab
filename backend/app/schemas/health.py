"""Health DTOs: `/health/live` and `/health/ready`.

Per the architecture contract: readiness includes the required DB; optional
services (Neo4j, OTEL collector, AI provider) are reported as `degraded`,
never masked as `ready`.
"""
from __future__ import annotations

from typing import Dict, Literal

from pydantic import BaseModel, Field

ServiceState = Literal["up", "degraded", "down", "unknown"]


class ServiceStatus(BaseModel):
    state: ServiceState
    detail: str | None = None


class LiveResponse(BaseModel):
    status: Literal["ok"] = "ok"
    app: str = Field(..., description="Application name")


class ReadyResponse(BaseModel):
    """Required DB must be `up`; otherwise overall status is `not_ready`.

    Optional services may be `degraded` while overall is still `ready`.
    """
    status: Literal["ready", "degraded", "not_ready"]
    services: Dict[str, ServiceStatus]
    app_env: str
