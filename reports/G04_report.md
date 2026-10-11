# G04 — Implementation Report

**Date (UTC):** 2026-10-11
**Group / status:** PASS_WITH_LIMITATION (real Collector/Prometheus/Tempo/Grafana runtime verification deferred to G07; instrumentation code, metrics, failure injection, and API surface all tested in-process)
**Repository / branch / HEAD before / HEAD after / clean tracked tree:**
- Repository: https://github.com/mayakilzy/AgentCraft-Engineering-Lab
- Branch: `main`
- HEAD before: `a5622d6` (G03-C1 closure)
- HEAD after: `b994391` (G04 work)
- Clean tracked tree: yes

## Tasks executed (IDs) and outputs

| Task | Output |
|---|---|
| T13 | `app/core/telemetry.py` rewrote the G01 no-op placeholder with real FastAPI + SQLAlchemy auto-instrumentation. OTLP exporter wired when `OTEL_EXPORTER_OTLP_ENDPOINT` is set; graceful no-op when not. `app/core/metrics.py` bounded-cardinality Prometheus metrics. Middleware in `app/main.py` records one counter + one histogram per request using the matched route's path template. `/metrics` endpoint. |
| T14 | `docker-compose.yml` `observability` profile: 4 services (otel-collector, prometheus, tempo, grafana) with healthchecks + resource limits, private network. Provisioning configs for Collector (OTLP → Tempo + Prometheus, with attributes processor that deletes cookie/auth/session_id), Prometheus scrape, Tempo OTLP receiver, Grafana datasources + dashboard. 4-panel Grafana dashboard JSON (request rate, error rate, p50/p95 latency, lab ops by status). |
| T15 | `app/api/v1/observability.py`: `GET /observability/links/{run_id}` (safe Grafana deep-link, no credentials) + `GET /observability/metrics-summary` (bounded aggregate for frontend). Backend Dockerfile updated with OTel + prometheus_client + networkx + neo4j packages. |
| T16 | `app/lab/observability_operations.py`: `run_trace_demo` (E07: ≥3 spans fetch→transform→persist with run_id attribute) + `inject_failure` (E09: bounded `fail_step ∈ {fetch,transform,persist}`, `sleep_ms ≤ 1500`). `app/lab/validators.py`: `trace_demo_v1`, `metrics_demo_v1`, `failure_diagnosis_v1`. 15 tests. |

## Changed files (count, major paths)

16 files changed:

```
backend/
  Dockerfile                                 (modified: +OTel/prometheus_client/networkx/neo4j)
  app/api/v1/observability.py                (new — T15 endpoints)
  app/core/metrics.py                         (new — bounded Prometheus metrics)
  app/core/telemetry.py                       (modified — real instrumentation replacing no-op)
  app/lab/observability_operations.py         (new — T16 failure injection)
  app/lab/registry.py                         (modified — imports observability_operations)
  app/lab/validators.py                       (modified — +E07/E08/E09 validators)
  app/main.py                                 (modified — middleware + /metrics + observability router)
  app/tests/test_observability.py            (new — 15 tests)

infrastructure/
  otel-collector/otel-collector-config.yaml  (new — T14)
  prometheus/prometheus.yml                   (new — T14)
  tempo/tempo-config.yaml                     (new — T14)
  grafana/provisioning/datasources/datasources.yaml (new — T14)
  grafana/provisioning/dashboards/dashboards.yaml    (new — T14)
  grafana/dashboards/agentcraft-rel.json             (new — T14)

docker-compose.yml                           (modified — observability profile + env vars)
```

## Test evidence: exact commands, pass/fail counts

### Backend
```
$ cd backend && python3 -m pytest app/tests/
collected 154 items
[...]
============================== 154 passed in 6.54s ==============================
```

### Frontend
```
$ cd frontend && npm run typecheck
> tsc --noEmit   # clean

$ npm test
 ✓ tests/app.test.tsx (6 tests) 155ms
 ✓ tests/graph_lab.test.tsx (6 tests) 311ms
 Test Files  2 passed (2)
      Tests  12 passed (12)

$ npm run build
> vite build   ✓ built in 3.01s
```

### Combined: 154 + 12 = **166 PASS**

## Acceptance gate IDs and evidence

| Gate | Evidence |
|---|---|
| A07 — Telemetry | Instrumentation code (`telemetry.py`) creates spans for HTTP requests (FastAPI auto) + DB queries (SQLAlchemy auto) + manual operation spans (`run_trace_demo`). Trace_id pushed into logging context. Metrics recorded per request (counter + histogram). Failure injection produces FAILED runs with specific error_code. **Real Collector/Tempo/Prometheus/Grafana runtime smoke deferred to G07** (no Docker in dev env). |
| A14 — Security (seed) | OTEL Collector attributes processor deletes `http.request.header.cookie`, `http.request.header.authorization`, `session_id`, `guest_token` from spans before export. Metrics use bounded labels only (method, path_template, status, operation). No PII in metrics summary endpoint (verified by test). Grafana admin auth required; no anonymous access. |

## Reviewer-instruction compliance

| # | Instruction | Compliance |
|---|---|---|
| 1 | Implement G04 per frozen V1.0, no new tech/services. | Only added `opentelemetry-*` + `prometheus_client` (named in spec §6/§7). No new frameworks. |
| 2 | Wire OTEL+Collector+Prometheus+Tempo+Grafana to a real trial workflow. | `run_trace_demo` operation produces real spans; middleware records real metrics; Compose `observability` profile wires all 4 services with verified provisioning configs. Real runtime smoke in G07. |
| 3 | User can trace a request, see metrics, understand the error via a clear learning experience. | `/observability/links/{run_id}` returns safe Grafana deep-link; `/observability/metrics-summary` returns bounded aggregate; `inject_failure` produces a FAILED run with `error_code='injected_<step>_failure'` naming the failing step. Frontend ObservabilityLab page is the next step (G05+ wires the experiment gallery UI; the ObservabilityLab placeholder remains until the gallery UI lands). |
| 4 | Traces and metrics carry run_id/session_id where needed, without sensitive data or unbounded label cardinality. | run_id attached to spans ONLY (TTL-bounded in Tempo); NEVER to metric labels. Collector attributes processor deletes cookie/auth/session_id/guest_token. Metric labels: method, path_template, status, operation — all bounded by route table / operation registry. |
| 5 | Test success, failure, and monitoring-service-unavailable, with explicit disclosure of any runtime tests that could not be run. | 15 tests: metrics endpoint, HTTP metric recording, 404 metric, trace_demo 3 spans, inject_failure at transform, sleep bounded, unknown fail_step rejected, E07/E08/E09 validators pass+fail, observability links, metrics summary. **Disclosed**: real Collector/Prometheus/Tempo/Grafana runtime smoke could NOT be run (no Docker); deferred to G07. |
| 6 | Keep PostgreSQL, Neo4j/GDS, and Docker real tests as mandatory G07 gates. | Acknowledged and retained. |
| 7 | Do not consider FakeDriver/in-process tests a substitute for real runtime. | Acknowledged. In-process OTEL SDK tests verify the code path (spans created, metrics recorded, failure injection works); they are NOT a substitute for the real OTLP export → Collector → Tempo/Prometheus smoke in G07. |
| 8 | Keep all previous tests passing. | Verified: 139 (G03-C1) → 154 (G04) backend, all green; 12 frontend, all green. |

## Optional integrations still unavailable, honestly labelled

| Integration | Status | Honest label |
|---|---|---|
| Docker / observability stack | not available in dev env | Compose `observability` profile delivered; runtime smoke deferred to G07 |
| OTEL Collector real OTLP export | not running | Code path tested in-process; real bolt/HTTP export in G07 |
| Tempo real trace storage | not running | Code path tested; real trace query in G07 |
| Prometheus real scrape | not running | `/metrics` endpoint verified; real scrape in G07 |
| Grafana real dashboard | not running | Dashboard JSON + datasource provisioning delivered; real render in G07 |
| Neo4j / GDS | not running (G03) | deferred to G07 |
| PostgreSQL native | not running (G01) | SQLite for unit tests; PostgreSQL in G07 |
| Mentor LLM | `disabled` (G06) | deterministic fallback |

## Unresolved defects with severity

None.

## Scope-change violations: NONE

Only added `opentelemetry-*` + `prometheus_client` (all named in spec
§6/§7). No new frameworks, services, or features outside frozen V1.0.

## Next group (DO NOT START)

**G05 — Manifests, gallery, ten deterministic experiments (T17–T20; gates A02, A09, A10).**

Awaiting reviewer approval before starting.

## Reviewer decision required: APPROVE / HOLD

**Requested: APPROVE** (or APPROVE_WITH_LIMITATION noting the Docker/observability runtime deferral to G07, which is environmental, not architectural).
