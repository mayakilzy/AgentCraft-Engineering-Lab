# ADR-0001 — Technology stack pinning and rationale

**Date:** 2026-10-11
**Status:** Accepted (G01, frozen V1.0)
**Supersedes:** none
**References:** `01_PROJECT_MASTER_SPEC.md` §6, `02_ARCHITECTURE_AND_CONTRACTS.md` §1, `04_EXECUTION_PROTOCOL.md` §"Constraints"

## Context

The repository is empty (clean baseline). The frozen V1.0 spec mandates a
specific stack: FastAPI + React/TypeScript + Vite + Tailwind + PostgreSQL +
SQLAlchemy + Alembic + NetworkX + Cytoscape.js + Neo4j + OpenTelemetry +
Prometheus + Tempo + Grafana + Docker Compose. Before writing application
code, dependency versions must be pinned after verification against the
runtime actually available in this environment, so that subsequent groups
can build on a stable, reproducible base.

## Decision

Pin the following versions, all verified installable in the current
environment (Python 3.12.15, Node 24.21.0):

### Backend (Python 3.12)
| Package | Version | Rationale |
|---|---|---|
| fastapi | 0.128.0 | Pre-installed; current stable; supports Pydantic v2 and modern lifespan. |
| uvicorn | (standard extra) | ASGI server bundled with `fastapi[standard]`. |
| pydantic | 2.x | Required by FastAPI 0.128. |
| pydantic-settings | 2.7.1 | Type-safe settings from env; minor pin to avoid behavioral drift. |
| SQLAlchemy | 2.0.36 | Current 2.0.x line; async-capable; mature JSON column support for PostgreSQL. |
| alembic | 1.14.1 | Compatible with SQLAlchemy 2.0; version 1.14.2 unavailable on PyPI (yanked); 1.14.1 is the latest 1.14.x. |
| psycopg2-binary | 2.9.10 | PostgreSQL driver; binary wheel to avoid libpq build dependency. |
| asyncpg | 0.30.0 | Async PostgreSQL driver for async SQLAlchemy sessions in later groups. |
| httpx | 0.28.1 | Used by FastAPI `TestClient` and for downstream mentor provider calls. |
| pytest | 8.3.4 | Stable test runner. |
| pytest-asyncio | 0.25.3 | Async test support (for G04+). |

PostgreSQL-specific features (JSONB, `gen_random_uuid()`) will be guarded
behind dialect checks so the same models can run on SQLite for unit tests,
per the testing strategy in ADR-0002 (forthcoming).

### Frontend (Node 24)
| Package | Version | Rationale |
|---|---|---|
| react | 18.3.x | Current stable; ecosystem compatibility with Cytoscape.js wrappers. |
| react-dom | 18.3.x | Matches react. |
| typescript | 5.6.x | Current 5.x; satisfies Vite + Tailwind 4 tooling. |
| vite | 5.4.x | Stable Vite; React plugin works on Node 24. |
| tailwindcss | 3.4.x | V1 spec names Tailwind; 3.4 is current stable. (Tailwind 4 alpha has breaking config; defer until GA.) |
| i18next | 23.x + react-i18next 15.x | Spec mandates i18next. |
| cytoscape | 3.30.x | Latest 3.x; spec mandates Cytoscape.js. |
| vitest | 2.1.x | Vite-native test runner. |
| @playwright/test | 1.49.x | E2E in later groups. |

### Infrastructure (Docker Compose, pinned in G04)
| Component | Version (target) | Notes |
|---|---|---|
| PostgreSQL | 16 (official image) | JSONB, `gen_random_uuid()`, logical types. |
| Neo4j | 5.x community (G03) | GDS plugin optional; detected by capability probe. |
| OTEL Collector | contrib-latest (G04) | OTLP receiver; Tempo + Prometheus exporters. |
| Prometheus | 2.x (G04) | Scrape API metrics. |
| Tempo | 2.x (G04) | Trace store. |
| Grafana | 11.x (G04) | Provisioned datasources/dashboards. |

Final image tags will be pinned in `docker-compose.yml` as each group wires
its component; pinning here is a target, not a commit-time guarantee until
that group runs.

## Alternatives considered

- **SQLModel** instead of SQLAlchemy + Pydantic separately: rejected — spec
  explicitly names SQLAlchemy and Pydantic as separate contracts; SQLModel's
  opinionated typing can conflict with the dual-model (ORM + DTO) pattern
  the architecture contract requires.
- **Tailwind 4 alpha**: rejected for V1.0 stability; revisit at V2.
- **Alembic 1.15/1.16**: deferred pinning to 1.14.1 because the exact
  1.14.2 release was yanked and later 1.x versions introduce migration
  template changes that have not been validated against our env yet.

## Consequences

- Backend `pyproject.toml` and frontend `package.json` will lock these
  versions.
- Tests run against SQLite by default; CI/Compose uses PostgreSQL.
- Any deviation requires a new ADR and explicit reviewer sign-off, per the
  frozen-scope governance rule.
