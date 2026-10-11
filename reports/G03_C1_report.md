# G03-C1 — Closure Report

**Date (UTC):** 2026-10-11
**Mission:** G03-C1 closure (fix GDS path issues before G04 can start)
**Status:** PASS — all 7 mandatory notes addressed; all closure conditions met
**Repository / branch / HEAD before / HEAD after / clean tracked tree:**
- Repository: https://github.com/mayakilzy/AgentCraft-Engineering-Lab
- Branch: `main`
- HEAD before: `1f09a89` (G03 report)
- HEAD after: `da5bfaa` (G03-C1 fixes)
- Clean tracked tree: yes

## Reviewer-note compliance

### Note #1 — GDS Graph Projection uses supported interface

**Problem:** The old code in `gds_service.detect_communities` attempted:
```python
s.run(
    "CALL gds.graph.project("
    "$name, "
    "MATCH (n:`__{label}__`) RETURN id(n) AS id, n.kind AS kind, "
    "MATCH (n:`__{label}__`)-[r]->(m:`__{label}__`) "
    "RETURN id(n) AS source, id(m) AS target, type(r) AS type".format(label=label),
    name=graph_name,
)
```
This is malformed: `gds.graph.project` is a procedure that takes
`(graphName, nodeSpec, relationshipSpec)` as strings/parameters, NOT
Cypher subqueries. The `.format()` call also risked KeyError on the
`{kind: ...}` block inside backticks (a Cypher map literal, not a Python
format placeholder).

**Fix:** The projection now uses the documented 3-argument signature:
```python
sess.run(
    "CALL gds.graph.project($name, $nodeLabel, '*')",
    name=graph_name,
    nodeLabel=full_label,
)
```
- `nodeSpec` = the session-scoped label (parameterised as `$nodeLabel`).
- `relationshipSpec` = `'*'` projects all relationship types whose both
  endpoints carry the projected label. GDS does this automatically;
  cross-label relationships are excluded, preserving session/dataset isolation.

**Test evidence:** `test_gds_projection_uses_supported_3arg_signature` asserts
the query string starts with `CALL gds.graph.project`, contains `$name` and
`$nodeLabel` (not string-interpolated), contains `'*'`, and does NOT contain
the old broken `MATCH (n:` inline subquery pattern.

### Note #2 — Unified label naming

**Problem:** The label format `__<namespace>__<ds_label>__` was constructed
inline in 3 places:
- `neo4j_service.import_fixture` (line 195-196)
- `gds_service.detect_communities` (line 77 — WRONG format, missing `__`
  wrapping and `ds_` prefix)
- `parity_service.run_parity` (line 156-158)

The gds_service version produced a different label string than import_fixture,
so the projection would read from an empty namespace.

**Fix:** Added `neo4j_service.dataset_label(session_id, dataset_id) -> str`
as the single source of truth. All 3 call sites now use this function. No
new abstraction layer — just one small shared function replacing 3 inline
duplications.

**Test evidence:** `test_g03c1_label_consistency.py` (8 tests) covers:
- format correctness (`__sess_<12hex>__ds_<sanitized>__`)
- determinism per (session_id, dataset_id)
- differentiation per session and per dataset
- dash sanitization
- import_fixture stores under the helper's label
- parity_service issues Cypher against the helper's label
- gds_service projects with `nodeLabel == dataset_label()` result

### Note #3 — Louvain on correct projection + correct nodeId→node_ref

**Problem:** Even if the projection had been created correctly, the
`ref_rows` lookup used `.format(label=label)` with the WRONG label (the
gds_service local `label` variable, not `full_label`). The
`id_to_ref` map would be empty, so `id_to_ref.get(nid)` returned None
for every Louvain row, producing empty communities.

**Fix:** With the unified label, the ref-lookup query
`MATCH (n:`<full_label>`) RETURN id(n) AS id, n.ref AS ref` reads from
the same label the projection was built from. The `id(n)` values returned
by the ref-lookup match the `nodeId` values returned by
`gds.louvain.stream` (both are Neo4j internal ids for the same nodes).

**Test evidence:**
- `test_gds_louvain_runs_on_correct_projection` asserts the Louvain query
  parameter `name == g_<full_label>`.
- `test_gds_success_path_returns_actual_node_refs` asserts every community
  member is a `str` (node_ref like `'A1'`), not an internal integer id;
  the union of all community members equals the fixture's declared node set.

### Note #4 — Guaranteed projection cleanup in finally

**Problem:** The old code called `gds.graph.drop` inside the `with` block
but NOT in a `finally`. If `gds.louvain.stream` raised, the projection
was leaked in the GDS graph catalog.

**Fix:** The projection lifecycle is now:
```python
sess = driver.session(database=...)
try:
    sess.run("CALL gds.graph.project(...)")  # may raise
    try:
        louvain_result = sess.run("CALL gds.louvain.stream(...)")  # may raise
        ref_result = sess.run("MATCH (n:...) RETURN id(n), n.ref")  # may raise
        # ... build communities ...
        return CommunityResult(provider="gds", ...)
    finally:
        # GUARANTEED cleanup — runs even when Louvain raises.
        try:
            sess.run("CALL gds.graph.drop($name, false)", name=graph_name)
        except Exception as cleanup_exc:
            log.warning("gds projection cleanup failed", ...)  # never mask original
except Exception as exc:
    return _networkx_fallback(...)  # fall back honestly
finally:
    sess.close()  # always close the driver session
```

**Test evidence:**
- `test_gds_projection_cleanup_runs_on_success` — drop query issued once,
  projection removed from store.
- `test_gds_projection_cleanup_runs_on_louvain_failure` — uses
  `_LouvainFailingFakeDriver` where Louvain raises; drop query STILL
  issued once; projection removed from store (no leak); result falls back
  to NetworkX honestly.
- `test_gds_projection_failure_falls_back_to_networkx` — uses
  `_ProjectionFailingFakeDriver` where projection itself raises; NO drop
  query issued (projection never created); result falls back to NetworkX.

### Note #5 — Strengthened FakeDriver + GDS tests

**Problem:** The old FakeDriver pattern-matched queries but tests only
asserted on function-call outcomes, not on query structure or parameters.
This made it impossible to catch regressions like the malformed projection
call.

**Fix:**
- FakeDriver now records EVERY `(query, params)` tuple on the session's
  `queries_run` list.
- Added `_RecordingFakeDriver` variant that captures queries across ALL
  sessions into a shared `_shared_queries` list (needed because the
  service opens a new session per call).
- Tests now assert on:
  - Query prefix (`CALL gds.graph.project`, `CALL gds.louvain.stream`,
    `CALL gds.graph.drop`)
  - Parameter presence (`$name`, `$nodeLabel`)
  - Parameter VALUES (`name == g_<full_label>`, `nodeLabel == full_label`)
  - Query body structure (no old broken `MATCH (n:` inline subquery)
- All G03-C1 test docstrings explicitly state: "These tests exercise the
  SERVICE CODE PATH against an in-process FakeDriver. They verify the
  Cypher query structure and parameters the service issues, NOT real Neo4j
  runtime behavior. The real Neo4j/GDS smoke is mandatory for G07 lockdown."

### Note #6 — NetworkX fallback not counted as GDS success

**Problem:** The fallback was already labelled `provider='networkx_fallback'`
with a "NOT GDS" note, but there was no explicit test asserting that a
fallback result is never counted as a GDS success.

**Fix:** Added `test_networkx_fallback_not_counted_as_gds_success` — a
hard invariant test. It forces a fallback (gds_licensed=False) and asserts:
- `result.provider == 'networkx_fallback'`
- `result.provider != 'gds'`
- The note contains "NOT GDS" and "do not certify native GDS behavior"

The existing `test_gds_provider_never_mislabels_fallback_as_gds` from G03
is also retained.

### Note #7 — No regression

**Verification:**
- Backend: `139 passed` (was 124 in G03; +15 new G03-C1 tests)
- Frontend typecheck: clean (`tsc --noEmit` exits 0)
- Frontend tests: `12 passed` (unchanged from G03)
- Frontend build: `✓ built in 2.71s` (production artifact produced)

Also fixed: `vite.config.ts` reference types updated from `/// <reference types="vitest" />`
to `/// <reference types="vitest/config" />` for vitest 4.x compatibility
(was causing `tsc -b` to fail with "test does not exist in type UserConfigExport").

## Closure conditions

| Condition | Status |
|---|---|
| All tests pass | ✓ 139 backend + 12 frontend + typecheck + build |
| Simulated GDS success path test | ✓ `test_gds_louvain_runs_on_correct_projection` + `test_gds_success_path_returns_actual_node_refs` |
| Projection failure + cleanup test | ✓ `test_gds_projection_cleanup_runs_on_louvain_failure` + `test_gds_projection_failure_falls_back_to_networkx` |
| Label name consistency test | ✓ `test_g03c1_label_consistency.py` (8 tests) |
| No architectural changes or new features | ✓ Only fixed the GDS call, unified label naming, added finally cleanup, strengthened tests. No new modules, no new endpoints, no new services. |
| Real Neo4j/GDS test deferred to G07 | ✓ Acknowledged in test docstrings and in this report |

## Changed files (count, major paths)

7 files changed:
```
backend/app/services/gds_service.py         (rewritten detect_communities)
backend/app/services/neo4j_service.py       (added dataset_label() helper)
backend/app/services/parity_service.py     (uses dataset_label() helper)
backend/app/tests/_fake_neo4j.py           (strengthened: records queries, tracks projections)
backend/app/tests/test_g03c1_gds_path.py   (new — 7 tests)
backend/app/tests/test_g03c1_label_consistency.py (new — 8 tests)
frontend/vite.config.ts                     (vitest 4.x reference types fix)
```

## Test evidence: exact commands, pass/fail counts

### Backend
```
$ cd backend && python3 -m pytest app/tests/
collected 139 items
[...]
============================== 139 passed in 4.87s ==============================
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
> vite build   ✓ built in 2.71s
```

### Combined: 139 + 12 = 151 PASS, 0 FAIL

## Optional integrations still unavailable, honestly labelled

| Integration | Status |
|---|---|
| Docker / Neo4j runtime | not available in dev env; real GDS smoke deferred to G07 |
| PostgreSQL native | not available; SQLite used for unit tests |
| OTEL stack | not yet wired (G04) |
| Mentor LLM | `disabled` (G06) |

## Unresolved defects with severity

None.

## Scope-change violations: NONE

Only fixed the GDS call, unified label naming, added finally cleanup,
strengthened tests. No new modules, endpoints, or features.

## Next step

G03-C1 closure complete. Awaiting reviewer approval to start **G04 —
Instrumentation + collector + dashboards (T13–T16; gate A07)**.

## Reviewer decision required: APPROVE / HOLD

**Requested: APPROVE** to proceed to G04.
