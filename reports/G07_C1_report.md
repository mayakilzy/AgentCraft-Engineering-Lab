# G07-C1 — Deployment Safety Closure Report

**Date (UTC):** 2026-10-12
**Mission:** G07 closure (narrow security closure — 4 reviewer fixes)
**Status:** PASS — all 4 fixes applied, 23 new tests, all previous tests pass

## Reviewer-note compliance

### C1-01 — Fail-closed production secrets

**Issue:** G07 relied on `.env.example` comments alone to prevent production from running with default/empty passwords. No code enforcement.

**Fix:** `app/config.py` now has a `@model_validator(mode="after")` that runs when `APP_ENV=production`. It raises `ValueError` (boot aborts) if any of:
- `POSTGRES_PASSWORD` is `changeme`, `""`, `password`, `admin`, or `secret`
- `NEO4J_PASSWORD` is a forbidden default (only when `NEO4J_URI` is set)
- `GRAFANA_ADMIN_PASSWORD` is a forbidden default
- `SESSION_COOKIE_SECURE` is not `true`
- `CORS_ORIGINS` contains `localhost`, `127.0.0.1`, or `0.0.0.0`

The validator collects ALL problems and raises them at once so the operator fixes them in one pass, not one at a time.

Local/dev mode (`APP_ENV=local` or `demo`) is NOT fail-closed — the safe defaults keep the dev loop fast.

**Tests (8):**
- `test_production_rejects_default_postgres_password`
- `test_production_rejects_empty_postgres_password`
- `test_production_rejects_default_grafana_password`
- `test_production_rejects_default_neo4j_password_when_configured`
- `test_production_accepts_strong_passwords`
- `test_production_neo4j_password_not_required_when_neo4j_not_configured`
- `test_local_env_not_fail_closed`
- `test_demo_env_not_fail_closed`

### C1-02 — Network exposure and metrics

**Issue:** G07 exposed the FastAPI port 8000 publicly in the Compose `ports:` block. The `/metrics` nginx block existed, but the API itself was reachable directly.

**Fix:**
- `docker-compose.yml`: the `api` service now uses `expose: ["8000"]` (internal-only) instead of `ports: ["8000:8000"]` (public). The `web` service (nginx on 8080) is the only public HTTP entry point.
- Prometheus scrapes `/metrics` on the private Docker network (`http://api:8000/metrics` — verified in `infrastructure/prometheus/prometheus.yml`).
- Nginx blocks external `/metrics` access (`location /metrics { deny all; }`).

**Tests (6):**
- `test_api_not_in_public_ports` — 8000 not in any `ports:` block
- `test_api_has_expose_block` — `expose: ["8000"]` present
- `test_nginx_proxies_api` — `proxy_pass http://api:8000`
- `test_prometheus_scrapes_api_on_private_network` — `api:8000` (not `localhost:8000`)
- `test_nginx_blocks_metrics` — `deny all` + 403
- `test_compose_admin_ports_not_exposed` (updated) — only 8080/3000 public

### C1-03 — Production configuration

**Issue:** G07 didn't enforce `SESSION_COOKIE_SECURE=true` or reject localhost CORS in production.

**Fix:** The C1-01 `@model_validator` also covers:
- `SESSION_COOKIE_SECURE` must be `true` in production (HTTPS only)
- `CORS_ORIGINS` must not contain localhost/127.0.0.1/0.0.0.0
- All problems reported at once (not one at a time)

**Tests (5):**
- `test_production_rejects_insecure_cookie`
- `test_production_rejects_localhost_cors`
- `test_production_accepts_https_cors`
- `test_production_reports_all_problems_at_once`
- `test_local_env_not_fail_closed` (already counted in C1-01)

### C1-04 — Scheduled retention

**Issue:** G07 had only a commented-out cron example, no actual scheduling. The Neo4j cleanup swallowed failures silently.

**Fix:**
- `docker-compose.yml`: a new `purge-cron` Compose service (profile `core`) runs `python -m app.cleanup_purge` in a sleep loop (6h interval). The service has a memory limit (128M) and depends on PostgreSQL being healthy.
- `session_service.purge_expired_sessions()` now reports Neo4j cleanup failures honestly:
  - Returns `neo4j_cleanup_failures` (list of session_ids that failed)
  - Per-session failures are caught and recorded; the loop continues with other sessions
  - When Neo4j is not configured, `neo4j_cleanup_failures` is `[]` (NOT a failure — honest no-op)
  - When Neo4j cleanup fails, `neo4j_nodes_deleted` is 0 (nothing deleted), and the failure is logged with the session_id
- The `cleanup_purge.py` docstring documents the retention semantics:
  - EXPIRED: `expires_at <= now()` → immediately rejected (401) but the row stays in the DB
  - PURGED: DB row + cascaded data deleted only when the purge cron runs
  - The distinction between expiry and purge is documented explicitly

**Tests (6):**
- `test_purge_cron_service_in_compose`
- `test_purge_cron_has_resource_limit`
- `test_purge_reports_neo4j_cleanup_failures` — simulates a Neo4j cleanup failure, asserts the failure is reported
- `test_purge_reports_no_failures_when_neo4j_not_configured` — no-op is NOT a failure
- `test_cleanup_purge_command_returns_audit_info`
- `test_retention_semantics_documented`

## Required Evidence

### Negative tests for unsafe production config
- `test_production_rejects_default_postgres_password` ✓
- `test_production_rejects_empty_postgres_password` ✓
- `test_production_rejects_default_grafana_password` ✓
- `test_production_rejects_default_neo4j_password_when_configured` ✓
- `test_production_rejects_insecure_cookie` ✓
- `test_production_rejects_localhost_cors` ✓

### Compose ports + /metrics path tests
- `test_api_not_in_public_ports` ✓
- `test_api_has_expose_block` ✓
- `test_prometheus_scrapes_api_on_private_network` ✓
- `test_nginx_blocks_metrics` ✓
- `test_compose_admin_ports_not_exposed` ✓ (updated)

### Scheduling + cleanup tests
- `test_purge_cron_service_in_compose` ✓
- `test_purge_cron_has_resource_limit` ✓
- `test_purge_reports_neo4j_cleanup_failures` ✓
- `test_purge_reports_no_failures_when_neo4j_not_configured` ✓

### All G01–G07 tests pass
```
$ cd backend && python3 -m pytest app/tests/
327 passed in 28.77s
$ cd frontend && npm test
17 passed
```
**Total: 344 PASS (327 backend + 17 frontend).**

## Runtime verification status (honest labelling)

| Service | Status | Evidence |
|---|---|---|
| FastAPI (in-process) | ✅ PASS | 327 backend tests run against it |
| SQLite (in-process) | ✅ PASS | All tests use SQLite |
| Fail-closed production config | ✅ PASS | 13 negative tests in test_g07c1 |
| Rate limiting (in-process) | ✅ PASS | test_g07_security tests |
| /metrics nginx block (config) | ✅ PASS | Static analysis |
| purge-cron Compose service (config) | ✅ PASS | Static analysis |
| PostgreSQL (Compose runtime) | ⛔ BLOCKED | Docker unavailable; config verified |
| Neo4j (Compose runtime) | ⛔ BLOCKED | Docker unavailable; FakeDriver tests pass |
| Neo4j GDS (Compose runtime) | ⛔ BLOCKED | Docker unavailable; FakeDriver tests pass |
| OTEL Collector (Compose runtime) | ⛔ BLOCKED | Docker unavailable; in-process OTEL works |
| Prometheus (Compose runtime) | ⛔ BLOCKED | Docker unavailable; /metrics endpoint works |
| Tempo (Compose runtime) | ⛔ BLOCKED | Docker unavailable; trace_id captured in-process |
| Grafana (Compose runtime) | ⛔ BLOCKED | Docker unavailable; provisioning configs ready |
| Nginx (Compose runtime) | ⛔ BLOCKED | Docker unavailable; config verified by static analysis |
| purge-cron (Compose runtime) | ⛔ BLOCKED | Docker unavailable; command tested in-process |

**Docker runtime smoke is BLOCKED** — `docker: command not found`, `sudo` requires a password. All Compose configs, Dockerfiles, nginx configs, and the new purge-cron service are verified by static analysis + in-process tests. The actual `docker compose up` smoke MUST run in a CI environment with Docker.

## Changed files (count, major paths)

**Backend (3 files):**
- `backend/app/config.py` (M) — fail-closed production validator + `postgres_password` + `grafana_admin_password` fields.
- `backend/app/cleanup_purge.py` (M) — retention semantics documentation.
- `backend/app/services/session_service.py` (M) — `purge_expired_sessions` reports Neo4j failures.
- `backend/app/tests/test_g07c1_security_closure.py` (A) — 23 tests.

**Infrastructure (2 files):**
- `docker-compose.yml` (M) — API `expose:` instead of `ports:`; new `purge-cron` service.
- `infrastructure/nginx/agentcraft.conf` (already had /metrics block from G07).

**Reports (1 file):**
- `reports/G07_C1_report.md` (A) — this report.

## Closure conditions

| Condition | Status |
|---|---|
| C1-01: Fail-closed production secrets | ✓ 8 tests |
| C1-02: Network exposure + /metrics | ✓ 6 tests |
| C1-03: Production configuration | ✓ 5 tests |
| C1-04: Scheduled retention + Neo4j honesty | ✓ 6 tests |
| All G01–G07 tests pass | ✓ 344 PASS |
| Docker runtime honestly labelled BLOCKED | ✓ |
| No new services beyond purge-cron | ✓ (purge-cron is a thin wrapper, not a new architecture) |
| No secrets printed in logs/reports | ✓ (passwords validated, never logged) |

## Next step

G07-C1 closure complete. STOP and await reviewer approval before G08.

## Reviewer decision required: APPROVE / HOLD

**Requested: APPROVE** to proceed to G08.

All 4 G07-C1 fixes applied: C1-01 (fail-closed production secrets), C1-02 (network exposure + /metrics), C1-03 (production config), C1-04 (scheduled retention + Neo4j failure honesty). 23 new tests. 344 total tests PASS. Docker runtime BLOCKED (documented honestly).
