# G01 — Implementation Report

**Date (UTC):** 2026-10-11
**Group / status:** PASS_WITH_LIMITATION (Docker runtime unavailable in dev env; Compose file delivered as artifact, will be exercised end-to-end in G07)
**Repository / branch / HEAD before / HEAD after / clean tracked tree:**
- Repository: https://github.com/mayakilzy/AgentCraft-Engineering-Lab
- Branch: `main`
- HEAD before: (none — empty repo)
- HEAD after: `60ae26a6e4996a6d8ae49914fa7380e4889a27fd`
- Clean tracked tree: yes

## Tasks executed (IDs) and outputs

| Task | Output |
|---|---|
| T01 | Repo layout, ADR-0001 (stack pinning rationale), README, .gitignore, .env.example |
| T02 | FastAPI app (`app/main.py`) with CORS, X-Request-Id middleware, contract error body handlers (`app/core/errors.py`); `/api/v1/health/live` + `/api/v1/health/ready` (`app/api/v1/health.py`); Pydantic DTOs (`app/schemas/{common,health,session,experiment}.py`); modules registry interface (`app/services/modules_registry.py`); JSON logging (`app/core/logging.py`); OTEL hook placeholder (`app/core/telemetry.py`) |
| T03 | Vite + React 18 + TypeScript + Tailwind 3 shell (`frontend/`); 5 nav sections (Home, Graph Lab, Observability Lab, Experiments, History); i18next EN + AR with RTL flip (`src/i18n/`); skip link, keyboard focus ring; Vitest 6 tests |
| T04 | SQLAlchemy ORM (`app/models/{base,guest_session,experiment,run,graph}.py`) with platform-independent GUID TypeDecorator and JSONB-on-PostgreSQL / JSON-on-SQLite; Alembic env + initial reversible migration (`alembic/versions/0001_initial_schema.py`); starter fixture `starter-five-v1` (`app/fixtures/graph_seed.py`); Docker Compose `core` profile (postgres+api+web with healthchecks); backend + frontend Dockerfiles; nginx reverse-proxy config |

## Changed files (count, major paths)

68 files staged in the commit. Major paths:

```
backend/
  pyproject.toml, Dockerfile, alembic.ini
  alembic/{env.py, script.py.mako, versions/0001_initial_schema.py}
  app/
    main.py, config.py
    core/{errors,logging,telemetry}.py
    api/deps.py, api/v1/health.py
    db/session.py
    models/{base,guest_session,experiment,run,graph}.py
    schemas/{common,health,session,experiment}.py
    services/modules_registry.py
    fixtures/graph_seed.py
    tests/{conftest,test_health,test_errors,test_modules_registry,test_migrations}.py
frontend/
  package.json, vite.config.ts, tsconfig{,.node}.json
  tailwind.config.js, postcss.config.js, index.html, Dockerfile
  src/{main.tsx, App.tsx, api/client.ts, components/{NavBar,Footer}.tsx,
       pages/index.tsx, i18n/{index.ts, locales/{en,ar}.json}, styles/index.css}
  tests/{setup.ts, app.test.tsx}
infrastructure/
  compose/docker-compose.yml
  nginx/agentcraft.conf
docker-compose.yml  (top-level mirror for `docker compose -f docker-compose.yml`)
docs/adr/0001-tech-stack-pinning.md
README.md, .gitignore, .env.example
```

## Test evidence: exact commands, pass/fail counts, relevant logs

### Backend
```
$ cd backend && python3 -m pytest app/tests/ -v
collected 19 items
app/tests/test_errors.py            ....   [21%]
app/tests/test_health.py           ....   [42%]
app/tests/test_migrations.py        ...... [73%]
app/tests/test_modules_registry.py ..... [100%]
============================= 19 passed in 0.74s ==============================
```

### Frontend
```
$ cd frontend && npm run typecheck
> tsc --noEmit     # clean (no errors)

$ npm run build
> vite build       # 58 modules transformed, built in 1.47s
dist/index.html                   0.41 kB │ gzip:  0.28 kB
dist/assets/index-CZmFz2qg.css    7.91 kB │ gzip:  2.28 kB
dist/assets/index-BVbPrimZ.js   222.81 kB │ gzip: 71.80 kB

$ npm test
> vitest run
 ✓ tests/app.test.tsx (6 tests) 141ms
 Test Files  1 passed (1)
      Tests  6 passed (6)
```

### Combined total: **25 / 25 PASS**

## Acceptance gate IDs and evidence

| Gate | Evidence |
|---|---|
| A01 — Repo boot | Clean checkout on a fresh clone; documented startup in README; `/api/v1/health/live` returns 200 with `{status:ok, app}` (test `test_live_ok`); `/api/v1/health/ready` returns 200 with DB `up` (test `test_ready_includes_database`); request-id middleware echoes header (tests `test_request_id_*`) |
| A02 — Manifest schema (seed) | Modules registry interface implemented with fail-closed validation: duplicate-id and missing-id rejected with `InvalidStateError` (tests `test_duplicate_id_rejected`, `test_missing_id_rejected`). Concrete 10 manifests wired in G05; `GET /api/v1/modules` honestly returns `{count:0, ids:[]}` (test `test_modules_endpoint_empty`). |
| A03 — Graph (seed shape) | `starter-five-v1` fixture has 5 nodes / 4 directed edges, no dangling endpoints, declared `expected` matches reality (test `test_fixture_shape`); lookup is fail-closed (test `test_fixture_lookup_fail_closed`). |
| A09 — Gallery (seed shape) | `GET /api/v1/experiments` honestly returns `{count:0, ids:[]}` (test `test_experiments_endpoint_empty`). Ten manifests wired in G05. |
| A12 — Localization (seed shape) | EN + AR locales with RTL document-dir flip verified end-to-end (test `switches locale to Arabic and flips document dir to rtl`); technical labels (status codes, dataset keys) intentionally untranslated per spec. |
| A14 — Security (seed shape) | Contract error body shape enforced on 404/422/500 (tests `test_404_unknown_endpoint_shaped`, `test_validation_error_shaped_422`); CORS allow-origin only for trusted origins (test `test_cors_headers_present`); `x-request-id` minted when missing; no real secrets in `.env.example`. |
| A15 — Deployment (artifact) | `docker-compose.yml` YAML validated (`yaml.safe_load` OK); `core` profile wires postgres:16-alpine + api + web with healthchecks and resource limits; non-root backend user. **Runtime smoke BLOCKED in dev env** (no Docker daemon) — exercised end-to-end in G07. |

## Screenshots / API output references

No screenshots taken (headless environment). API evidence is captured in
pytest output above; raw responses can be reproduced with:

```
$ curl -s http://localhost:8000/api/v1/health/live
{"status":"ok","app":"AgentCraft Engineering Lab"}

$ curl -s -i http://localhost:8000/api/v1/health/ready
HTTP/1.1 200 OK
x-request-id: <minted>
{"status":"ready","services":{"database":{"state":"up","detail":"select 1 ok"}}, "app_env":"local"}
```

## Security and isolation evidence

- `.env.example` contains only placeholders; `.env` is gitignored.
- No AI provider key is committed; mentor provider defaults to `disabled`
  (deterministic fallback path; wired in G06).
- CORS allowlist is the only origins allowed; preflight tested.
- Guest session model carries an opaque random `cookie_token` (wired in G07);
  FK relationships use `ondelete=CASCADE` so cleanup is automatic.
- Non-root user in the backend Dockerfile (uid 1000).
- No arbitrary code/SQL/Cypher is accepted from the client in G01 surface
  (no execute endpoint wired yet; will be allowlisted operation handlers in G05).

## Optional integrations unavailable, honestly labelled

| Integration | Status | Honest label |
|---|---|---|
| Docker daemon | unavailable in dev env (sudo password required) | Compose file delivered; runtime smoke deferred to G07 |
| PostgreSQL native install | unavailable (apt sudo blocked) | Migration logic tested against SQLite via dialect-aware `GUID` TypeDecorator; PostgreSQL path is the production target |
| Neo4j + GDS | not yet wired | G03 |
| OTEL Collector + Prometheus + Tempo + Grafana | not yet wired | G04 |
| Mentor LLM provider | `disabled` by default | G06 |

## Unresolved defects with severity

None.

Known limitations (not defects):
- `pytest-asyncio` emits a deprecation warning about unset
  `asyncio_default_fixture_loop_scope`; cosmetic only, fixed by adding
  the option in `pyproject.toml` when async tests are added (G04+).
- React Router v6 prints future-flag warnings on the test console; cosmetic
  only; will be opted-in when migrating to v7 in a later ADR if needed.

## Scope-change violations: NONE

All work is within the frozen V1.0 scope and the G01 task definitions. No
new features, no microservices, no agents/swarm, no extra queue, no
arbitrary code execution surface introduced.

## Next group (DO NOT START)

**G02 — relational graph, NetworkX, Cytoscape (T05–T08; gates A03, A06).**

Awaiting reviewer approval before starting.

## Reviewer decision required: APPROVE / HOLD

**Requested: APPROVE** (or APPROVE_WITH_LIMITATION noting the Docker runtime
deferral, which is environmental, not architectural).
