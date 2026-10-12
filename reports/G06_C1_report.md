# G06-C1 — Reviewer Fix Report

**Date (UTC):** 2026-10-12
**Mission:** G06 closure (apply 2 reviewer fixes before G07)
**Status:** PASS — both fixes applied, 7 new tests, all previous tests pass

## Reviewer-note compliance

### Fix #1 — `mentor.provider_mode` reflects the actual code path

**Issue:** The `_provider_mode(settings)` helper returned `"openai"` when `settings.mentor_provider == "openai"` and an API key was set — but the code path is ALWAYS deterministic (no OpenAI call is wired). Reporting `"openai"` without an actual call would be dishonest.

**Fix:** `_provider_mode()` now always returns `"deterministic"`. The function's docstring documents that when a real OpenAI call is wired (a future task), it should return `"openai"` ONLY when the OpenAI code path was actually taken.

**Test:** `test_mentor_provider_mode_deterministic_when_openai_configured` — sets `mentor_provider="openai"` and a fake API key, then asserts `answer.provider_mode == "deterministic"`. Proves the mode reflects the actual path, not the configured provider.

### Fix #2 — E09/E10 "corrected rerun" → "recovery demonstration"

**Issue:** The E09/E10 step 4 (E09) / step 5 (E10) was named `rerun_corrected` (E09) / `fix` (E10), implying it was a re-execution of the failed operation. In reality, the failed step uses `operation_key=inject_failure` while the recovery step uses `operation_key=run_trace_demo` — a DIFFERENT operation. Both share the same underlying `_run_trace_demo` function, but the manifest treats them as distinct operations with distinct `operation_key`s.

**Fix:**
- Renamed the step id from `rerun_corrected`/`fix` to `recovery_demo` in both E09 and E10.
- Updated the step title from "Disable injection and rerun" / "Fix and compare" to "Recovery demonstration" / "عرض الاسترجاع".
- Updated the instruction to explicitly state: "Run `run_trace_demo` (a DIFFERENT operation from `inject_failure`) WITHOUT `fail_step` to demonstrate the workflow recovers when the injection is disabled. This is NOT a re-execution of the failed operation; it is a demonstration that the same fetch→transform→persist workflow succeeds without the injected failure."
- Updated the experiment descriptions to say "demonstrate recovery" instead of "rerun the corrected case".
- Bumped E09 and E10 manifest versions from 1.1.0 to 1.2.0.

**Tests:**
- `test_E09_recovery_step_uses_different_operation_than_failed_step` — asserts the recovery step's `operation_key` differs from the failed step's (`run_trace_demo` ≠ `inject_failure`), the step id is `recovery_demo`, and the instruction mentions "DIFFERENT operation".
- `test_E10_recovery_step_uses_different_operation_than_failed_step` — same for E10.
- `test_E09_E10_descriptions_say_recovery_not_rerun` — asserts the experiment descriptions mention "recovery", not "rerun".
- `test_E09_full_run_still_passes_after_rename` — the full E09 run still passes; the last step is `recovery_demo` with `operation_key=run_trace_demo`.
- `test_E10_full_run_still_passes_after_rename` — same for E10.

## Closure conditions

| Condition | Status |
|---|---|
| `mentor.provider_mode` reflects the actual code path | ✓ always `"deterministic"` (no OpenAI call wired) |
| E09/E10 recovery step named/described honestly | ✓ `recovery_demo` + "DIFFERENT operation" |
| Test proving the description is honest | ✓ 7 new tests in `test_g06c1_review_fixes.py` |
| All G01–G06 tests pass | ✓ 276 backend + 17 frontend = 293 PASS |
| Typecheck clean | ✓ |
| Build succeeds | ✓ |

## Test evidence

```
$ cd backend && python3 -m pytest app/tests/
276 passed in 26.71s

$ cd frontend && npm run typecheck   # clean
$ npm test                           # 17 passed
$ npm run build                      # ✓ built
```

## Next step

G06-C1 closure complete. Proceeding to **G07 — Isolation and deployment** per the frozen plan.
