# G02 — Implementation Report

**Date (UTC):** 2026-10-11
**Group / status:** PASS_WITH_LIMITATION (Docker/PostgreSQL runtime still unavailable in dev env; SQLite-backed tests verify logic correctness; G07 will exercise the actual PostgreSQL + Compose smoke)
**Repository / branch / HEAD before / HEAD after / clean tracked tree:**
- Repository: https://github.com/mayakilzy/AgentCraft-Engineering-Lab
- Branch: `main`
- HEAD before: `bc0d838` (G01 report commit)
- HEAD after: this commit (G02 work + report)
- Clean tracked tree: yes

## Tasks executed (IDs) and outputs

| Task | Output |
|---|---|
| T05 | Scoped graph storage: `app/services/graph_service.py` (add_node, add_edge with referential integrity + cardinality caps + self-loop rejection; cross-session/cross-dataset endpoints structurally impossible because node lookups are scoped by `session.id`); `app/services/session_service.py` (minimal guest session lifecycle — create + resolve from opaque cookie token; full lifecycle deferred to G07); `app/api/v1/sessions.py`, `app/api/v1/graph.py`, `app/api/v1/seed.py`; `app/schemas/graph.py`; 18 tests. |
| T06 | NetworkX adapter + algorithms: `app/services/graph_algorithms.py` (build_digraph, build_digraph_from_fixture, shortest_path, degree_centrality, in_out_degrees, reachable_descendants/ancestors, components weakly+strongly, graph_metrics, simulate_node_removal_reachability); `app/api/v1/graph_analysis.py` (5 endpoints); 2 new fixtures (`directed-path-v1` for E02, `mixed-kind-v1` for E03); 17 tests. |
| T07 | Cytoscape.js viewer: `frontend/src/components/GraphViewer.tsx` (4 layouts, kind filter with no dangling edges, selection callbacks, per-kind color, directed-edge styling, focusable container); `frontend/src/pages/GraphLabPage.tsx` (dataset/fixture selectors, Load/Refresh, layout switch, kind filter chips, metrics panel, selection panels, shortest-path mini-tool, empty + error states); 6 Vitest tests; typecheck clean; production build succeeds. |
| T08 | E01–E03 foundations: `app/lab/registry.py` (fail-closed OPERATIONS + VALIDATORS registries); `app/lab/operations.py` (seed_graph, shortest_path, filter_by_kind, graph_metrics); `app/lab/validators.py` (seed_five_nodes_v1, shortest_path_directed_v1, filter_by_kind_v1); 14 tests with deterministic passing AND failing cases per exercise. |

## Changed files (count, major paths)

27 files changed in the G02 commit. Major additions:

```
backend/
  app/api/deps.py                          (modified: +GuestSessionDep)
  app/api/v1/sessions.py                   (new)
  app/api/v1/graph.py                      (new)
  app/api/v1/seed.py                       (new)
  app/api/v1/graph_analysis.py             (new)
  app/db/session.py                        (modified: SessionLocal is now a true Session factory)
  app/fixtures/graph_seed.py               (modified: +2 fixtures for E02/E03)
  app/lab/__init__.py, registry.py,        (new — fail-closed operation/validator registry)
              operations.py, validators.py
  app/main.py                              (modified: mounts 4 new routers)
  app/schemas/graph.py                     (new)
  app/services/graph_service.py            (new)
  app/services/graph_algorithms.py         (new)
  app/services/session_service.py          (new)
  app/tests/conftest.py                    (modified: file-DB migrations + dependency override)
  app/tests/test_graph_storage.py          (new, 18 tests)
  app/tests/test_graph_algorithms.py       (new, 17 tests)
  app/tests/test_lab_exercises.py          (new, 14 tests)

frontend/
  src/api/client.ts                        (modified: +typed graph/session API)
  src/components/GraphViewer.tsx           (new)
  src/pages/GraphLabPage.tsx               (new)
  src/pages/index.tsx                      (modified: re-exports GraphLabPage)
  tests/graph_lab.test.tsx                  (new, 6 tests)
```

## Test evidence: exact commands, pass/fail counts, relevant logs

### Backend
```
$ cd backend && python3 -m pytest app/tests/
collected 68 items
app/tests/test_errors.py            ....      [ 6%]
app/tests/test_health.py           ....      [12%]
app/tests/test_migrations.py        ......    [20%]
app/tests/test_modules_registry.py .....     [29%]
app/tests/test_graph_storage.py     ..................  [55%]   # 18 new
app/tests/test_graph_algorithms.py .................    [80%]   # 17 new
app/tests/test_lab_exercises.py     ..............        [100%] # 14 new
============================= 68 passed in 3.26s ==============================
```

### Frontend
```
$ cd frontend && npm run typecheck
> tsc --noEmit   # clean

$ npm test
 ✓ tests/app.test.tsx (6 tests) 140ms
 ✓ tests/graph_lab.test.tsx (6 tests) 311ms   # 6 new
 Test Files  2 passed (2)
      Tests  12 passed (12)

$ npm run build
> vite build
✓ 58 + ... modules transformed
✓ built in 2.69s
```

### Combined total: **80 / 80 PASS** (was 25 in G01; +55 in G02)

## Acceptance gate IDs and evidence

| Gate | Evidence |
|---|---|
| A03 — Graph | `starter-five-v1`: exact 5 nodes / 4 edges / no dangling (test `test_seed_starter_five_loads_deterministic_data`, `test_fixture_shape`). `directed-path-v1`: known shortest path A→T3 = [A,T1,T2,T3] (test `test_shortest_path_known_directed_path`); unreachable pair A→ISO returns None (test `test_shortest_path_disconnected_returns_none`). SQL/Cypher parity deferred to G03. |
| A06 — Visualizer | Filter (kind chips, clear-all), 4 layouts (grid/circle/concentric/breadthfirst), node+edge detail panels, empty state, error state, keyboard focusable container (tests `renders layout buttons and lets the user switch`, `renders kind filter chips and toggles selection`, `shows the metrics panel after a successful load`, `shows the selected node panel when the viewer reports selection`). Directed edge styling (target-arrow-shape triangle) preserves the contract's "clear directed edges" requirement. |
| A02 — Manifest schema (seed) | Fail-closed registry: unknown operation/validator keys raise `InvalidStateError` (tests `test_unknown_operation_rejected`, `test_unknown_validator_rejected`, `test_duplicate_id_rejected` from G01). Concrete 10 manifests land in G05. |
| A09 — Gallery (seed shape) | `GET /api/v1/experiments` still honestly returns `{count:0, ids:[]}` — manifests land in G05. |
| A10 — Validation | Seeded success passes; bad input fails with deterministic error code; wrong-expected validator fails honestly (tests `test_E01_pass`, `test_E01_fail_wrong_fixture`, `test_E01_fail_missing_input`, `test_E02_pass_*`, `test_E02_fail_*`, `test_E03_pass_*`, `test_E03_fail_wrong_subset`). |
| A08 — Session isolation (seed shape) | Cross-session reads return empty (test `test_session_cannot_read_other_session_dataset`); cross-session edge rejected with 404 because the target node is invisible outside its owner session (test `test_edge_cannot_connect_nodes_from_different_sessions`); cross-dataset edges within the same session also rejected (test `test_edge_cannot_cross_datasets_in_same_session`). Full session lifecycle (TTL refresh, scheduled purge, per-IP rate limit, CSRF for state changes) lands in G07. |

## Screenshots / API output references

No screenshots taken (headless environment). API evidence reproduced via:

```
$ curl -s -X POST http://localhost:8000/api/v1/sessions/guest \
       -H 'Content-Type: application/json' \
       -d '{"locale":"en"}' -c /tmp/c.txt | jq .
{ "session_id": "...", "expires_at": "...", "locale": "en" }

$ curl -s -X POST http://localhost:8000/api/v1/graph/lab/seed \
       -H 'Content-Type: application/json' -b /tmp/c.txt \
       -d '{"dataset_key":"starter-five-v1"}' | jq .
{ "dataset_id": "lab", "node_count": 5, "edge_count": 4 }

$ curl -s -X POST http://localhost:8000/api/v1/graph/lab/shortest-path \
       -H 'Content-Type: application/json' -b /tmp/c.txt \
       -d '{"source":"T4","target":"T1"}' | jq .
{ "dataset_id": "lab", "source": "T4", "target": "T1",
  "path": ["T4", "T1"], "length": 1 }
```

(Frontend Graph Lab page exercises all of the above interactively.)

## Security and isolation evidence

- **Guest session cookie**: opaque 256-bit random token (`secrets.token_urlsafe(32)`); HttpOnly + SameSite=Lax; max-age from settings (24h default); never returned in response body (test `test_create_guest_session_sets_cookie`).
- **Cookie missing → 401**: `test_missing_cookie_returns_401`.
- **Cross-session isolation**: enforced structurally because all graph queries scope by `session.id`; cross-session edge attempted by test `test_edge_cannot_connect_nodes_from_different_sessions` returns 404 because the target node is invisible outside its session.
- **Cross-dataset isolation**: same session, different dataset → target node invisible, 404 (`test_edge_cannot_cross_datasets_in_same_session`).
- **Cardinality caps**: `max_graph_nodes` and `max_graph_edges` enforced server-side (tests `test_max_graph_nodes_enforced`, `test_max_graph_edges_enforced`).
- **Self-loop edges**: rejected (test `test_add_edge_self_loop_rejected`).
- **Duplicate (source, target, relation) triplets**: rejected by DB unique constraint (`ux_ge_session_dataset_src_tgt_rel`) — test `test_add_edge_duplicate_triplet_rejected`.
- **No arbitrary Python/SQL/Cypher from clients**: only allowlisted operation handlers in `app/lab/operations.py`; registry is fail-closed (`test_unknown_operation_rejected`).
- **Healthcheck tool in backend image verified**: `curl` is installed in the backend Dockerfile (line 13) and used by both the Dockerfile `HEALTHCHECK` (line 45) and the `docker-compose.yml` healthcheck (line 51). No fix required (reviewer instruction #2).

## Optional integrations unavailable, honestly labelled

| Integration | Status | Honest label |
|---|---|---|
| Docker daemon | still unavailable in dev env (sudo blocked) | Compose file delivered; runtime smoke deferred to G07 |
| PostgreSQL native install | still unavailable | Migration logic + ORM correctness verified against SQLite; PostgreSQL dialect path (native UUID + JSONB) is the production target and will be exercised end-to-end in G07 |
| Neo4j + GDS | not yet wired | G03 |
| OTEL Collector + Prometheus + Tempo + Grafana | not yet wired | G04 |
| Mentor LLM provider | `disabled` by default | G06 |

## Unresolved defects with severity

None.

Known non-defects:
- Frontend bundle is 678 KB / 217.58 KB gzip (above the 500 KB Vite warning threshold). Cytoscape.js itself is ~300 KB; this is acceptable for a learning lab. Will revisit code-splitting in G07 if a public-deployment budget mandates it.
- `pytest-asyncio` deprecation warning still present (cosmetic; addressed when async tests land in G04).
- React Router v6 future-flag warnings on test console (cosmetic; opt-in deferred to a later ADR if upgrading to v7).

## Scope-change violations: NONE

All work is within the frozen V1.0 scope and the G02 task definitions. No
new features, no microservices, no agents/swarm, no extra queue, no
arbitrary code execution surface introduced.

## Reviewer-instruction compliance check

| # | Instruction | Compliance |
|---|---|---|
| 1 | Keep Docker/PostgreSQL constraints in tracking log; SQLite is not a substitute for PostgreSQL runtime test. | Tracking log retained; G02 tests still run against SQLite only; Compose smoke explicitly scheduled for G07. |
| 2 | Verify the healthcheck tool is present in the backend image. | `curl` installed in `backend/Dockerfile` line 13 and used in HEALTHCHECK (line 45) + Compose (line 51). Verified. No fix needed. |
| 3 | Test session/dataset isolation; an edge must never connect nodes from different sessions. | Three dedicated tests: `test_session_cannot_read_other_session_dataset`, `test_edge_cannot_connect_nodes_from_different_sessions` (returns 404 with `not found in this dataset`), `test_edge_cannot_cross_datasets_in_same_session`. |
| 4 | No default passwords or local CORS in public deployment — lockdown in G07. | `.env.example` carries placeholders only; `CORS_ORIGINS` defaults to local dev origins; production lockdown explicitly scheduled for G07. |
| 5 | No services/frameworks/features outside frozen V1.0 spec. | Stack unchanged from ADR-0001; only added `networkx` (named in spec) and `cytoscape` (named in spec). No new framework. |
| 6 | Keep G01 tests passing after each modification. | Verified at every checkpoint: 37 → 54 → 68 backend tests, all green throughout G02. |

## Next group (DO NOT START)

**G03 — Neo4j + Cypher + GDS conditional (T09–T12; gates A04, A05).**

Awaiting reviewer approval before starting.

## Reviewer decision required: APPROVE / HOLD

**Requested: APPROVE** (or APPROVE_WITH_LIMITATION noting the Docker/PostgreSQL runtime deferral to G07, which is environmental, not architectural).
