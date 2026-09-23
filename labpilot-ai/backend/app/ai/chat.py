"""AI Copilot chat: quick actions and free-text questions about the student's current experiment.

Built on the existing Copilot pieces: `copilot.get_hint` (hint levels per attempt), `copilot.build_context` (the experiment, the
student's code, the latest real test results and recent mistakes), the guardrails and the `AIInteraction` audit table
(rows with kind="chat"; nothing else in the schema changed).

CONNECTING A REAL LLM LATER needs no change to this file: configure a provider (see app/ai/factory.py and .env.example).
`_generated_reply` then sends CHAT_SYSTEM_PROMPT plus the context to `provider.generate()` for explain_error, explain_concept,
similar_problem and free-text questions; hints keep using `copilot.get_hint`. Every AI reply is parsed, stripped of long code
and checked against the reference solution, and falls back to the local rule-based content below if anything is wrong.
"""
import logging
import re
import time
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import chat_content as content
from app.ai import copilot
from app.ai.base import AIProvider, AIProviderError, AIRequest
from app.ai.factory import get_provider
from app.ai.guardrails import leaks_solution, strip_long_code
from app.ai.prompts import CHAT_SYSTEM_PROMPT, build_chat_prompt
from app.ai.providers import MockProvider
from app.ai.rules import build_rule_based_guidance
from app.core.constants import CATEGORIES, category_label
from app.core.errors import NotFound
from app.models import AIInteraction, Experiment, Student, Submission
from app.services import views
from app.services.mistakes import classify_outcomes, primary_category, recent_mistakes
from app.services.submissions import validate_code
from app.utils.timeutil import utcnow

log = logging.getLogger("labpilot.chat")
MAX_HINT_LEVEL = copilot.MAX_HINT_LEVEL

QUICK_ACTIONS = [
    {"id": "explain_error", "label": "Explain my error"},
    {"id": "hint", "label": "Give me a hint"},
    {"id": "explain_concept", "label": "Explain the concept"},
    {"id": "similar_problem", "label": "Give me a similar problem"},
]
ACTION_LABELS = {a["id"]: a["label"] for a in QUICK_ACTIONS} | {"check_attempt": "I tried again: check my attempt"}
SOLUTION_NOTE = "I do not hand out complete solutions: working it out yourself is how the skill sticks. Here is a hint instead."

# ---- understanding a typed question (rule-based; a real provider reads the text itself) ---------------------
_INTENTS = [
    ("solution_request", r"\b(full|complete|whole|entire)\s+(solution|code|answer|program)\b|\b(give|show|write|tell)\s+(me\s+)?(the\s+)?(solution|answer|code)\b|do (it|this|my (homework|lab)) for me|write (it|this|the code) for me"),
    ("check_attempt", r"tried again|try again|i (changed|fixed|updated)|check my (attempt|code|change|fix|new)|did (that|it) work|is (it|this) (right|correct|fixed)|still (wrong|failing|not working)"),
    ("similar_problem", r"similar|another (problem|question|exercise|one)|more practice|practice (problem|question|exercise)|new problem|extra problem"),
    ("explain_error", r"error|wrong|fail|crash|traceback|exception|not working|doesn'?t work|bug|mismatch|incorrect|why (is|does|did|do)\b"),
    ("hint", r"hint|stuck|clue|nudge|where (do|should) i|how (do|should) i|start|next step"),
    ("explain_concept", r"concept|what (is|are|does|do)\b|what's|explain|mean\b|how does|difference|understand|teach|why (use|do we)"),
]


def resolve_intent(action: Optional[str], message: Optional[str]) -> str:
    if action:
        return action
    text = (message or "").lower()
    for intent, pattern in _INTENTS:
        if re.search(pattern, text):
            return intent
    return "general"


def _clean_message(message: Optional[str]) -> Optional[str]:
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", " ", message or "").strip()
    return text[:500] or None


def note_for_text(text: str) -> Optional[dict]:
    lowered = (text or "").lower()
    return next((n for n in content.CONCEPT_NOTES if re.search(n["pattern"], lowered)), None)


# ---- what the Copilot knows (shown next to the chat) -------------------------------------------------------
def _latest_submission(db: Session, student_id: int, experiment_id: int) -> Optional[Submission]:
    return db.scalar(
        select(Submission).where(Submission.student_id == student_id, Submission.experiment_id == experiment_id)
        .order_by(Submission.created_at.desc(), Submission.id.desc())
    )


def _published(db: Session) -> list[Experiment]:
    return list(db.scalars(select(Experiment).where(Experiment.is_published.is_(True)).order_by(Experiment.position, Experiment.id)))


def default_experiment(db: Session, student: Student, experiments: list[Experiment]) -> Optional[Experiment]:
    """The experiment the student worked on most recently; otherwise the first one they have not mastered."""
    recent = db.scalar(select(Submission).where(Submission.student_id == student.id).order_by(Submission.created_at.desc(), Submission.id.desc()))
    by_id = {e.id: e for e in experiments}
    if recent is not None and recent.experiment_id in by_id:
        return by_id[recent.experiment_id]
    progress = views.experiment_progress(db, student.id)
    return next((e for e in experiments if progress.get(e.id, views.EMPTY_PROGRESS)["status"] != "mastered"), experiments[0] if experiments else None)


def experiment_context(db: Session, student: Student, exp: Experiment, progress: dict) -> dict:
    p = progress.get(exp.id, views.EMPTY_PROGRESS)
    latest = _latest_submission(db, student.id, exp.id)
    category = None
    if latest is not None:
        key = primary_category(classify_outcomes(latest.code, copilot.outcomes_from_submission(latest)))
        category = {"key": key, "label": category_label(key)} if key else None
    attempt = views.current_attempt_info(db, student.id, exp)
    return {
        "experiment": {"id": exp.id, "title": exp.title, "difficulty": exp.difficulty, "objective": exp.objective, "estimated_minutes": exp.estimated_minutes},
        "score": {
            "best_percent": p["best_percent"], "best_score": p["best_score"], "max_score": exp.max_score, "status": p["status"],
            "attempts": p["attempts"], "runs": p["runs"], "submissions": p["submissions"],
        },
        "latest_run": None if latest is None else {
            "kind": latest.kind, "passed": latest.passed_count, "total": latest.total_count,
            "score": latest.score, "max_score": latest.max_score, "created_at": latest.created_at,
        },
        "attempt": {"attempt_number": attempt["attempt_number"], "hints_used": attempt["hints_used"], "max_hints": MAX_HINT_LEVEL},
        "category": category,
        "recent_mistakes": [{"label": m["label"], "experiment": m["experiment_title"]} for m in recent_mistakes(db, student.id, 5)],
    }


def context_payload(db: Session, student: Student, experiment_id: Optional[int] = None, provider: Optional[AIProvider] = None) -> dict:
    provider = provider or get_provider()
    experiments = _published(db)
    progress = views.experiment_progress(db, student.id)
    chosen = None
    if experiment_id is not None:
        chosen = next((e for e in experiments if e.id == experiment_id), None)
        if chosen is None:
            raise NotFound("Experiment not found")
    elif experiments:
        chosen = default_experiment(db, student, experiments)
    return {
        "provider": {"is_real": provider.is_real, "label": provider.label if provider.is_real else "Rule-based mode", "model": provider.model},
        "experiments": [
            {"id": e.id, "title": e.title, "difficulty": e.difficulty,
             "status": progress.get(e.id, views.EMPTY_PROGRESS)["status"], "best_percent": progress.get(e.id, views.EMPTY_PROGRESS)["best_percent"]}
            for e in experiments
        ],
        "experiment_id": chosen.id if chosen else None,
        "context": experiment_context(db, student, chosen, progress) if chosen else None,
        "quick_actions": QUICK_ACTIONS,
    }


# ---- stored conversation ------------------------------------------------------------------------------------------
def _chat_rows(db: Session, student_id: int, experiment_id: int, limit: int = 100) -> list[AIInteraction]:
    """Newest first."""
    return list(db.scalars(
        select(AIInteraction)
        .where(AIInteraction.student_id == student_id, AIInteraction.experiment_id == experiment_id, AIInteraction.kind == "chat")
        .order_by(AIInteraction.created_at.desc(), AIInteraction.id.desc()).limit(limit)
    ))


def serialize_exchange(row: AIInteraction) -> dict:
    reply = dict(row.response or {})
    reply.update(id=row.id, created_at=row.created_at)
    request = row.request_context or {}
    return {"id": row.id, "created_at": row.created_at, "user": {"text": request.get("user_text", ""), "action": request.get("action")}, "assistant": reply}


def conversation(db: Session, student_id: int, experiment_id: int, limit: int = 30) -> list[dict]:
    """Oldest first, so the page can render it top to bottom."""
    return [serialize_exchange(r) for r in reversed(_chat_rows(db, student_id, experiment_id, limit))]


def _count_intent(rows: list[AIInteraction], intent: str) -> int:
    return sum(1 for r in rows if (r.request_context or {}).get("intent") == intent)


def _recent_history(rows: list[AIInteraction], n: int = 4) -> list[dict]:
    turns = []
    for r in reversed(rows[:n]):
        reply = r.response or {}
        turns.append({"student": ((r.request_context or {}).get("user_text") or "")[:200], "copilot": (reply.get("text") or reply.get("title") or "")[:300]})
    return turns


# ---- rule-based replies (no AI needed) --------------------------------------------------------------------------------
def _case_phrase(ctx: dict) -> str:
    failing = (ctx.get("latest_run") or {}).get("failing_tests") or []
    if not failing:
        return "the first failing case"
    t = failing[0]
    if "stdin" in t:  # visible cases only: hidden cases never carry their input
        shown = (t["stdin"] or "").strip().replace("\n", " / ")[:30]
        return f"the case \"{t['name']}\" (input `{shown}`)"
    return f"the case \"{t['name']}\" (a hidden case, so its input is not shown)"


def _rule_explain_error(ctx: dict) -> dict:
    category = ctx["category"]
    if category == "not_run":
        return {"title": "Nothing to explain yet", "text": "You have not run this experiment yet, so there is no error to look at. The Copilot works from your real test results.",
                "sections": [], "steps": list(content.NOT_RUN_STEPS)}
    if category == "none":
        return {"title": "No error found", "text": "Your latest run passes every visible test, so there is no error to explain. That does not prove the hidden cases pass.",
                "sections": [{"title": "What to check next", "body": "Think about inputs the visible tests do not cover: the smallest, the largest, zero, negative and repeated values. Then submit for grading."}], "steps": []}
    guidance = build_rule_based_guidance({**ctx, "hint_level": MAX_HINT_LEVEL})
    return {
        "title": f"Your error in simple words: {ctx['category_label']}",
        "text": content.SIMPLE[category],
        "sections": [{"title": "What your results show", "body": guidance["explanation"]}, {"title": "Concept to review", "body": guidance["concept_to_review"]}],
        "steps": [s.format(case=_case_phrase(ctx)) for s in content.DEBUG_STEPS[category]],
    }


def _concept_for(experiment: Experiment, ctx: dict, message: Optional[str], index: int) -> dict:
    if message:
        typed = note_for_text(message)
        if typed:
            return typed
    concepts = list(experiment.concepts or [])
    if not concepts:
        concepts = [CATEGORIES.get(ctx["category"], {}).get("concept", "Reading the problem statement")]
    name = concepts[index % len(concepts)]
    return note_for_text(name) or {
        "title": name, "idea": f"\"{name}\" is one of the ideas this experiment practises. Re-read the Aim and the Procedure to see where it is used, and ask for a hint if you are unsure where to start.",
        "example_kind": "text", "example": experiment.objective, "watch_out": "Try a very small input by hand before you write any code.",
    }


def _rule_concept(experiment: Experiment, ctx: dict, message: Optional[str], index: int) -> dict:
    note = _concept_for(experiment, ctx, message, index)
    sections = [
        {"title": "The idea", "body": note["idea"]},
        {"title": "A small example", "body": note["example"], "kind": note["example_kind"]},
        {"title": "Watch out for", "body": note["watch_out"]},
    ]
    category = ctx["category"]
    if category in CATEGORIES:
        sections.append({"title": "In your work", "body": f"Your latest result points to \"{ctx['category_label']}\". {CATEGORIES[category]['tip']}"})
    else:
        sections.append({"title": "In this experiment", "body": experiment.objective})
    return {"title": f"Concept: {note['title']}", "text": note["idea"], "sections": sections[1:], "steps": []}


def _practice_pool(experiment: Experiment, ctx: dict) -> list[dict]:
    skills = [content.CATEGORY_SKILL[ctx["category"]]] if ctx["category"] in content.CATEGORY_SKILL else []
    skills += [s for s in (experiment.skills or []) if s in content.SIMILAR_PROBLEMS]
    skills += ["Problem Solving"]
    pool, seen = [], set()
    for skill in skills:
        for problem in content.SIMILAR_PROBLEMS.get(skill, []):
            if problem["id"] not in seen:
                seen.add(problem["id"])
                pool.append({**problem, "skill": skill})
    return pool


def _related_experiment(db: Session, experiment: Experiment, progress: dict) -> Optional[dict]:
    mine = set(experiment.skills or [])
    options = []
    for e in _published(db):
        shared = mine & set(e.skills or [])
        if e.id == experiment.id or not shared:
            continue
        status = progress.get(e.id, views.EMPTY_PROGRESS)["status"]
        options.append(((status == "mastered", -len(shared), e.position), e, status, sorted(shared)))
    if not options:
        return None
    _, e, status, shared = sorted(options, key=lambda o: o[0])[0]
    return {"id": e.id, "title": e.title, "difficulty": e.difficulty, "status": status, "shared_skills": shared}


def _rule_similar(experiment: Experiment, ctx: dict, index: int) -> dict:
    pool = _practice_pool(experiment, ctx)
    problem = pool[index % len(pool)]
    return {
        "title": f"Practice problem: {problem['title']}",
        "text": f"Here is a fresh problem that practises {problem['skill']}. It is not part of your lab, so it does not affect your score.",
        "sections": [], "steps": [], "practice": {k: problem[k] for k in ("title", "statement", "example", "start_with", "skill")},
    }


# ---- the real-provider hook -----------------------------------------------------------------------------------------
def parse_chat_reply(raw: str) -> dict:
    """Extract {"reply", "steps"} from a model reply; raises ValueError if unusable."""
    import json

    text = (raw or "").strip()
    data = None
    try:
        data = json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                data = json.loads(text[start:end + 1])
            except ValueError:
                data = None
    if not isinstance(data, dict):
        raise ValueError("The AI reply was not a JSON object")
    reply = data.get("reply")
    if not isinstance(reply, str) or not reply.strip():
        raise ValueError("The AI reply has no text")
    steps = [strip_long_code(s.strip())[:300] for s in (data.get("steps") or []) if isinstance(s, str) and s.strip()][:6]
    return {"reply": strip_long_code(reply.strip())[:1200], "steps": steps}


def _generate(provider: AIProvider, experiment: Experiment, ctx: dict, intent: str, message: Optional[str], history: list[dict], focus: str):
    """Ask the configured provider. Returns (parsed, None) or (None, reason)."""
    request = AIRequest(
        task="copilot_chat", system_prompt=CHAT_SYSTEM_PROMPT, user_prompt=build_chat_prompt(ctx, intent, message, history, focus),
        context={**ctx, "intent": intent}, max_tokens=900,
    )
    try:
        parsed = parse_chat_reply(provider.generate(request))
    except (AIProviderError, ValueError) as exc:
        log.warning("Chat provider '%s' failed (%s); using the local rule-based reply", provider.name, exc)
        return None, f"provider_error: {exc}"[:200]
    if leaks_solution(" ".join([parsed["reply"], *parsed["steps"]]), experiment.reference_solution, experiment.starter_code):
        return None, "solution_leak_blocked"
    return parsed, None


# ---- the main entry point ------------------------------------------------------------------------------------------
def handle_message(
    db: Session, student: Student, experiment: Experiment, *, action: Optional[str] = None, message: Optional[str] = None,
    code: Optional[str] = None, console_output: Optional[str] = None, provider: Optional[AIProvider] = None, now=None,
) -> dict:
    """Answer one chat message and store the exchange. Returns the exchange: {id, created_at, user, assistant}."""
    if not action and not (message and message.strip()):
        raise ValueError("Choose a quick action or type a question")
    now = now or utcnow()
    provider = provider or get_provider()
    message = _clean_message(message)
    requested = resolve_intent(action, message)
    user_text = message or ACTION_LABELS[action]
    started = time.perf_counter()

    latest = _latest_submission(db, student.id, experiment.id)
    if code is not None and code.strip():
        code_text = validate_code(code)
    else:
        code_text = (latest.code if latest else None) or experiment.starter_code or "# no code yet"
    hints_used = views.current_attempt_info(db, student.id, experiment)["hints_used"]  # reading only: no attempt is created
    ctx, latest = copilot.build_context(db, student, experiment, code_text, message, console_output, min(MAX_HINT_LEVEL, hints_used + 1))
    progress = views.experiment_progress(db, student.id)
    ctx["progress"] = progress.get(experiment.id, views.EMPTY_PROGRESS)
    rows = _chat_rows(db, student.id, experiment.id)

    intent, note = requested, None
    if requested == "solution_request":
        intent, note = "hint", SOLUTION_NOTE
    elif requested == "general":
        intent = "explain_concept" if (message and note_for_text(message)) else "hint"
        note = "I was not sure exactly what you meant, so I picked the closest help. You can also use the quick actions."

    used, is_fallback, reason = MockProvider(), False, None
    if intent == "hint":
        hint = copilot.get_hint(db, student, experiment, code_text, question=message, console_output=console_output, provider=provider, now=now)
        reply = {
            "title": f"Hint {hint['hint_level']} of {MAX_HINT_LEVEL}", "text": hint["hint"],
            "sections": [s for s in (
                {"title": "What is going wrong", "body": hint["explanation"]},
                {"title": "Concept to review", "body": hint["concept_to_review"]},
                {"title": "Next step", "body": hint["next_step"]},
            ) if s["body"]],
            "steps": [], "hint": {"level": hint["hint_level"], "max": MAX_HINT_LEVEL, "interaction_id": hint["interaction_id"]},
        }
        used = provider if hint["is_ai"] and not hint["is_fallback"] else MockProvider()
        is_fallback, reason = hint["is_fallback"], hint.get("fallback_reason")
        note = " ".join(x for x in (note, hint.get("note")) if x) or None
    elif intent == "check_attempt":
        reply = _check_attempt(db, student, experiment, latest, code, rows)
    else:
        index = _count_intent(rows, intent)
        concept_focus = _concept_for(experiment, ctx, message, index)["title"] if intent == "explain_concept" else ""
        parsed = None
        if provider.is_real:
            parsed, reason = _generate(provider, experiment, ctx, intent, message, _recent_history(rows), concept_focus)
        if parsed is not None:
            used = provider
            reply = {"title": {"explain_error": "Your error, step by step", "explain_concept": f"Concept: {concept_focus}", "similar_problem": "A practice problem", "general": "Copilot"}.get(intent, "Copilot"),
                     "text": parsed["reply"], "sections": [], "steps": parsed["steps"]}
        else:
            is_fallback = provider.is_real  # a local reply counts as a fallback only when an AI reply was expected
            reply = {"explain_error": lambda: _rule_explain_error(ctx), "explain_concept": lambda: _rule_concept(experiment, ctx, message, index),
                     "similar_problem": lambda: _rule_similar(experiment, ctx, index)}.get(intent, lambda: _rule_explain_error(ctx))()
        if intent == "similar_problem":
            reply["related_experiment"] = _related_experiment(db, experiment, progress)

    reply["intent"] = intent
    latest_after = latest
    if intent in ("hint", "explain_error"):
        reply["baseline"] = {"submission_id": latest_after.id if latest_after else None, "passed": latest_after.passed_count if latest_after else 0, "total": latest_after.total_count if latest_after else 0}
    if intent in ("hint", "explain_error") and ctx["category"] != "none":
        reply["try_again"] = {"experiment_id": experiment.id, "label": "Try again in the editor"}
    reply.setdefault("suggestions", {
        "hint": ["explain_error", "explain_concept"], "explain_error": ["hint", "explain_concept"],
        "explain_concept": ["hint", "similar_problem"], "similar_problem": ["similar_problem", "explain_concept"],
        "check_attempt": ["hint", "explain_error"],
    }.get(intent, ["hint", "explain_concept"]))
    reply.update(
        provider=used.name, provider_label=used.label if used.is_real else "Rule-based mode", is_ai=used.is_real and not is_fallback,
        is_fallback=is_fallback, fallback_reason=reason, note=note,
    )

    row = AIInteraction(
        student_id=student.id, experiment_id=experiment.id, submission_id=latest.id if latest else None, kind="chat",
        hint_level=min(MAX_HINT_LEVEL, hints_used + 1),
        request_context={
            "action": action, "requested": requested, "intent": intent, "message": message, "user_text": user_text,
            "category": ctx["category"], "score": {k: ctx["progress"].get(k) for k in ("best_percent", "attempts", "status")},
        },
        response=reply, provider=used.name, is_fallback=is_fallback, latency_ms=int((time.perf_counter() - started) * 1000), created_at=now,
    )
    db.add(row)
    db.flush()
    return serialize_exchange(row)


# ---- the "Try again" workflow: compare with the result at the time of the last hint or explanation -----------------
def _check_attempt(db: Session, student: Student, experiment: Experiment, latest: Optional[Submission], client_code: Optional[str], rows: list[AIInteraction]) -> dict:
    baseline = next(((r.response or {}).get("baseline") for r in rows if (r.response or {}).get("baseline")), None)
    try_again = {"experiment_id": experiment.id, "label": "Try again in the editor"}

    def result(status, title, text, **extra):
        out = {"title": title, "text": text, "sections": [], "steps": [], "outcome": {"status": status, **extra}}
        if status not in ("all_passed",):
            out["try_again"] = try_again
        else:
            out["suggestions"] = ["similar_problem", "explain_concept"]
        return out

    if latest is None:
        return result("not_run", "Nothing to check yet", "You have not run this experiment yet. Open the editor, press Run tests, then come back and check your attempt.")
    now_state = {"passed": latest.passed_count, "total": latest.total_count}
    if latest.passed_count == latest.total_count:
        return result("all_passed", "All the visible tests pass", f"Well done: {latest.passed_count} of {latest.total_count} cases pass now. Submit for grading to check the hidden cases as well.", after=now_state)
    if baseline and baseline.get("submission_id") == latest.id:
        edited = bool(client_code and client_code.strip() and client_code.strip() != latest.code.strip())
        text = ("You changed your code, but have not run it yet. Press Run tests in the editor, then come back." if edited
                else "There is no new run since my last help. Change one thing in the editor, press Run tests, then come back and check.")
        return result("no_new_run", "No new run yet", text, before=baseline, after=now_state)
    before = baseline or {"passed": 0, "total": latest.total_count}
    before_ratio = before["passed"] / before["total"] if before.get("total") else 0
    after_ratio = latest.passed_count / latest.total_count if latest.total_count else 0
    figures = f"{before['passed']} of {before['total']} before, {latest.passed_count} of {latest.total_count} now"
    if after_ratio > before_ratio:
        return result("improved", "Progress: that change helped", f"More cases pass ({figures}). Keep going with the same approach: pick the next failing case and repeat.", before=before, after=now_state)
    if after_ratio < before_ratio:
        return result("worse", "That change made things worse", f"Fewer cases pass ({figures}). Undo the last change, or compare it with what worked before, and try a smaller change.", before=before, after=now_state)
    return result("same", "Same result as before", f"The result did not change ({figures}). The failing case behaves as before, so the fix is probably somewhere else. Ask for the next hint, or trace the failing case by hand.", before=before, after=now_state)
