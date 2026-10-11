# AgentCraft Engineering Lab

An open-source, hands-on learning laboratory for software engineers exploring
**graph intelligence** and **observability**. Users explore real working
examples, verify results, record runs, and ask a context-aware textual tutor
to diagnose failures.

> **Status:** V1.0 scope FROZEN. Sequential group delivery (G01 → G08).
> Current group: **G01 — Foundation and skeleton**.

---

## What this project is (and is not)

**It is:** a learning lab with ten canonical, deterministic experiments covering
graph modeling, shortest path, centrality, community detection, SQL/Cypher
parity, OpenTelemetry traces, Prometheus/Grafana dashboards, and failure
diagnosis.

**It is not:** a production OSINT tool, a monitoring surveillance system, a
general-purpose app factory, or a marketplace. See `docs/spec` (frozen spec
package) for the full scope and explicit exclusions.

---

## Repository layout

```
backend/             FastAPI + SQLAlchemy + Alembic (Python 3.12)
  app/
    api/v1/          REST endpoints (health, sessions, modules, runs, mentor, graph)
    core/            config, errors, logging, telemetry hooks
    models/          SQLAlchemy ORM models
    schemas/         Pydantic DTOs (request/response)
    services/        business logic + modules registry
    db/              engine/session factories
    tests/           pytest unit + integration tests
  alembic/           migrations (PostgreSQL dialect; SQLite-compatible subset for tests)
frontend/            React + TypeScript + Vite + Tailwind + i18next
  src/
    pages/           Home, Graph Lab, Observability Lab, Experiments, History
    components/      shared UI (mentor sidebar, stepper, etc.)
    i18n/            EN + AR locale resources
    api/             typed API client
lab-modules/         trusted module manifests + fixtures (graph, observability)
infrastructure/      Docker Compose, OTEL Collector, Prometheus, Tempo, Grafana
docs/                architecture, spec, ADRs
reports/             per-group implementation reports
```

---

## Quick start (local dev)

### Prerequisites
- Python 3.12+
- Node 20+ (tested on Node 24)
- Docker + Docker Compose (for full-stack runtime)

### Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head           # against SQLite for tests, or PostgreSQL via DATABASE_URL
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

### Full stack (Docker Compose, `core` profile)
```bash
docker compose --profile core up -d --build
# API:        http://localhost:8000
# Frontend:   http://localhost:8080
# PostgreSQL: localhost:5432
```

Observability stack (`observability` profile — wired in G04):
```bash
docker compose --profile observability up -d --build
# Grafana:    http://localhost:3000
# Prometheus: http://localhost:9090
# Tempo:      http://localhost:3200
```

---

## Configuration

Copy `.env.example` to `.env` and adjust. **No real secrets are committed.**
All AI provider keys are optional; the mentor has a deterministic fallback
when no provider is configured.

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./agentcraft.db` | Use `postgresql+psycopg2://...` for production |
| `APP_ENV` | `local` | `local` \| `demo` \| `production` |
| `SESSION_TTL_HOURS` | `24` | Guest session expiry |
| `MENTOR_PROVIDER` | `disabled` | `disabled` (deterministic) \| `openai` (server-side key only) |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:8080` | Trusted origins |
| `RUN_TIME_BUDGET_SECONDS` | `30` | Max wall-clock per lab operation |

---

## Testing

```bash
# Backend unit + integration
cd backend && pytest -q

# Frontend type-check + unit
cd frontend && npm run typecheck && npm test

# E2E (Playwright, added in later groups)
cd tests && npx playwright test
```

---

## Development protocol

1. Work one group at a time (G01 → G08), in task order within each group.
2. Commit after cohesive tasks; keep the working tree clean.
3. Run all relevant tests before completing a group.
4. Write `reports/GXX_report.md` using `contracts/GROUP_REPORT_TEMPLATE.md`.
5. **STOP** and await reviewer approval. Never silently start the next group.

---

## License

MIT (see `LICENSE`). Synthetic datasets are original and contain no personal
data. No external OSINT, scraping, or social profiling is performed.
