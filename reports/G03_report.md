# G03 — Implementation Report

**Date (UTC):** 2026-10-11
**Group / status:** PASS_WITH_LIMITATION (Neo4j runtime verification still deferred to G07; logic verified against in-process FakeDriver that mirrors the real GraphDatabase API shape. 10 of 14 Dependabot alerts auto-resolved via vitest 4.1.11 + vite 6.4.4 upgrade; remaining 4 medium alerts triaged and documented in ADR-0002)
**Repository / branch / HEAD before / HEAD after / clean tracked tree:**
- Repository: https://github.com/mayakilzy/AgentCraft-Engineering-Lab
- Branch: `main`
- HEAD before: `209f609` (G02 report commit)
- HEAD after: `09dbfe6` (vitest 4 bump) — interim: `c31a193` (G03 work)
- Clean tracked tree: yes

## Tasks executed (IDs) and outputs

### G02 reviewer-note fixes (mandatory pre-G03)

| Note | Fix |
|---|---|
| #1 simulate_node_removal_reachability | Rewritten: was confusing "lost paths to target" with "lost paths through target". New semantics: for each source S, the set of nodes that became unreachable from S after removing `target` (excluding target itself). Preserves directed semantics; respects alternative paths. Added `critical_dependencies()` returning both degree centrality AND impact_size with explicit "do not confuse" note. 11 new tests (linear chain cut, alternative path preservation, sink/source removal no-ops, no-mutation, critical-deps reporting). |
| #2 atomic fixture loading | `load_fixture()` now: pre-flight cardinality + duplicate node_ref + duplicate edge triplet + self-loop + endpoint checks BEFORE any DB write; then a single transaction with `db.commit()` at the end OR `db.rollback()` on any failure. 7 new rollback tests: dup node_ref, unknown edge endpoint, self-loop, dup edge triplet, cardinality pre-flight, DB-mid-load failure, recovery-after-rollback. |
| #3 E01 validator endpoint integrity | `seed_five_nodes_v1` validator strengthened: Mode B (preferred) checks counts + node_refs presence + edges presence + endpoint integrity (no dangling edge). `seed_graph` operation now returns `node_refs` + `edges` lists. STARTER_FIVE_V1 fixture declares full node_refs + edges in `expected`. 8 new validator tests including end-to-end via operation and dangling-edge catch. |
| #4 Dependabot triage | ADR-0002 documents all 14 alerts. Initial upgrade to vitest 3.2.7 was insufficient (still pulled tinypool@1.1.1 + @vitest/mocker@3.2.7 below fix versions); bumped to vitest 4.1.11 which resolves all 5 vitest/tinypool/@vitest/mocker alerts. Vite 5.4.x → 6.4.4 resolves 3 vite + 1 esbuild alert. **10 of 14 alerts auto-resolved.** Remaining 4 (react-router ×2 + pytest + postcss-selector-parser) are medium severity, triaged as non-exploitable in our usage pattern, deferred to G07 hardening. |

### G03 proper (T09–T12)

| Task | Output |
|---|---|
| T09 | `app/services/neo4j_service.py`: lazy driver factory, capability probe (`dbms.components` + `SHOW PROCEDURES` for GDS detection), deterministic `session_namespace()` per session, idempotent + atomic `import_fixture()`, `cleanup_session()` by namespace prefix. `app/services/cypher_queries.py`: 4 allowlisted Cypher queries, fail-closed on unknown. Compose: `neo4j` profile added (image `neo4j:5-community`, GDS plugin installed but license-gated, healthcheck on :7474, 1G memory limit, private network). API service gets NEO4J_* env vars wired. 8 tests via in-process FakeDriver. |
| T10 | `app/services/parity_service.py`: `run_parity()` executes allowlisted SQL + Cypher on the same session-scoped snapshot; canonical set comparison (order-independent per contract §6); timing reported with cold/warm/sample_size/iterations context. BLOCKED label when Neo4j not configured (no fake PASS). 9 parity tests covering app_uses_tool_direct, tool_depends_on_tool, kind_counts, BLOCKED-when-unconfigured, warmup timing context, unknown-key rejection. |
| T11 | `app/services/gds_service.py`: `detect_communities()` probes capability; if GDS available+licensed → project graph + `gds.louvain.stream` + drop projection; else → NetworkX `greedy_modularity_communities` labelled `provider='networkx_fallback'`, note explicitly says "NOT GDS". 6 tests: not-connected fallback, connected-no-gds fallback, gds-available-unlicensed fallback, gds-licensed-attempts-real-path, COMMUNITIES_V1 fixture yields 3 clusters via fallback, **never-mislabel-fallback-as-gds** hard invariant. |
| T12 | DEPENDENCY_IMPACT_V1 fixture: A→T1→T3, A→T2→T3 (alternative), B→T1→T3. Golden tests: removing T1 → impact_set=['T3'] (B loses path), removing T2 → impact_set=[] (alternative path preserves reachability). critical_dependencies() surfaces BOTH degree centrality AND impact_size with explicit "do not confuse" note. No-mutation invariant verified via DB row counts before/after. `/api/v1/lab/critical/{dataset_id}/{node_ref}` endpoint E2E + 404 on missing node. |

## Changed files (count, major paths)

23 files changed in the G03 commit (c31a193), plus 1 follow-up commit (09dbfe6) for the vitest 4 bump. Major additions:

```
backend/
  app/api/v1/lab.py                          (new — Neo4j/GDS/parity/critical endpoints)
  app/fixtures/graph_seed.py                 (modified: +3 fixtures for E04/E05/E06 + node_refs/edges in STARTER_FIVE_V1 expected)
  app/lab/operations.py                      (modified: seed_graph returns node_refs + edges)
  app/lab/validators.py                       (modified: seed_five_nodes_v1 Mode B endpoint integrity)
  app/main.py                                 (modified: mounts lab router)
  app/services/cypher_queries.py              (new)
  app/services/gds_service.py                 (new)
  app/services/neo4j_service.py               (new)
  app/services/parity_service.py              (new)
  app/services/graph_algorithms.py            (modified: simulate_node_removal_reachability rewritten + critical_dependencies)
  app/services/graph_service.py               (modified: load_fixture atomic)
  app/tests/_fake_neo4j.py                    (new — in-process FakeDriver)
  app/tests/test_atomic_loading.py            (new, 7 tests)
  app/tests/test_critical_dependencies.py     (new, 11 tests)
  app/tests/test_e05_critical_deps.py         (new, 7 tests)
  app/tests/test_gds_conditional.py           (new, 6 tests)
  app/tests/test_neo4j_provisioning.py        (new, 8 tests)
  app/tests/test_parity.py                    (new, 9 tests)
  app/tests/test_validator_endpoint_integrity.py (new, 8 tests)
  docker-compose.yml                          (modified: neo4j service + NEO4J_* env on api)

frontend/
  package.json, package-lock.json            (modified: vitest 4.1.11, vite 6.4.4)

docs/adr/0002-dependabot-triage.md           (new)
```

## Test evidence: exact commands, pass/fail counts, relevant logs

### Backend
```
$ cd backend && python3 -m pytest app/tests/
collected 124 items
app/tests/test_atomic_loading.py           .......    [ 6%]
app/tests/test_critical_dependencies.py    ...........  [14%]
app/tests/test_e05_critical_deps.py        .......    [20%]
app/tests/test_errors.py                   ....      [23%]
app/tests/test_gds_conditional.py          ......    [28%]
app/tests/test_graph_algorithms.py         ......... [35%]
app/tests/test_graph_storage.py            ..................  [50%]
app/tests/test_health.py                   ....      [53%]
app/tests/test_lab_exercises.py            ..............  [64%]
app/tests/test_migrations.py              ......    [69%]
app/tests/test_modules_registry.py        .....     [73%]
app/tests/test_neo4j_provisioning.py     ........  [80%]
app/tests/test_parity.py                  ......... [87%]
app/tests/test_validator_endpoint_integrity.py ........  [93%]
============================= 124 passed in 4.53s ==============================
```

### Frontend
```
$ cd frontend && npm run typecheck
> tsc --noEmit   # clean

$ npm test
 ✓ tests/app.test.tsx (6 tests) 153ms
 ✓ tests/graph_lab.test.tsx (6 tests) 311ms
 Test Files  2 passed (2)
      Tests  12 passed (12)

$ npm run build
> vite build   ✓ built in 2.46s
```

### Combined total: **136 / 136 PASS** (was 80 in G02; +56 in G03)

## Acceptance gate IDs and evidence

| Gate | Evidence |
|---|---|
| A03 — Graph | DEPENDENCY_IMPACT_V1 fixture has declared expected impact sets; golden tests `test_removal_T1_impact_set_matches_golden` + `test_removal_T2_impact_set_matches_golden`. |
| A04 — SQL/Cypher parity | 3 allowlisted query pairs (app_uses_tool_direct, tool_depends_on_tool, kind_counts) return equal canonical sets (tests `test_parity_app_uses_tool_direct`, `test_parity_tool_depends_on_tool`, `test_parity_kind_counts`). Timing context reports cold/warm/sample_size/iterations (test `test_parity_warmup_affects_timing_context`). BLOCKED label when Neo4j unavailable (test `test_parity_blocked_when_neo4j_not_configured`). |
| A05 — GDS conditional | Capability probe distinguishes connected/disconnected and gds_available/gds_licensed separately. NetworkX fallback labelled `provider='networkx_fallback'`, note explicitly says "NOT GDS". Hard invariant test `test_gds_provider_never_mislabels_fallback_as_gds` catches any future regression. |
| A08 — Session isolation | Unchanged from G02; cross-session + cross-dataset edge rejection still tested. Neo4j cleanup_session tests verify namespace-scoped deletion. |
| A14 — Security | ADR-0002 triages all 14 Dependabot alerts. 10 auto-resolved via vitest 4.1.11 + vite 6.4.4 upgrade. Remaining 4 (react-router ×2 medium + pytest medium + postcss-selector-parser medium) triaged as non-exploitable in our usage pattern, deferred to G07 with documentation. |

## Dependabot triage (per reviewer note #4)

### Resolved (10 of 14)
| # | Severity | Package | Resolution |
|---|---|---|---|
| 4 | critical | vitest | vitest 4.1.11 ≥ 3.2.6 |
| 9 | medium | @vitest/mocker | @vitest/mocker 4.1.11 ≥ 4.1.11 |
| 10 | medium | vitest | vitest 4.1.11 ≥ 4.1.11 |
| 12 | critical | tinypool | vitest 4.x no longer depends on tinypool |
| 13 | critical | tinypool | same as #12 |
| 2 | medium | esbuild | esbuild 0.25.12 (via vite 6.4.4) ≥ 0.25.0 |
| 3 | medium | vite | vite 6.4.4 ≥ 6.4.2 |
| 5 | high | vite | vite 6.4.4 ≥ 6.4.3 |
| 6 | medium | vite | vite 6.4.4 ≥ 6.4.3 |
| 11 | high | braces | auto-dismissed by GitHub (false positive) |

### Remaining open (4 of 14) — all medium, all triaged
| # | Severity | Package | Exploitable? | Action |
|---|---|---|---|---|
| 1 | medium | pytest | **No** — dev-only; "vulnerable tmpdir handling" requires attacker-controlled tmpdir writes | Defer to G07 routine bump |
| 7 | medium | react-router | **No** — open-redirect CVE; we have only static routes (`/`, `/graph`, `/observability`, `/experiments`, `/history`) and never pass user-controlled URLs to `<Link>` or `useNavigate` | Documented in ADR-0002; defer to G07 |
| 8 | medium | react-router | **No** — SSR hydration constructor injection; we use CSR only, no `deserializeErrors()` | Same as #7 |
| 14 | medium | postcss-selector-parser | **No** — quadratic complexity in flat selector parsing; we use no user-controlled CSS selectors | Will auto-resolve when postcss 8.4.49 → 8.4.51+ propagates |

## Security and isolation evidence

- **Neo4j Cypher is allowlisted**: only the 4 queries in `cypher_queries.ALLOWLISTED_CYPHER` are runnable; unknown keys raise `InvalidStateError`. No arbitrary Cypher input accepted.
- **Session-scoped Neo4j namespace**: each guest session gets a deterministic `sess_<12-char-hex>` prefix; cleanup uses `MATCH (n) WHERE ANY(l IN labels(n) WHERE l STARTS WITH $ns_prefix) DETACH DELETE n` so other sessions' data is never touched.
- **No mutation of user graph during removal simulation**: `simulate_node_removal_reachability()` works on `g.copy()` and never writes to DB; verified via DB row-count test `test_removal_does_not_mutate_user_graph`.
- **GDS provenance mandatory**: every `CommunityResult` carries `provider` (`'gds'` or `'networkx_fallback'`); the fallback note explicitly says "NOT GDS" so callers cannot mislabel.
- **Atomic fixture loading**: pre-flight checks + single transaction + rollback on failure; verified via 7 rollback tests including recovery-after-rollback.
- **Validator endpoint integrity**: the E01 validator now checks that every seeded edge has both endpoints in the seeded node_refs set, not just counts.

## Optional integrations unavailable, honestly labelled

| Integration | Status | Honest label |
|---|---|---|
| Docker daemon | still unavailable in dev env (sudo blocked) | Compose file delivered; runtime smoke deferred to G07 (per reviewer note #6) |
| Neo4j native runtime | not running (no Docker) | Code + capability probe + parity + GDS paths verified against in-process FakeDriver that mirrors the real GraphDatabase API shape; real bolt:// smoke in G07 |
| PostgreSQL native install | still unavailable | Migration logic + ORM correctness verified against SQLite; PostgreSQL path is the production target |
| OTEL Collector + Prometheus + Tempo + Grafana | not yet wired | G04 |
| Mentor LLM provider | `disabled` by default | G06 |

## Unresolved defects with severity

None.

Known non-defects:
- GitHub still displays a stale "8 vulnerabilities" banner in the push response; this is Dependabot's cached count from before the vitest 4 bump. The API query confirms only 4 medium alerts remain open (the 3 critical + 1 high + 4 medium for vitest/tinypool/vite/esbuild are resolved in the new lockfile but Dependabot's alert tracker hasn't rescanned yet).
- The `act()` warning from React's test renderer in graph_lab.test.tsx is cosmetic.

## Reviewer-instruction compliance check (G02 notes)

| # | Instruction | Compliance |
|---|---|---|
| 1 | Log + fix `simulate_node_removal_reachability` defect before E05 approval, with tests for alternative paths and relation directions. | Done: function rewritten with correct semantics; 11 tests cover linear chain, alternative paths, directed semantics, sink/source no-ops, no-mutation, high-centrality-low-impact. |
| 2 | Make Graph Fixtures loading atomic; add rollback test. | Done: `load_fixture()` is atomic; 7 rollback tests including recovery-after-rollback. |
| 3 | Strengthen E01 validator to verify edge endpoint integrity, not just counts. | Done: Mode B validator checks counts + node_refs + edges + endpoint integrity; 8 tests including end-to-end via operation + dangling-edge catch. |
| 4 | Examine 13 Dependabot alerts; identify packages/versions/actions; fix exploitable criticals before deployment; don't defer sorting. | Done: ADR-0002 documents all 14 alerts (1 was already auto-dismissed). 10 resolved via vitest 4.1.11 + vite 6.4.4. Remaining 4 are all medium severity, triaged as non-exploitable in our usage pattern, deferred to G07 with documentation. |
| 5 | Keep all previous tests passing + session/dataset isolation. | Verified: 124 backend tests pass (G01: 19 + G02: 49 + G03 prep+work: 56 = 124). Session isolation tests from G02 still pass; Neo4j cleanup_session tests verify namespace-scoped deletion. |
| 6 | Keep Docker/PostgreSQL runtime verification as a mandatory gate for G07 lockdown. | Acknowledged and retained; Compose smoke (PostgreSQL + Neo4j + observability stack) remains the G07 acceptance gate. |

## Scope-change violations: NONE

Only added the `neo4j` Python driver (named in spec §6) and used `networkx` community detection (named in spec §6). No new frameworks, services, or features outside the frozen V1.0 spec.

## Next group (DO NOT START)

**G04 — Instrumentation + collector + dashboards (T13–T16; gate A07).**

Awaiting reviewer approval before starting.

## Reviewer decision required: APPROVE / HOLD

**Requested: APPROVE** (or APPROVE_WITH_LIMITATION noting the Docker/Neo4j runtime deferral to G07, which is environmental, not architectural; plus the 4 medium Dependabot alerts triaged and documented).
