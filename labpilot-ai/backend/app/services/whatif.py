"""What-If Experiment: predict -> run a modified program -> compare -> explain."""
import json
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.base import AIProvider, AIProviderError, AIRequest
from app.ai.factory import get_provider
from app.ai.prompts import WHATIF_SYSTEM_PROMPT, build_whatif_prompt
from app.core.errors import AppError, NotFound
from app.models import AIInteraction, Experiment, Student, WhatIfPrediction
from app.sandbox import get_sandbox
from app.services.skills import record_skill_evidence
from app.utils.text import normalize_output, truncate
from app.utils.timeutil import utcnow

log = logging.getLogger("labpilot.whatif")
MAX_INPUT_CHARS = 2000


def public_scenarios(experiment: Experiment) -> list[dict]:
    return [
        {
            "id": s["id"], "title": s["title"], "description": s.get("description", ""),
            "modified_code": s["modified_code"], "default_input": s.get("stdin", ""),
        }
        for s in (experiment.what_if_scenarios or [])
    ]


def find_scenario(experiment: Experiment, scenario_id: str) -> dict:
    for s in experiment.what_if_scenarios or []:
        if s.get("id") == scenario_id:
            return s
    raise NotFound("What-if scenario not found")


def compare(prediction: str, actual: str, errored: bool, error_type: Optional[str]) -> tuple[bool, str]:
    """Return (matched, human-readable difference)."""
    if errored:
        p = prediction.lower()
        matched = "error" in p or bool(error_type and error_type.lower() in p) or "crash" in p or "exception" in p
        return matched, "" if matched else f"The modified program stops with {error_type or 'an error'} instead of printing a result."
    pred_lines = normalize_output(prediction).split("\n")
    act_lines = normalize_output(actual).split("\n")
    if pred_lines == act_lines:
        return True, ""
    for n, (p, a) in enumerate(zip(pred_lines, act_lines), start=1):
        if p != a:
            return False, f"Line {n}: you predicted `{truncate(p, 60)}`, the program printed `{truncate(a, 60)}`."
    return False, f"You predicted {len(pred_lines)} line(s) but the program printed {len(act_lines)}."


def _ai_explanation(provider: AIProvider, ctx: dict) -> Optional[str]:
    request = AIRequest(
        task="whatif_explanation", system_prompt=WHATIF_SYSTEM_PROMPT,
        user_prompt=build_whatif_prompt(ctx), context=ctx, max_tokens=400,
    )
    try:
        raw = provider.generate(request)
        text = json.loads(raw[raw.find("{") : raw.rfind("}") + 1]).get("explanation", "")
        return text.strip()[:900] or None
    except (AIProviderError, ValueError, AttributeError) as exc:
        log.warning("What-if AI explanation failed (%s); using the teacher's explanation", exc)
        return None


def run_whatif(
    db: Session, student: Student, experiment: Experiment, scenario_id: str, prediction: str,
    stdin: Optional[str] = None, provider: Optional[AIProvider] = None, sandbox=None, now=None,
) -> dict:
    now = now or utcnow()
    scenario = find_scenario(experiment, scenario_id)
    prediction = (prediction or "").strip()
    if not prediction:
        raise AppError(422, "Please enter a prediction before running the experiment")
    if len(prediction) > MAX_INPUT_CHARS or (stdin is not None and len(stdin) > MAX_INPUT_CHARS):
        raise AppError(422, "Prediction or input is too long")
    stdin = scenario.get("stdin", "") if stdin is None else stdin

    outcome = (sandbox or get_sandbox()).run(scenario["modified_code"], stdin)
    errored = outcome.exit_code != 0 or outcome.timed_out
    if errored:
        last = next((ln for ln in reversed(outcome.stderr.strip().splitlines()) if ln.strip()), outcome.error_type or "Error")
        actual = f"[{outcome.error_type or 'Error'}] {last}"[:300]
    else:
        actual = outcome.stdout.rstrip("\n")
    matched, diff = compare(prediction, actual, errored, outcome.error_type)

    base = scenario.get("explanation") or "Compare the modified line with the original and trace one iteration by hand."
    explanation = ("Your prediction matches the real output. " if matched else (diff + " ")) + base
    ai_used = "rule-based"
    provider = provider or get_provider()
    if provider.is_real:
        ctx = {
            "experiment_title": experiment.title, "scenario_title": scenario["title"],
            "scenario_description": scenario.get("description", ""), "modified_code": scenario["modified_code"],
            "stdin": stdin, "prediction": prediction, "actual_output": actual, "matched": matched,
            "teacher_explanation": scenario.get("explanation", ""),
        }
        text = _ai_explanation(provider, ctx)
        if text:
            explanation, ai_used = text, provider.name
            db.add(AIInteraction(
                student_id=student.id, experiment_id=experiment.id, kind="whatif_explanation",
                request_context=ctx, response={"explanation": text}, provider=provider.name, created_at=now,
            ))

    earlier = db.scalars(select(WhatIfPrediction.stdin).where(
        WhatIfPrediction.student_id == student.id, WhatIfPrediction.experiment_id == experiment.id,
        WhatIfPrediction.scenario_id == scenario_id,
    )).all()
    repeat = any((e or "").strip() == (stdin or "").strip() for e in earlier)
    if matched and repeat:
        explanation += " You had already tried this input, so it does not add to your Skill Passport again."

    row = WhatIfPrediction(
        student_id=student.id, experiment_id=experiment.id, scenario_id=scenario_id,
        scenario_title=scenario["title"], modified_code=scenario["modified_code"], stdin=stdin,
        prediction=prediction, actual_output=actual, matched=matched, explanation=explanation,
        ai_provider=ai_used, created_at=now,
    )
    db.add(row)
    db.flush()
    # Credit only the first attempt at a given scenario and input: repeating it after seeing the answer proves nothing.
    skill_change = (
        record_skill_evidence(db, student.id, "Problem Solving", 1.0, 0.5, now, experiment_id=experiment.id, source="whatif")
        if matched and not repeat else None
    )
    return serialize_prediction(row, skill_change)


def history(db: Session, student_id: int, experiment_id: int, limit: int = 10) -> list[dict]:
    """Newest first. `credited` marks the first matched attempt for each scenario and input."""
    rows = db.scalars(
        select(WhatIfPrediction)
        .where(WhatIfPrediction.student_id == student_id, WhatIfPrediction.experiment_id == experiment_id)
        .order_by(WhatIfPrediction.created_at, WhatIfPrediction.id)
    ).all()
    seen, out = set(), []
    for r in rows:
        key = (r.scenario_id, (r.stdin or "").strip())
        out.append(serialize_prediction(r, credited=bool(r.matched and key not in seen)))
        seen.add(key)
    return list(reversed(out))[:limit]


def serialize_prediction(row: WhatIfPrediction, skill_change: Optional[dict] = None, credited: Optional[bool] = None) -> dict:
    return {
        "credited": (skill_change is not None) if credited is None else credited,
        "id": row.id, "experiment_id": row.experiment_id, "scenario_id": row.scenario_id,
        "scenario_title": row.scenario_title, "stdin": row.stdin, "prediction": row.prediction,
        "actual_output": row.actual_output, "matched": row.matched, "explanation": row.explanation,
        "ai_provider": row.ai_provider, "skill_change": skill_change, "created_at": row.created_at,
    }
