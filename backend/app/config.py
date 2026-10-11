"""Application settings loaded from environment variables.

All AI keys are optional; the mentor has a deterministic fallback when no
provider is configured. No secret is ever returned to the client.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed configuration. Defaults are safe for local dev."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_env: str = "local"  # local | demo | production
    app_name: str = "AgentCraft Engineering Lab"
    log_level: str = "INFO"

    # Database
    database_url: str = "sqlite:///./agentcraft.db"

    # Sessions
    session_ttl_hours: int = 24
    session_cookie_name: str = "ac_guest"
    session_cookie_secure: bool = False

    # Security
    cors_origins: List[str] = ["http://localhost:5173", "http://localhost:8080"]
    rate_limit_per_minute: int = 60

    # Lab runtime bounds
    run_time_budget_seconds: int = 30
    max_graph_nodes: int = 200
    max_graph_edges: int = 500
    max_output_bytes: int = 262144  # 256 KiB
    max_question_chars: int = 2000

    # Mentor (Engineering Tutor)
    mentor_provider: str = "disabled"  # disabled | openai
    mentor_openai_api_key: str | None = None
    mentor_openai_model: str = "gpt-4o-mini"

    # Observability (wired in G04)
    otel_exporter_otlp_endpoint: str | None = None
    otel_service_name: str = "agentcraft-api"
    prometheus_url: str | None = None
    tempo_url: str | None = None
    grafana_url: str | None = None

    # Neo4j (wired in G03)
    neo4j_uri: str | None = None
    neo4j_user: str = "neo4j"
    neo4j_password: str | None = None
    neo4j_database: str = "neo4j"
    gds_licensed: bool = False

    @field_validator("app_env")
    @classmethod
    def _validate_env(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in {"local", "demo", "production"}:
            raise ValueError("app_env must be one of local|demo|production")
        return v

    @field_validator("mentor_provider")
    @classmethod
    def _validate_provider(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in {"disabled", "openai"}:
            raise ValueError("mentor_provider must be disabled|openai")
        return v

    @property
    def is_test_like(self) -> bool:
        """True when running against SQLite (unit tests or local dev)."""
        return self.database_url.startswith("sqlite")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor; safe to inject as a FastAPI dependency."""
    return Settings()
