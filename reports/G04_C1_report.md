# G04-C1 — Closure Report

**Date (UTC):** 2026-10-11
**Mission:** G04-C1 closure (fix P50/P95 calculation, document acceptance conditions, before G05 can start)
**Status:** PASS — all 6 mandatory notes addressed
**Repository / branch / HEAD before / HEAD after:**
- HEAD before: `6dd6802` (G04 report)
- HEAD after: `2afa77c` (G04-C1 fixes)
- Clean tracked tree: yes

## Reviewer-note compliance

### Note #1 — P50/P95 calculation fixed

**Bug:** The previous `get_metrics_summary` endpoint collected histogram
`_sum` values as if they were individual samples, then sorted them and
picked the median. This was incorrect: Prometheus histogram `_sum` is the
cumulative sum of all observation values for a label set, NOT a sample.
The "p50" and "p95" it produced were meaningless.

**Fix:** Added `_histogram_quantile(buckets, q)` that uses the histogram
bucket counts (`_bucket{le="..."}` samples) with linear interpolation —
the same algorithm Prometheus uses in `histogram_quantile()`. The function:
1. Sums bucket counts across all label sets into one combined histogram.
2. Finds the target rank = `q * total_count`.
3. Walks buckets from smallest `le` to largest, accumulating cumulative counts.
4. When cumulative first reaches the target, linearly interpolates within
   that bucket: `prev_le + (target - prev_count) / bucket_count * (le - prev_le)`.
5. Returns `None` when there are no observations or all counts are 0.

The endpoint's `note` field now explicitly says "P50/P95 computed from
histogram buckets via linear interpolation (approximate)".

### Note #2 — Tests with known latencies + empty state

10 new tests in `test_g04c1_quantiles.py`:

| Test | What it verifies |
|---|---|
| `test_quantile_empty_returns_none` | No buckets → None (empty state) |
| `test_quantile_zero_observations_returns_none` | Buckets exist but all 0 → None |
| `test_quantile_p50_single_bucket` | 10 obs in [0, 0.005] → p50 = 0.0025 (interpolated midpoint) |
| `test_quantile_p50_known_latency_30ms` | 10 obs at 30ms → p50 in [0.025, 0.05] bucket, ≈0.0375 |
| `test_quantile_p95_known_latency_mixed` | 20 obs (19 fast + 1 slow) → p95 in correct bucket |
| `test_quantile_p50_with_clear_buckets` | 5 fast + 5 slow → p50 at bucket boundary 0.005 |
| `test_metrics_summary_empty_state_returns_none` | Endpoint returns None when no observations |
| `test_metrics_summary_with_known_latencies` | Endpoint returns p50/p95 in correct bucket range |
| `test_metrics_summary_p50_lt_p95_with_mixed_latencies` | p50 < p95 for bimodal distribution |
| `test_metrics_summary_no_pii_in_response` | No session_id/cookie/authorization in response |

The endpoint tests use `monkeypatch` to control the `render_metrics()`
return value, so they're independent of the shared module-level registry
state (which accumulates across tests in the full suite).

### Note #3 — run_id ↔ trace_id ↔ Grafana acceptance condition documented

ADR-0003 Part A records the 5-step wiring plan for E07–E09 acceptance:

| Step | Owning group | What gets built |
|---|---|---|
| 1 | G05 | `runs.trace_id` column populated at run creation from the active OTEL span |
| 2 | G05 | `GET /observability/links/{run_id}` returns the stored `trace_id` (session-scoped DB lookup) |
| 3 | G05 | Grafana deep-link substitutes the actual `trace_id` into the Tempo explore URL |
| 4 | G05 | E07 validator (`trace_demo_v1`) asserts `run.trace_id is not None` |
| 5 | G05 | E09 validator (`failure_diagnosis_v1`) asserts the failed run has a non-null `trace_id` |

**Acceptance condition:** E07–E09 cannot PASS until steps 1–5 are complete.
G04 delivered the instrumentation, metrics, failure injection, validators,
and the observability endpoint (returning `trace_id: null` with an honest
note). G05 connects the run-persistence layer.

### Note #4 — G07 deployment security checklist

ADR-0003 Part B records 10 mandatory conditions for the G07 public-deployment
lockdown:

| # | Condition | Current state |
|---|---|---|
| 1 | No default passwords | `.env.example` has placeholders; Compose uses `${VAR:-changeme}` — G07 verifies override |
| 2 | Admin ports restricted | Only Grafana (3000) + API (8000) + web (8080) have public ports; Prometheus/Tempo/Collector are network-only |
| 3 | `/metrics` protected | Currently open — G07 adds reverse-proxy auth or blocks external access |
| 4 | CORS locked | `.env.example` has localhost; G07 verifies production origin |
| 5 | Secure cookie | Default `false` for dev; G07 verifies `true` in production |
| 6 | Rate limiting on runs | `RATE_LIMIT_PER_MINUTE=60` configured; enforcement on runs endpoint lands in G05 |
| 7 | No secrets in env | Verified since G01; G07 re-verifies |
| 8 | Non-root containers | Backend Dockerfile `USER ac`; G07 re-verifies |
| 9 | Resource limits | All Compose services have `deploy.resources.limits.memory` |
| 10 | Scheduled purge | G07 adds `app.cleanup_purge` management command + cron schedule |

### Note #5 — All tests pass

```
$ cd backend && python3 -m pytest app/tests/
============================== 164 passed in 6.56s ==============================

$ cd frontend && npm run typecheck   # clean
$ npm test                           # 12 passed
$ npm run build                      # ✓ built in 2.78s
```

**Combined: 164 backend + 12 frontend = 176 PASS.**

### Note #6 — No new features/services/architectural changes

Only 3 files changed:
- `backend/app/api/v1/observability.py` (fixed the quantile bug + added `_histogram_quantile`)
- `backend/app/tests/test_g04c1_quantiles.py` (new — 10 tests)
- `docs/adr/0003-observability-acceptance-and-g07-security.md` (new — documentation)

No new modules, endpoints, services, or dependencies.

## Closure conditions

| Condition | Status |
|---|---|
| P50/P95 uses histogram buckets, not `_sum` | ✓ `_histogram_quantile()` with bucket counts + linear interpolation |
| Tests with known latencies | ✓ 10 tests with deterministic bucket inputs |
| Empty state test | ✓ `test_quantile_empty_returns_none` + `test_metrics_summary_empty_state_returns_none` |
| run_id↔trace_id↔Grafana acceptance documented | ✓ ADR-0003 Part A |
| G07 security conditions documented | ✓ ADR-0003 Part B (10-item checklist) |
| All previous tests pass | ✓ 164 backend + 12 frontend |
| No new features/services/architecture | ✓ Only bug fix + tests + docs |

## Next step

G04-C1 closure complete. Awaiting reviewer approval to start **G05 —
Manifests, gallery, ten deterministic experiments (T17–T20; gates A02,
A09, A10)**.

## Reviewer decision required: APPROVE / HOLD

**Requested: APPROVE** to proceed to G05.
