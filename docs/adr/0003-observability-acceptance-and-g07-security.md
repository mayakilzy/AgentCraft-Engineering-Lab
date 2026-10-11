# ADR-0003 — Observability acceptance conditions for E07–E09 + G07 deployment security

**Date:** 2026-10-11
**Status:** Accepted (G04-C1)
**Supersedes:** none
**References:** G04-C1 reviewer notes #3 + #4; `02_ARCHITECTURE_AND_CONTRACTS.md` §7 + §9; `05_DEPLOYMENT_AND_OPERATIONS.md`

## Context

G04-C1 reviewer identified two mandatory documentation gaps that must be
closed before G05 can start:

1. The link between `run_id` ↔ `trace_id` ↔ Grafana is a mandatory
   acceptance condition for experiments E07–E09 (trace one request,
   build monitoring dashboard, diagnose a hidden failure). The wiring
   plan must be recorded so the owning group knows exactly what to build.

2. G07 deployment security conditions (default passwords, admin port
   restrictions, `/metrics` protection) must be recorded as a checklist
   so the lockdown group has a concrete gate to verify.

This ADR records both without introducing code changes (G04-C1 is a
closure mission — no new features per reviewer note #6).

## Decision

### Part A — `run_id` ↔ `trace_id` ↔ Grafana wiring plan (E07–E09 acceptance)

The wiring is split across three groups per the original mission sequence:

| Wiring step | Owning group | What gets built |
|---|---|---|
| 1. `trace_id` stored on the `runs` table | **G05** (T17–T20) | When a run is created (`POST /api/v1/experiments/{id}/runs`), the handler captures the current span's `trace_id` (from `opentelemetry.trace.get_current_span().get_span_context().trace_id`) and stores it in the `runs.trace_id` column (already defined in the G01 migration). |
| 2. `GET /observability/links/{run_id}` returns the stored `trace_id` | **G05** | The endpoint (already implemented in G04-T15) currently returns `trace_id: null`. G05 replaces this with a DB lookup: `SELECT trace_id FROM runs WHERE id = $run_id AND session_id = $current_session`. The session-scoped WHERE clause preserves cross-session isolation (A08). |
| 3. Grafana deep-link uses the `trace_id` | **G05** | The `grafana_tempo_query` field already builds a Tempo explore URL. G05 substitutes the actual `trace_id` into the query template so the user can click through from the run record to Grafana Tempo. |
| 4. E07 validator asserts `trace_id` is present and the trace has ≥3 spans | **G05** | The `trace_demo_v1` validator (already implemented in G04-T16) is extended to also assert `run.trace_id is not None` — proving the run-to-trace correlation was wired. |
| 5. E09 validator asserts the failed run's `trace_id` + `fail_step` are both present | **G05** | The `failure_diagnosis_v1` validator is extended to assert the failed run has a non-null `trace_id` so the user can find the failing span in Grafana. |

**Acceptance condition (E07–E09):** experiments E07, E08, E09 cannot PASS
until steps 1–5 are complete. G04 delivered the instrumentation, the
metrics, the failure-injection operation, the validators, and the
observability endpoints. G05 delivers the run-persistence layer that
connects `run_id` to `trace_id`. When G05 is approved, the E07–E09
end-to-end flow is: user starts a run → run stores `trace_id` → user
opens `/observability/links/{run_id}` → sees the Grafana Tempo deep-link
→ clicks through → sees the trace with `run_id` as a span attribute.

**Current status (G04):** steps 1–5 are NOT yet wired. The
`trace_id` column exists on the `runs` table (G01 migration) but is
never populated (the runs endpoint doesn't exist yet — it lands in G05).
The `/observability/links/{run_id}` endpoint returns `trace_id: null`
with an honest note. This is the expected state at the end of G04.

### Part B — G07 deployment security checklist

The following conditions are MANDATORY for the G07 public-deployment
lockdown. Each must be verified with concrete evidence (not a claim):

| # | Condition | How to verify | Current state |
|---|---|---|---|
| 1 | No default passwords | `POSTGRES_PASSWORD`, `NEO4J_PASSWORD`, `GRAFANA_ADMIN_PASSWORD` must all be set to non-default values via environment variables (not checked into the repo). The `.env.example` must carry placeholders only. | `.env.example` has placeholders; Compose uses `${VAR:-default}` with a `changeme` default that MUST be overridden in production. G07 verifies the override is present. |
| 2 | Admin ports restricted | Prometheus (9090), Tempo (3200), OTEL Collector (4317/4318/8889) must NOT be exposed publicly. Only Grafana (3000) and the API (8000) + frontend (8080) have public ports. | Compose `observability` profile: only Grafana has `ports:` mapping; all others are network-only. G07 verifies no admin port is mapped. |
| 3 | `/metrics` protected from public access | The `/metrics` endpoint exposes internal route patterns (path_template labels). It must NOT be publicly accessible in production. Options: (a) reverse-proxy auth, (b) bind to internal network only, (c) rate-limit. | Currently `/metrics` is open. G07 adds a reverse-proxy rule that requires basic auth or blocks external access to `/metrics` while allowing Prometheus (on the private network) to scrape. |
| 4 | CORS locked to trusted origins | `CORS_ORIGINS` must list only the production frontend URL, not localhost. | `.env.example` has localhost defaults; G07 verifies the production env sets the real origin. |
| 5 | Session cookie `Secure` flag | `SESSION_COOKIE_SECURE=true` in production (HTTPS only). | Default is `false` for local dev; G07 verifies the production override. |
| 6 | Rate limiting on run creation | `POST /api/v1/experiments/{id}/runs` must be rate-limited per session+IP to prevent abuse. | `RATE_LIMIT_PER_MINUTE=60` is configured but not yet enforced on the runs endpoint (lands in G05). G07 verifies enforcement. |
| 7 | No secrets in env files | `.env` must be gitignored; `.env.example` carries only placeholders. | Verified since G01. G07 re-verifies. |
| 8 | Non-root containers | Backend Dockerfile uses `USER ac` (uid 1000). | Verified since G01. G07 re-verifies. |
| 9 | Resource limits on all containers | Each Compose service has `deploy.resources.limits.memory`. | Verified since G01 (core) + G04 (observability). G07 re-verifies. |
| 10 | Scheduled purge of guest sessions | A cron job or management command must purge expired `guest_sessions` + Neo4j namespace data (retention ≤24h). | Not yet implemented; G07 adds a `python -m app.cleanup_purge` management command and a cron schedule. |

**Acceptance condition (G07):** the public deployment CANNOT be approved
until all 10 conditions are verified with concrete evidence (command +
output or config snippet). Conditions 3, 6, and 10 require new code in
G07; the rest are config verification.

## Alternatives considered

- **Wire run_id↔trace_id in G04 instead of G05:** rejected because the
  runs table doesn't have any rows yet (the runs endpoint lands in G05).
  Wiring the correlation before the runs exist would be premature and
  untestable.
- **Protect `/metrics` with a hardcoded token in G04:** rejected because
  it's a deployment concern (G07), not an instrumentation concern (G04).
  Adding auth to `/metrics` now would require a new middleware + config,
  which is scope creep per reviewer note #6.

## Consequences

- G05 has a concrete wiring plan for steps 1–5; the `trace_id` column
  already exists, the observability endpoint already exists, the
  validators already exist — G05 just connects them.
- G07 has a 10-item security checklist with verification methods; items
  3, 6, 10 require new code, the rest are config verification.
- No code changes in this ADR (G04-C1 is documentation-only for notes
  #3 + #4).
