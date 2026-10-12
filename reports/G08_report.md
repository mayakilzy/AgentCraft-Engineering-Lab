# G08 — Acceptance and Release Qualification Report

**Date (UTC):** 2026-10-12
**Mission:** G08 — Acceptance and release qualification
**Status:** PASS_WITH_LIMITATION — all qualification work complete; Docker runtime smoke BLOCKED (environmental); release gate CLOSED.

## Acceptance conditions compliance

### قبول-1 — Purge terminal failures stay visible

**Fix:** `purge_expired_sessions` now reports `failed_tasks_remaining` + `failed_task_ids` in the result. The `cleanup_purge` command returns exit 2 when failed tasks remain. A subsequent run cannot return exit 0 while failed tasks exist.

**Tests:**
- `test_purge_failed_tasks_stay_visible` — failed tasks remain in the table across runs
- `test_cleanup_purge_exit_2_with_failed_tasks` — exit 2 when failed tasks exist
- `test_cleanup_purge_exit_0_after_failed_resolved` — exit 0 after operator resolves

### قبول-2 — Retention semantics corrected

**Fix:** The `purge_expired_sessions` docstring now explicitly states:
- Default: 24h TTL + 6h purge = 30h worst-case (NOT a ≤24h guarantee)
- To guarantee ≤24h: set purge interval to ≤1h OR session_ttl_hours to ≤18h
- The guarantee does NOT hold during DB outages

**Tests:**
- `test_retention_no_24h_claim_in_docs` — no unconditional ≤24h claim
- `test_retention_outage_disclaimer` — outage disclaimer present
- `test_retention_default_ttl_is_24h` — default TTL is 24h

### قبول-3 — Neo4j namespace correctness

**Fix:** `purge_expired_sessions` now uses `neo4j_service.session_namespace()` (the SAME function as `cleanup_session` and `dataset_label`) to compute the namespace stored in `purge_tasks`. This guarantees the retry cleans up the correct nodes.

Also fixed `cleanup_session` to use the same `counters.nodes_deleted` attribute access pattern as the retry code.

**Tests:**
- `test_purge_namespace_matches_session_namespace` — the stored namespace matches `session_namespace()`
- `test_purge_cleans_only_target_session` — two sessions have different namespaces; A's prefix doesn't match B's label

### قبول-4 — E01–E10 full qualification

**Implementation:** `test_qualification_e01_e10_run_via_api` runs all 10 experiments via the API and verifies the status matches the qualification table.

| Experiment | Status | Evidence |
|---|---|---|
| E01 — Build Your First Graph | PASSED | `test_qualification_e01_e10_run_via_api` |
| E02 — Shortest Path | PASSED | per-step inputs (G06-PRE-01) |
| E03 — Interactive Graph Explorer | PASSED | filter + reset view |
| E04 — SQL vs Cypher | BLOCKED | Neo4j not configured (honest BLOCKED, not FAILED) |
| E05 — Critical Dependencies | PASSED | directed reachability |
| E06 — Discover Communities | PASSED | NetworkX fallback (GDS not licensed) |
| E07 — Trace One Request | PASSED | in-process OTEL, trace_id captured |
| E08 — Build Monitoring Dashboard | PASSED | metrics registry observations |
| E09 — Diagnose a Hidden Failure | PASSED | intentional failure + recovery demo |
| E10 — Integrated Challenge | PASSED | graph + telemetry integrated |

### قبول-5 — CI runtime evidence

**Implementation:** Created `.github/workflows/docker-smoke.yml` — a CI workflow that:
1. Builds all Docker images
2. Starts the core + observability + Neo4j profiles
3. Runs the backend test suite against PostgreSQL + Neo4j
4. Verifies data persistence (restart API, check session survives)
5. Verifies /metrics is blocked via Nginx (403)
6. Verifies purge-cron is running
7. Tears down

**Status:** The CI workflow file exists and is ready. It CANNOT run in the dev env (Docker unavailable). When pushed to a CI environment with Docker (e.g., GitHub Actions), it will execute the full runtime smoke.

### قبول-6 — Release honesty

**Implementation:** Updated README to document:
- Docker runtime verification is BLOCKED in the dev env
- All in-process code paths are tested
- The Compose runtime smoke must run in CI before the release gate opens
- **This project is NOT production-ready until the Docker runtime PASS is verified**

No V1.0 release tag exists (verified by `test_no_v1_release_tag`).

## Changed files

**Backend (4 files):**
- `backend/app/cleanup_purge.py` (M) — exit 2 on failed tasks + honest logging
- `backend/app/services/neo4j_service.py` (M) — fixed `cleanup_session` counters access + namespace doc
- `backend/app/services/session_service.py` (M) — namespace correctness + failed task reporting + docstring
- `backend/app/tests/test_g08_qualification.py` (A) — 16 qualification tests

**Infrastructure (1 file):**
- `.github/workflows/docker-smoke.yml` (A) — CI runtime smoke workflow

**Documentation (2 files):**
- `README.md` (M) — known limitations + not production-ready
- `reports/G08_report.md` (A) — this report

## Test evidence

### Backend tests
```
$ cd backend && python3 -m pytest app/tests/
363 passed in 30.42s
```

### Frontend tests
```
$ cd frontend && npm test
17 passed
```

### Frontend typecheck + build
```
typecheck: clean
build: ✓ built in 2.90s
```

### Combined
**380 tests PASS (363 backend + 17 frontend).**

## Acceptance gate status

| Gate | Description | Status | Evidence |
|---|---|---|---|
| A01 | Repo boot | ✅ PASS | 363 backend tests |
| A02 | Manifest schema | ✅ PASS | 10 manifests validate; malformed rejected |
| A03 | Graph | ✅ PASS | E01-E03 + E05 + E10 in-process |
| A04 | SQL/Cypher | ⛔ BLOCKED | Neo4j not configured (E04 BLOCKED) |
| A05 | GDS | ⛔ BLOCKED | GDS not licensed (E06 NetworkX fallback) |
| A06 | Visualizer | ✅ PASS | Cytoscape.js viewer + E03 |
| A07 | Telemetry | ✅ PASS (in-process) | OTEL spans created; Tempo/Grafana runtime BLOCKED |
| A08 | Demo isolation | ✅ PASS | Cross-session 404 tests |
| A09 | Gallery | ✅ PASS | 10 manifests, EN/AR, guided + challenge |
| A10 | Validation | ✅ PASS | Seeded success + bad input fails |
| A11 | Mentor | ✅ PASS | Grounded + deterministic + no cross-session leak |
| A12 | Localization | ✅ PASS | EN/AR full RTL, technical labels intact |
| A13 | Report | ✅ PASS | Export md/json + compare |
| A14 | Security | ✅ PASS | Fail-closed production + rate limiting + /metrics |
| A15 | Deployment | ⛔ BLOCKED | Docker runtime smoke BLOCKED (CI workflow ready) |
| A16 | Full walkthrough | ✅ PASS | E01-E10 all run via API |

## Runtime verification status (honest labelling)

| Service | Status | Evidence |
|---|---|---|
| FastAPI (in-process) | ✅ PASS | 363 backend tests |
| SQLite (in-process) | ✅ PASS | All tests use SQLite |
| Fail-closed production config | ✅ PASS | 13 + 6 tests |
| purge_tasks recoverable cleanup | ✅ PASS | 4 + 3 tests |
| E01–E10 qualification | ✅ PASS | 10 experiments via API |
| CI workflow file | ✅ READY | `.github/workflows/docker-smoke.yml` |
| PostgreSQL (Compose runtime) | ⛔ BLOCKED | Docker unavailable; CI workflow ready |
| Neo4j (Compose runtime) | ⛔ BLOCKED | Docker unavailable; FakeDriver tests pass |
| Neo4j GDS (Compose runtime) | ⛔ BLOCKED | Docker unavailable; FakeDriver tests pass |
| OTEL Collector (Compose runtime) | ⛔ BLOCKED | Docker unavailable; in-process OTEL works |
| Prometheus (Compose runtime) | ⛔ BLOCKED | Docker unavailable; /metrics endpoint works |
| Tempo (Compose runtime) | ⛔ BLOCKED | Docker unavailable; trace_id captured in-process |
| Grafana (Compose runtime) | ⛔ BLOCKED | Docker unavailable; provisioning configs ready |
| Nginx (Compose runtime) | ⛔ BLOCKED | Docker unavailable; config verified by static analysis |
| purge-cron (Compose runtime) | ⛔ BLOCKED | Docker unavailable; command tested in-process |

## Release gate

**CLOSED.**

The release gate remains CLOSED until the Docker runtime smoke (A15) PASS is verified in a CI environment with Docker. The CI workflow file is ready (`.github/workflows/docker-smoke.yml`). When it runs and passes, the release gate can open.

**This project is NOT production-ready.** The README documents this limitation clearly.

## Scope-change violations: NONE
- No new services, no new dependencies, no new architectural decisions.
- The CI workflow is a standard GitHub Actions file (no new framework).
- The namespace fix uses an existing function (`session_namespace`).
- The failed-task reporting uses the existing `purge_tasks` table.

## Reviewer decision required: APPROVE / HOLD

**Requested: APPROVE** for the qualification work (G08). The release gate remains CLOSED until the Docker runtime PASS is verified in CI.

All G08 acceptance conditions addressed:
- قبول-1: failed tasks stay visible (exit 2)
- قبول-2: retention semantics corrected (no false ≤24h claim)
- قبول-3: Neo4j namespace correctness (uses `session_namespace()`)
- قبول-4: E01–E10 qualification table (9 PASSED + 1 BLOCKED)
- قبول-5: CI workflow file ready (Docker BLOCKED in dev env)
- قبول-6: release honesty (README + no V1.0 tag)

380 tests PASS. Typecheck clean. Build succeeds. No scope violations.
