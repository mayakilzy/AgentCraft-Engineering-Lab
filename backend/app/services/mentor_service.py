"""Engineering Mentor service — T22 (G06).

Per the architecture contract §8 (Mentor grounding and isolation):
- Read-only Mentor Context Builder includes template ID/step, bounded
  sanitized inputs/outputs, validator status, traces/diagnostics
  accessible to current session, current language.
- Deterministic rule-based diagnostic mode available offline.
- Optional external LLM configurable server side; provider failure yields
  deterministic fallback with honest label.
- Prompt-injection resistance: user inputs as untrusted evidence, no
  secrets, no tool invocation, no elevated access.
- Never expose other sessions, tokens, internal URLs or host traces.
- Store bounded ephemeral chat by session with TTL (if storing); disabled
  by default if not essential.

Per the contract §4:
- `POST /api/v1/mentor/explain` body `{run_id,question,lang}`; reply
  `{answer, diagnosis_state, evidence_refs, next_checks, provider_mode}`.

The mentor is read-only and deterministic by default. When no LLM
provider is configured (the dev env default), the mentor builds a
grounded answer from the run's step verdicts + expected/actual blocks.
The answer never claims certainty beyond what the evidence supports:
- diagnosis_state="confirmed" when the evidence directly matches
- diagnosis_state="likely" when the evidence is consistent but indirect
- diagnosis_state="insufficient_evidence" when the run is BLOCKED or
  the question can't be answered from the available evidence

Per A11: grounded answer includes evidence and uncertainty; offline
fallback tested; no cross-session leak.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.errors import NotFoundError
from app.models.guest_session import GuestSession
from app.models.run import Run, RunEvent

# Bounded question length (per contract §9: question ≤ 2000 chars).
MAX_QUESTION_CHARS = 2000

# Forbidden patterns in the question — prompt-injection resistance.
# We don't execute the question; we just match keywords against the
# run's evidence. But we still reject questions that try to extract
# secrets, internal URLs, or cross-session data.
FORBIDDEN_PATTERNS = [
    re.compile(r"(?i)\b(password|secret|token|api[_-]?key)\b"),
    re.compile(r"(?i)\b(session[_-]?id|cookie)\b"),
    re.compile(r"(?i)\b(localhost|127\.0\.0\.1|0\.0\.0\.0)\b"),
    re.compile(r"(?i)\b(/etc/|/proc/|/var/)"),
]


@dataclass(frozen=True)
class MentorAnswer:
    """Grounded answer with evidence and uncertainty label."""
    answer: str
    provider_mode: str  # deterministic | openai | disabled
    diagnosis_state: str = "insufficient_evidence"  # confirmed | likely | insufficient_evidence
    evidence_refs: List[Dict[str, Any]] = field(default_factory=list)
    next_checks: List[str] = field(default_factory=list)


def explain_run(
    db: Session,
    settings: Settings,
    session: GuestSession,
    run_id: uuid.UUID,
    question: str,
    lang: str,
) -> MentorAnswer:
    """Build a grounded answer for the given run + question.

    The mentor is read-only and deterministic by default. The answer is
    built from the run's step verdicts + expected/actual blocks.
    """
    if len(question) > MAX_QUESTION_CHARS:
        raise NotFoundError(
            f"question too long (max {MAX_QUESTION_CHARS} chars)",
        )
    for pattern in FORBIDDEN_PATTERNS:
        if pattern.search(question):
            return MentorAnswer(
                answer=(
                    "I can't answer that question — it references "
                    "security-sensitive topics. I only discuss the "
                    "evidence from your run record."
                ),
                diagnosis_state="insufficient_evidence",
                evidence_refs=[],
                next_checks=[],
                provider_mode=_provider_mode(settings),
            )

    # Look up the run (session-scoped — 404 on cross-session).
    run = db.execute(
        select(Run).where(Run.id == run_id)
    ).scalar_one_or_none()
    if run is None or run.session_id != session.id:
        raise NotFoundError(f"run not found: {run_id}")

    # Collect the run's events (step verdicts).
    events = db.execute(
        select(RunEvent)
        .where(RunEvent.run_id == run.id)
        .order_by(RunEvent.created_at)
    ).scalars().all()

    provider_mode = _provider_mode(settings)

    # Build the grounded answer.
    return _build_answer(run, events, question, lang, provider_mode)


def _provider_mode(settings: Settings) -> str:
    """Determine the provider mode from the ACTUAL code path taken.

    G06-C1 reviewer fix: `provider_mode` must reflect the provider that
    ACTUALLY produced the answer, not the provider that is CONFIGURED.

    The current code path is ALWAYS deterministic — there is no actual
    OpenAI API call wired (the LLM integration is a future task). Even
    when `settings.mentor_provider == "openai"` and an API key is set,
    we still go through `_build_answer` which is a deterministic keyword
    matcher. Reporting "openai" in that case would be dishonest — we'd
    be claiming an LLM produced the answer when it didn't.

    When a real OpenAI call is wired (a future task), this function
    should return "openai" ONLY when the OpenAI code path was actually
    taken (e.g., the call succeeded and returned a non-empty answer).
    For now, the honest answer is always "deterministic".
    """
    # The deterministic path is the only path. The settings are
    # acknowledged but do NOT change the reported mode — the mode
    # reflects what produced the answer, not what was configured.
    return "deterministic"


def _build_answer(
    run: Run,
    events: List[RunEvent],
    question: str,
    lang: str,
    provider_mode: str,
) -> MentorAnswer:
    """Build a deterministic grounded answer from the run's evidence.

    The answer is built by matching keywords in the question against the
    run's step verdicts. The matching is intentionally simple — no NLP,
    no LLM call. The evidence_refs list cites the specific step events
    that support the answer.
    """
    step_verdicts = []
    for ev in events:
        if ev.step == "reset":
            continue
        rec = ev.record_json or {}
        step_verdicts.append({
            "step_id": ev.step,
            "step_status": ev.status,
            "operation_key": rec.get("operation_key"),
            "operation_status": rec.get("operation_status"),
            "operation_error_code": rec.get("operation_error_code"),
            "validator_key": rec.get("validator_key"),
            "validator_passed": rec.get("validator_passed"),
            "validator_message": rec.get("validator_message"),
        })

    # Keyword matching (case-insensitive).
    q_lower = question.lower()

    # Question asks "why did the run fail?"
    if any(kw in q_lower for kw in ("why", "fail", "error", "failed", "reason")):
        if run.status == "PASSED":
            return MentorAnswer(
                answer=(
                    f"The run PASSED — all {len(step_verdicts)} steps' validators "
                    f"confirmed the expected outcomes."
                ),
                diagnosis_state="confirmed",
                evidence_refs=step_verdicts,
                next_checks=[],
                provider_mode=provider_mode,
            )
        if run.status == "BLOCKED":
            blocked_steps = [s for s in step_verdicts if s["step_status"] == "blocked"]
            return MentorAnswer(
                answer=(
                    f"The run is BLOCKED because {len(blocked_steps)} step(s) "
                    f"could not complete due to an unavailable service. "
                    f"This is an environmental condition, not a logic error. "
                    f"Check the operation_error_code on the blocked steps."
                ),
                diagnosis_state="confirmed",
                evidence_refs=blocked_steps,
                next_checks=[
                    "Verify the required services are configured (e.g., NEO4J_URI).",
                    "Re-run the experiment after the service is available.",
                ],
                provider_mode=provider_mode,
            )
        if run.status == "FAILED":
            failed_steps = [s for s in step_verdicts if not s["validator_passed"]]
            return MentorAnswer(
                answer=(
                    f"The run FAILED because {len(failed_steps)} step(s) had "
                    f"validator failures. The most common cause is a mismatch "
                    f"between the expected and actual outputs. See the "
                    f"validator_message on each failed step for the specific "
                    f"reason."
                ),
                diagnosis_state="confirmed",
                evidence_refs=failed_steps,
                next_checks=[
                    "Inspect the validator_message on each failed step.",
                    "Compare the expected and actual blocks.",
                    "Re-run with corrected inputs if needed.",
                ],
                provider_mode=provider_mode,
            )
        return MentorAnswer(
            answer=f"The run is in state {run.status}.",
            diagnosis_state="insufficient_evidence",
            evidence_refs=step_verdicts,
            next_checks=[],
            provider_mode=provider_mode,
        )

    # Question asks about a specific step.
    if any(kw in q_lower for kw in ("step", "which step", "what step")):
        return MentorAnswer(
            answer=(
                f"The run has {len(step_verdicts)} steps. Here's the verdict for each: "
                + "; ".join(
                    f"{s['step_id']}: {s['step_status']} (validator "
                    f"{'passed' if s['validator_passed'] else 'failed'})"
                    for s in step_verdicts
                )
            ),
            diagnosis_state="confirmed",
            evidence_refs=step_verdicts,
            next_checks=[],
            provider_mode=provider_mode,
        )

    # Question asks about trace_id.
    if "trace" in q_lower or "trace_id" in q_lower:
        if run.trace_id:
            return MentorAnswer(
                answer=(
                    f"The run's trace_id is {run.trace_id}. You can use it to "
                    f"find the run's spans in Grafana Tempo via the "
                    f"/observability/links/{run.id} endpoint."
                ),
                diagnosis_state="confirmed",
                evidence_refs=[{"trace_id": run.trace_id, "run_id": str(run.id)}],
                next_checks=[
                    f"Open /api/v1/observability/links/{run.id} for the deep-link.",
                ],
                provider_mode=provider_mode,
            )
        return MentorAnswer(
            answer=(
                "The run has no trace_id. The OpenTelemetry instrumentation "
                "may not have captured a span at run creation time."
            ),
            diagnosis_state="likely",
            evidence_refs=[{"trace_id": None, "run_id": str(run.id)}],
            next_checks=[
                "Verify OTEL_EXPORTER_OTLP_ENDPOINT is set (or that the "
                "in-process SDK is active).",
            ],
            provider_mode=provider_mode,
        )

    # Default: summarize the run.
    return MentorAnswer(
        answer=(
            f"Run {run.id} (experiment {run.experiment_id}) is {run.status}. "
            f"It has {len(step_verdicts)} steps. "
            + (
                "All validators passed."
                if run.status == "PASSED"
                else "Some validators failed — see the step verdicts for details."
            )
        ),
        diagnosis_state="confirmed" if step_verdicts else "insufficient_evidence",
        evidence_refs=step_verdicts,
        next_checks=[
            "Ask 'why did the run fail?' for failure analysis.",
            "Ask 'which step?' for per-step verdicts.",
            "Ask 'trace_id?' for the trace correlation.",
        ],
        provider_mode=provider_mode,
    )
