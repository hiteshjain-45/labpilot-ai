"""AI Practical Copilot: build context -> call provider -> validate/sanitise -> log."""
import logging
import re
import time
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.base import AIProvider, AIProviderError, AIRequest
from app.ai.factory import get_provider
from app.ai.guardrails import clean_fields, leaks_solution, parse_guidance
from app.ai.prompts import COPILOT_SYSTEM_PROMPT, build_copilot_prompt
from app.ai.providers import MockProvider
from app.core.constants import CATEGORIES, category_label
from app.models import AIInteraction, Experiment, Student, Submission
from app.services.evaluation import TestOutcome
from app.services.mistakes import classify_outcomes, pattern_for, primary_category, recent_mistakes, student_category_counts
from app.services.submissions import get_open_attempt, validate_code
from app.utils.text import truncate
from app.utils.timeutil import utcnow

log = logging.getLogger("labpilot.copilot")
MAX_HINT_LEVEL = 3


def outcomes_from_submission(submission: Submission) -> list[TestOutcome]:
    return [
        TestOutcome(
            test_case_id=r.test_case_id, name=r.test_name, kind=r.test_kind, is_hidden=r.is_hidden,
            stdin=r.stdin, expected_output=r.expected_output, weight=1, passed=r.passed, status=r.status,
            actual_output=r.actual_output, stderr=r.stderr, error_type=r.error_type,
            runtime_ms=r.runtime_ms, timed_out=r.timed_out,
        )
        for r in submission.results
    ]


def _failing_test_view(o: TestOutcome) -> dict:
    """What the AI may see about a failing test. Hidden tests never expose inputs or expected output."""
    view = {"name": o.name, "kind": o.kind, "status": o.status, "error_type": o.error_type}
    if not o.is_hidden:
        view.update(
            stdin=truncate(o.stdin, 300), expected=truncate(o.expected_output, 300),
            actual=truncate(o.actual_output, 300), stderr=truncate(o.stderr, 600),
        )
    return view


def redact_hidden(text: str, outcomes: list[TestOutcome]) -> str:
    """Remove hidden-test data that an error message may echo (for example a ValueError quoting the input).

    Whole values are matched, never single common words, and anything that also appears in a visible case is left
    alone, so ordinary words and the names of the failing cases stay readable.
    """
    def lines(o: TestOutcome) -> list[str]:
        return [ln.strip() for v in (o.stdin, o.expected_output, o.actual_output) for ln in (v or "").splitlines()]

    visible = {ln for o in outcomes if not o.is_hidden for ln in lines(o)}
    secrets = {ln for o in outcomes if o.is_hidden for ln in lines(o) if len(ln) >= 3 and ln not in visible}
    for secret in sorted(secrets, key=len, reverse=True):
        text = re.sub(rf"(?<!\w){re.escape(secret)}(?!\w)", "[hidden]", text)
    return text


def build_context(
    db: Session, student: Student, experiment: Experiment, code: str, question: Optional[str],
    console_output: Optional[str], hint_level: int,
) -> tuple[dict, Optional[Submission]]:
    latest = db.scalar(
        select(Submission)
        .where(Submission.student_id == student.id, Submission.experiment_id == experiment.id)
        .order_by(Submission.created_at.desc(), Submission.id.desc())
    )
    category, detail, latest_view, changed = "not_run", "", None, False
    if latest is not None:
        outcomes = outcomes_from_submission(latest)
        found = classify_outcomes(latest.code, outcomes)
        category = primary_category(found) or "none"
        detail = redact_hidden(next((m.detail for m in found if m.category == category), ""), outcomes)
        changed = latest.code.strip() != code.strip()
        latest_view = {
            "kind": latest.kind, "passed": latest.passed_count, "total": latest.total_count,
            "failing_tests": [_failing_test_view(o) for o in outcomes if not o.passed][:4],
        }
    history = student_category_counts(db, student.id)
    pattern = {"times_before": 0, "experiments_affected": 0, "same_experiment": 0}
    if latest is not None and category in CATEGORIES:
        pattern = pattern_for(db, student.id, category, latest.attempt_id, experiment.id)
    context = {
        "experiment": {
            "title": experiment.title, "objective": experiment.objective,
            "problem_statement": truncate(experiment.problem_statement, 1500),
            "difficulty": experiment.difficulty, "concepts": experiment.concepts or [],
            "teacher_hints": experiment.hints or [],
        },
        "student_code": truncate(code, 6000),
        "code_changed_since_last_run": changed,
        "latest_run": latest_view,
        "console_output": truncate(console_output, 1500) if console_output else None,
        "category": category,
        "category_label": category_label(category) if category in CATEGORIES else "",
        "category_detail": detail,
        "previous_mistakes": [{"category": c, "count": n} for c, n in history.most_common(3)],
        "pattern": pattern,
        # labels and experiment titles only: mistake details could echo hidden-test data
        "recent_mistakes": [{"label": m["label"], "experiment": m["experiment_title"]} for m in recent_mistakes(db, student.id, 5)],
        "hint_level": hint_level,
        "question": truncate(question, 500) if question else None,
    }
    return context, latest


def get_hint(
    db: Session, student: Student, experiment: Experiment, code: str,
    question: Optional[str] = None, console_output: Optional[str] = None,
    provider: Optional[AIProvider] = None, now=None,
) -> dict:
    now = now or utcnow()
    code = validate_code(code)
    provider = provider or get_provider()
    attempt = get_open_attempt(db, student.id, experiment, now)
    level = min(MAX_HINT_LEVEL, attempt.hints_used + 1)
    context, latest = build_context(db, student, experiment, code, question, console_output, level)

    request = AIRequest(
        task="copilot_hint", system_prompt=COPILOT_SYSTEM_PROMPT,
        user_prompt=build_copilot_prompt(context), context=context,
    )
    used, is_fallback, reason = provider, False, None
    started = time.perf_counter()
    guidance = None
    try:
        guidance = clean_fields(parse_guidance(provider.generate(request)))
        if leaks_solution(" ".join(guidance.values()), experiment.reference_solution, experiment.starter_code):
            guidance, reason = None, "solution_leak_blocked"
    except (AIProviderError, ValueError) as exc:
        reason = f"provider_error: {exc}"[:200]
        log.warning("Copilot provider '%s' failed (%s); using rule-based guidance", provider.name, exc)
    if guidance is None:
        used, is_fallback = MockProvider(), provider.is_real  # a rule-based reply is a fallback only if AI was expected
        guidance = clean_fields(parse_guidance(used.generate(request)))
    latency = int((time.perf_counter() - started) * 1000)

    note = None
    if question and not (provider.is_real and not is_fallback):
        note = "Free-text questions are only read when an AI provider is configured; this guidance is based on your latest results."
    if context["category"] not in ("not_run", "none") and context["code_changed_since_last_run"]:
        note = (note + " " if note else "") + "You edited the code since the last run; run it again for guidance on the new version."

    attempt.hints_used += 1
    interaction = AIInteraction(
        student_id=student.id, experiment_id=experiment.id, submission_id=latest.id if latest else None,
        kind="hint", hint_level=level, request_context=context,
        response={**guidance, "category": context["category"], "note": note, "fallback_reason": reason},
        provider=used.name, is_fallback=is_fallback, latency_ms=latency, created_at=now,
    )
    db.add(interaction)
    db.flush()
    return serialize_interaction(interaction, used, reason)


def serialize_interaction(i: AIInteraction, provider: Optional[AIProvider] = None, reason: Optional[str] = None) -> dict:
    r = i.response or {}
    category = r.get("category", "logic")
    return {
        "interaction_id": i.id,
        "error_category": category,
        "category_label": category_label(category) if category in CATEGORIES else {"none": "No errors found", "not_run": "Not run yet"}.get(category, category),
        "explanation": r.get("explanation", ""),
        "hint": r.get("hint", ""),
        "concept_to_review": r.get("concept_to_review", ""),
        "next_step": r.get("next_step", ""),
        "hint_level": i.hint_level,
        "provider": i.provider,
        "provider_label": provider.label if provider else ("Rule-based mode" if i.provider == "mock" else i.provider),
        "is_ai": i.provider != "mock",
        "is_fallback": i.is_fallback,
        "fallback_reason": reason or r.get("fallback_reason"),
        "note": r.get("note"),
        "created_at": i.created_at,
    }
