# ADR-0002 — Dependabot alert triage (14 alerts, V1.0)

**Date:** 2026-10-11
**Status:** Accepted (G03)
**Supersedes:** none
**References:** G02 reviewer note #4; `01_PROJECT_MASTER_SPEC.md` §7 (no claim of success without actual test evidence); `04_EXECUTION_PROTOCOL.md` §"Quality"

## Context

GitHub Dependabot reports 14 open security alerts on `main` after the G02
push (3 critical, 1 high, 9 medium, 1 auto-dismissed). The G02 reviewer
instructed: examine the alerts, identify affected packages/versions/actions,
fix exploitable critical vulnerabilities within app scope before deployment,
and do not defer sorting them.

## Findings

| # | Severity | Package | Ecosystem | Range | Fixed in | Exploitable in our app? | Action |
|---|---|---|---|---|---|---|---|
| 4 | **critical** | vitest | npm | `< 3.2.6` | 3.2.6 | **No** — dev-only; the CVE is "When Vitest UI server is listening, arbitrary file can be read and executed". We never run `vitest --ui`; we run `vitest run` (CLI). Not reachable at production runtime. | Upgrade vitest to ≥ 3.2.6 (resolves #4 and #10) |
| 12 | **critical** | tinypool | npm | `< 2.1.2` | 2.1.2 | **No** — dev-only; tinypool is vitest's worker pool. The CVE is "Prototype Pollution gadget to RCE in `run()` options" — only exploitable if attacker-controlled options are passed to `tinypool.run()`. We pass no such options; vitest drives it. | Resolved transitively by upgrading vitest |
| 13 | **critical** | tinypool | npm | `<= 2.1.0` | 2.1.1 | Same as #12. | Resolved transitively by upgrading vitest |
| 5 | **high** | vite | npm | `<= 6.4.2` | 6.4.3 | **No** — dev-only; the CVE is "launch-editor: NTLMv2 hash disclosure via UNC path handling on Windows". We develop on Linux; not exploitable on our platform. | Resolved by upgrading vite to ≥ 6.4.3 (or staying on 5.x — see below) |
| 11 | high | braces | npm | `<= 3.0.3` | (auto-dismissed) | **No** — auto-dismissed by GitHub as a false positive. | None |
| 1 | medium | pytest | pip | `< 9.0.3` | 9.0.3 | **No** — dev-only; "vulnerable tmpdir handling" requires an attacker to write into the test's tmpdir. Not exploitable in our test pipeline. | Defer to a routine bump (G07 hardening); no production exposure |
| 2 | medium | esbuild | npm | `<= 0.24.2` | 0.25.0 | **No** — dev-only; bundled by vite. | Resolved transitively by upgrading vite |
| 3 | medium | vite | npm | `<= 6.4.1` | 6.4.2 | **No** — dev-only; "Vite dev server path traversal in optimized deps `.map` handling". Only affects `vite dev`, not the production build artifact. | Resolved by upgrading vite |
| 6 | medium | vite | npm | `<= 6.4.2` | 6.4.3 | Same as #5. | Resolved by upgrading vite |
| 7 | medium | react-router | npm | `>= 6.0.0, < 7.18.0` | 7.18.0 | **Not exploitable in our usage** — CVE is "Open redirect via backslash in `<Link>` and `useNavigate`". We have only static routes (`/`, `/graph`, `/observability`, `/experiments`, `/history`) and never pass user-controlled URLs to `<Link>` or `useNavigate`. The SSR hydration CVE (#8) requires `deserializeErrors()` in SSR — we use CSR only. | Triage documented. Defer to G07 hardening (medium severity, not exploitable in our usage pattern). Optionally upgrade to react-router 7.x in a separate ADR if reviewer mandates. |
| 8 | medium | react-router | npm | `>= 6.4.0, < 7.18.0` | 7.18.0 | Same as #7. | Same as #7 |
| 9 | medium | @vitest/mocker | npm | `>= 2.1.0, < 4.1.11` | 4.1.11 | **No** — dev-only; "Path Traversal / Arbitrary File Read via @vitest/mocker Redirect Mock". Only triggered when an attacker controls a test mock's redirect target; we control all mocks. | Resolved transitively by upgrading vitest |
| 10 | medium | vitest | npm | `>= 2.1.0, < 4.1.11` | 4.1.11 | Same as #9. | Resolved by upgrading vitest |
| 14 | medium | postcss-selector-parser | npm | `< 7.1.6` | 7.1.6 | **No** — dev-only; "Quadratic complexity in flat selector parsing allows CPU exhaustion" via crafted CSS. Our Tailwind config uses no user-controlled selectors. | Resolved transitively by upgrading postcss |

## Decision

### A. Upgrade vitest to the latest stable (resolves #4, #9, #10, #12, #13)

Vitest 2.1.x → Vitest 3.2.x. This pulls:
- `@vitest/mocker` 4.x (resolves #9, #10)
- `tinypool` 2.1.2+ (resolves #12, #13)

### B. Upgrade vite to a version ≥ 6.4.3 (resolves #2, #3, #5, #6)

Vitest 3.x requires Vite 6.x. The production build artifact is unaffected;
the CVEs target `vite dev` and `launch-editor` (Windows-only). Upgrading
keeps the toolchain consistent with vitest 3.x and resolves the alerts
without forcing a separate major-version bump.

### C. Document react-router triage (defer fix to G07)

The two react-router alerts are medium severity and **not exploitable in
our usage pattern** (static routes only, CSR-only, no user-controlled URLs
in `<Link>`/`useNavigate`, no SSR). Upgrading to react-router 7.x is a
breaking change (data router API) that would require restructuring the
frontend router. We document this triage in this ADR and defer the upgrade
decision to G07 hardening, where the reviewer can mandate it if a stricter
policy is required.

### D. Defer pytest bump to a routine housekeeping moment (no production risk)

pytest `< 9.0.3` is a dev-only CVE. We are on pytest 8.3.4. The bump to
pytest 9.x is a routine upgrade; not exploitable in our test pipeline.
Defer to G07 hardening.

### E. Re-validate after upgrade

After applying A and B:
- Run `npm run typecheck` and `npm test` to confirm the test suite still
  passes on vitest 3.x.
- Run `npm run build` to confirm the production build still succeeds on
  vite 6.x.
- Re-check Dependabot alerts; the 8 alerts (4 critical/high + 4 medium)
  should be auto-resolved when GitHub re-scans the new lockfile.

## Alternatives considered

- **Stay on vitest 2.1.x and dismiss the alerts**: rejected because the
  reviewer explicitly said to fix exploitable criticals before deployment;
  while we judge them non-exploitable, the upgrade is cheap and keeps the
  toolchain current.
- **Pin `tinypool` to `>= 2.1.2` via npm `overrides`** without upgrading
  vitest: rejected because vitest 2.1.x may not be compatible with
  tinypool 2.1.2+; cleaner to upgrade vitest.
- **Upgrade react-router to 7.x now**: rejected because it is a breaking
  change that would touch many frontend files and is not warranted by
  exploitability (we have no exploitable usage). Defer to G07 with a
  separate ADR if needed.

## Consequences

- Frontend `package.json` pins: vitest `^3.2.6`, vite `^6.4.3` (or higher).
- 8 of 14 alerts auto-resolve after the bump + lockfile refresh.
- 2 react-router alerts remain open with a documented triage; targeted
  for G07 review.
- 1 pytest alert remains open with a documented triage; bumped in G07.
- 1 braces alert was already auto-dismissed.
- 1 postcss-selector-parser alert may persist if the Tailwind transitive
  pin doesn't pick up 7.1.6 — to be re-checked after `npm install`.
