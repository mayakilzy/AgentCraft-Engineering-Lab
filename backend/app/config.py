"""Application settings loaded from environment variables.

All AI keys are optional; the mentor has a deterministic fallback when no
provider is configured. No secret is ever returned to the client.

G07-C1: production mode is fail-closed. When `APP_ENV=production`:
- `SESSION_COOKIE_SECURE` MUST be true (HTTPS only).
- `CORS_ORIGINS` MUST NOT contain localhost/127.0.0.1.
- `POSTGRES_PASSWORD`, `NEO4J_PASSWORD`, `GRAFANA_ADMIN_PASSWORD` MUST
  be set to non-default values (not 'changeme', not empty).
- The app aborts boot if any of these conditions is violated.

Local/dev mode (`APP_ENV=local` or `demo`) keeps the safe defaults so
the dev loop is not affected.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Default passwords that are NOT acceptable in production.
FORBIDDEN_DEFAULT_PASSWORDS = frozenset({"changeme", "", "password", "admin", "secret"})


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

    # G07-C1: production secrets (read from env, validated on boot).
    # These are the SAME env vars the Compose stack reads; we validate
    # them here so the app fails fast on misconfiguration, not at the
    # first DB connection.
    postgres_password: str = "changeme"
    grafana_admin_password: str = "changeme"

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

    @model_validator(mode="after")
    def _validate_production_safety(self) -> "Settings":
        """G07-C1: fail-closed production mode.

        When `APP_ENV=production`, the app aborts boot if any of:
        - `SESSION_COOKIE_SECURE` is not true
        - `CORS_ORIGINS` contains localhost/127.0.0.1
        - `POSTGRES_PASSWORD` is a forbidden default or empty
        - `NEO4J_PASSWORD` is a forbidden default or empty (when Neo4j
          is configured via NEO4J_URI)
        - `GRAFANA_ADMIN_PASSWORD` is a forbidden default or empty

        This is a hard gate — the app CANNOT start in production with
        insecure config. Local/dev mode is unaffected.
        """
        if self.app_env != "production":
            return self  # only production is fail-closed

        problems: list[str] = []

        # #5: SESSION_COOKIE_SECURE must be true in production (HTTPS).
        if not self.session_cookie_secure:
            problems.append(
                "SESSION_COOKIE_SECURE must be true in production (HTTPS only)"
            )

        # #4: CORS must not contain localhost.
        localhost_patterns = ("localhost", "127.0.0.1", "0.0.0.0")
        bad_origins = [
            o for o in self.cors_origins
            if any(p in o for p in localhost_patterns)
        ]
        if bad_origins:
            problems.append(
                f"CORS_ORIGINS must not contain localhost in production: {bad_origins}"
            )

        # #1: POSTGRES_PASSWORD must not be a default/empty.
        if self.postgres_password in FORBIDDEN_DEFAULT_PASSWORDS:
            problems.append(
                "POSTGRES_PASSWORD must be set to a non-default value in production "
                "(not 'changeme', not empty)"
            )

        # #1: NEO4J_PASSWORD must not be a default/empty (when Neo4j is configured).
        if self.neo4j_uri and self.neo4j_password in FORBIDDEN_DEFAULT_PASSWORDS:
            problems.append(
                "NEO4J_PASSWORD must be set to a non-default value in production "
                "when NEO4J_URI is configured (not 'changeme', not empty)"
            )

        # #1: GRAFANA_ADMIN_PASSWORD must not be a default/empty.
        if self.grafana_admin_password in FORBIDDEN_DEFAULT_PASSWORDS:
            problems.append(
                "GRAFANA_ADMIN_PASSWORD must be set to a non-default value in "
                "production (not 'changeme', not empty)"
            )

        if problems:
            # Fail-closed: raise with all problems at once so the operator
            # fixes them all in one pass.
            raise ValueError(
                "production config is insecure — aborting boot: "
                + "; ".join(problems)
            )

        return self

    @property
    def is_test_like(self) -> bool:
        """True when running against SQLite (unit tests or local dev)."""
        return self.database_url.startswith("sqlite")

    @property
    def is_production(self) -> bool:
        """True when APP_ENV=production (the fail-closed mode)."""
        return self.app_env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor; safe to inject as a FastAPI dependency."""
    return Settings()
