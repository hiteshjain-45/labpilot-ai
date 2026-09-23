"""Adaptive Experiment Engine: choose the next experiment from recent performance.

The decision is transparent and rule-based (no AI needed):
  1. derive a target difficulty from the average of the last 5 graded submissions
  2. score every not-yet-mastered experiment: difficulty fit + overlap with the student's
     frequent mistake categories + gaps in the skills the experiment trains
  3. store the recommendation together with a human-readable reason and the raw signals
"""
from dataclasses import dataclass, field
from statistics import mean
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import practice_tags, DIFFICULTIES, category_label
from app.models import ExecutionResult, Experiment, ExperimentRecommendation, SkillRecord, Submission
from app.services.mistakes import student_category_counts
from app.utils.timeutil import utcnow

MASTERY_THRESHOLD = 0.8  # best graded score >= 80% counts as mastered
RECENT_WINDOW = 5


@dataclass
class Recommendation:
    experiment: Experiment
    difficulty: str
    reason: str
    signals: dict = field(default_factory=dict)


def best_ratios(db: Session, student_id: int) -> dict[int, float]:
    rows = db.execute(
        select(Submission.experiment_id, func.max(Submission.score / func.nullif(Submission.max_score, 0)))
        .where(Submission.student_id == student_id, Submission.kind == "submit")
        .group_by(Submission.experiment_id)
    ).all()
    return {exp_id: float(ratio or 0.0) for exp_id, ratio in rows}


def failed_case_counts(db: Session, submission_ids: list[int]) -> dict[str, int]:
    """Failed test cases in the given submissions, by kind (normal / edge / performance) and how many were hidden."""
    counts = {"normal": 0, "edge": 0, "performance": 0, "hidden": 0}
    if not submission_ids:
        return counts
    for kind, hidden, n in db.execute(
        select(ExecutionResult.test_kind, ExecutionResult.is_hidden, func.count())
        .where(ExecutionResult.submission_id.in_(submission_ids), ExecutionResult.passed.is_(False))
        .group_by(ExecutionResult.test_kind, ExecutionResult.is_hidden)
    ).all():
        counts[kind if kind in counts else "normal"] += n
        counts["hidden"] += n if hidden else 0
    return counts


def choose_target_level(
    experiments: list[Experiment], best: dict[int, float], recent_avg: Optional[float], last_level: int
) -> tuple[int, str]:
    """Return (level index, why) where why is one of new | advance | consolidate | hold | ease."""
    if recent_avg is None:
        return 0, "new"
    mastered_levels = [DIFFICULTIES.index(e.difficulty) for e in experiments if best.get(e.id, 0) >= MASTERY_THRESHOLD]
    top = max(mastered_levels, default=-1)
    if recent_avg >= 0.8:
        if top == -1:
            return 0, "consolidate"
        level_exps = [e for e in experiments if DIFFICULTIES.index(e.difficulty) == top]
        if all(best.get(e.id, 0) >= MASTERY_THRESHOLD for e in level_exps):
            return min(top + 1, len(DIFFICULTIES) - 1), "advance"
        return top, "consolidate"
    if recent_avg >= 0.5:
        return last_level, "hold"
    return max(last_level - 1, 0), "ease"


def compute_recommendation(db: Session, student_id: int) -> Optional[Recommendation]:
    experiments = db.scalars(
        select(Experiment).where(Experiment.is_published.is_(True)).order_by(Experiment.position, Experiment.id)
    ).all()
    if not experiments:
        return None
    best = best_ratios(db, student_id)
    recent = db.scalars(
        select(Submission)
        .where(Submission.student_id == student_id, Submission.kind == "submit")
        .order_by(Submission.created_at.desc(), Submission.id.desc())
        .limit(RECENT_WINDOW)
    ).all()
    recent_avg = mean(s.score / s.max_score for s in recent if s.max_score) if recent else None
    by_id = {e.id: e for e in experiments}
    last_exp = by_id.get(recent[0].experiment_id) if recent else None
    last_level = DIFFICULTIES.index(last_exp.difficulty) if last_exp else 0

    target, why = choose_target_level(experiments, best, recent_avg, last_level)
    pool = [e for e in experiments if best.get(e.id, 0) < MASTERY_THRESHOLD]
    if not pool:
        return None  # everything mastered

    failed = failed_case_counts(db, [s.id for s in recent])
    mistakes = student_category_counts(db, student_id)
    total_mistakes = sum(mistakes.values())
    mastery = {r.skill: r.mastery for r in db.scalars(select(SkillRecord).where(SkillRecord.student_id == student_id))}

    def score(e: Experiment) -> float:
        distance = abs(DIFFICULTIES.index(e.difficulty) - target)
        tagged = set(e.focus_categories or [])
        weakness = sum(n for c, n in mistakes.items() if tagged & set(practice_tags(c))) / total_mistakes if total_mistakes else 0.0
        gaps = [(100 - mastery.get(s, 0.0)) / 100 for s in (e.skills or [])]
        skill_gap = sum(gaps) / len(gaps) if gaps else 0.0
        started = 0.75 if 0.3 <= best.get(e.id, -1) < MASTERY_THRESHOLD else 0.0  # finish what was started
        focus = set(e.focus_categories or [])
        cases = (1.0 if failed["edge"] >= 2 and "boundary" in focus else 0.0) + (1.0 if failed["performance"] >= 1 and "inefficient" in focus else 0.0)
        return (3.0 if distance == 0 else -1.5 * distance) + 4.0 * weakness + 2.0 * skill_gap + started + cases

    ranked = sorted(pool, key=lambda e: (-score(e), e.position, e.id))
    chosen = ranked[0]

    level = DIFFICULTIES[target]
    parts: list[str] = []
    if recent_avg is None:
        parts.append("You have not submitted anything yet, so the plan starts with a beginner experiment.")
    else:
        n, pct = len(recent), round(recent_avg * 100)
        lead = f"Your last {n} graded submission{'s' if n != 1 else ''} average {pct}%"
        tail = {
            "advance": f"and every {DIFFICULTIES[target - 1]} experiment is mastered, so the next step is {level} level.",
            "consolidate": f"which is strong; you stay at {level} level until the remaining experiments are done.",
            "hold": f"which is solid progress, so you stay at {level} level to consolidate.",
            "ease": f"so the plan steps back to {level} level to rebuild a firm foundation.",
        }[why]
        parts.append(f"{lead}, {tail}")
    matching = sorted(((mistakes[c], c) for c in (chosen.focus_categories or []) if mistakes.get(c)), reverse=True)
    if matching:
        count, category = matching[0]
        label = category_label(category).lower()
        parts.append(
            f"Recommended because you recently struggled with {label} ({count}x); this experiment practises it."
            if count >= 2 else f"Recommended because your recent mistake was {label}; this experiment practises it."
        )
    elif "boundary" in (chosen.focus_categories or []) and failed["edge"] >= 2:
        parts.append(f"Recommended because your recent submissions missed {failed['edge']} edge cases, and this experiment practises boundary conditions.")
    elif "inefficient" in (chosen.focus_categories or []) and failed["performance"] >= 1:
        parts.append("Recommended because a recent submission failed a performance case, and this experiment practises efficient solutions.")
    weak = sorted(((mastery.get(s, 0.0), s) for s in (chosen.skills or [])))
    if weak and weak[0][0] < 70:
        parts.append(f"It also builds {weak[0][1]} (currently {round(weak[0][0])}%).")
    if best.get(chosen.id) is not None:
        parts.append(f"Your best score here so far is {round(best[chosen.id] * 100)}%, so this is a chance to improve it.")

    signals = {
        "recent_average": None if recent_avg is None else round(recent_avg, 3),
        "recent_submissions": len(recent),
        "target_difficulty": level,
        "decision": why,
        "top_mistakes": mistakes.most_common(3),
        "failed_cases": failed,
        "candidates": [{"experiment_id": e.id, "score": round(score(e), 2)} for e in ranked[:3]],
    }
    return Recommendation(chosen, chosen.difficulty, " ".join(parts), signals)


def latest_recommendation(db: Session, student_id: int) -> Optional[ExperimentRecommendation]:
    return db.scalar(
        select(ExperimentRecommendation)
        .where(ExperimentRecommendation.student_id == student_id)
        .order_by(ExperimentRecommendation.created_at.desc(), ExperimentRecommendation.id.desc())
    )


def refresh_recommendation(db: Session, student_id: int, now=None) -> Optional[ExperimentRecommendation]:
    """Recompute and store the recommendation. Unchanged picks are updated in place (no duplicates)."""
    result = compute_recommendation(db, student_id)
    if result is None:
        return None
    latest = latest_recommendation(db, student_id)
    if latest and latest.experiment_id == result.experiment.id and not latest.followed:
        latest.reason, latest.signals, latest.difficulty = result.reason, result.signals, result.difficulty
        db.flush()
        return latest
    rec = ExperimentRecommendation(
        student_id=student_id, experiment_id=result.experiment.id, difficulty=result.difficulty,
        reason=result.reason, signals=result.signals, created_at=now or utcnow(),
    )
    db.add(rec)
    db.flush()
    return rec


def current_recommendation(db: Session, student_id: int) -> Optional[ExperimentRecommendation]:
    latest = latest_recommendation(db, student_id)
    if latest is None or latest.followed:
        return refresh_recommendation(db, student_id)
    return latest


def mark_followed(db: Session, student_id: int, experiment_id: int, now=None) -> None:
    rows = db.scalars(
        select(ExperimentRecommendation).where(
            ExperimentRecommendation.student_id == student_id,
            ExperimentRecommendation.experiment_id == experiment_id,
            ExperimentRecommendation.followed.is_(False),
        )
    ).all()
    for rec in rows:
        rec.followed, rec.followed_at = True, now or utcnow()
    db.flush()
