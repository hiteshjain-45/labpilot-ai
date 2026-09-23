"""Practical Skill Passport: mastery per skill, updated from demonstrated performance.

Every change is also written to `skill_evidence`, so the passport can show WHICH experiments moved a skill,
what was demonstrated recently and what needs more practice.
"""
from collections import defaultdict
from datetime import timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import DIFFICULTIES, DIFFICULTY_WEIGHT, SKILLS, skill_level_label
from app.models import Experiment, SkillEvidence, SkillRecord
from app.utils.timeutil import utcnow

UP_RATE = 0.30  # how fast mastery moves towards better evidence
DOWN_RATE = 0.10  # weaker evidence lowers mastery only gently
RECENT_DAYS = 7  # "recently demonstrated"
PRACTICE_BELOW = 45  # below the "Proficient" threshold a skill is listed as needing practice


def apply_evidence(mastery: float, ratio: float, weight: float) -> float:
    """Move mastery (0-100) towards `ratio*100`; improvement is faster than decline."""
    target = max(0.0, min(1.0, ratio)) * 100
    rate = (UP_RATE if target >= mastery else DOWN_RATE) * weight
    return round(max(0.0, min(100.0, mastery + rate * (target - mastery))), 1)


def record_skill_evidence(
    db: Session, student_id: int, skill: str, ratio: float, weight: float, now=None,
    *, experiment_id: Optional[int] = None, source: str = "submission",
) -> Optional[dict]:
    if skill not in SKILLS:
        return None
    now = now or utcnow()
    record = db.scalar(select(SkillRecord).where(SkillRecord.student_id == student_id, SkillRecord.skill == skill))
    if record is None:
        record = SkillRecord(student_id=student_id, skill=skill, mastery=0.0, evidence_count=0)
        db.add(record)
    before = record.mastery or 0.0
    record.mastery = apply_evidence(before, ratio, weight)
    record.evidence_count = (record.evidence_count or 0) + 1
    record.last_evidence_at = now
    db.add(SkillEvidence(
        student_id=student_id, skill=skill, experiment_id=experiment_id, source=source, ratio=round(ratio, 3),
        before=round(before, 1), after=record.mastery, delta=round(record.mastery - before, 1), created_at=now,
    ))
    db.flush()
    return {"skill": skill, "before": round(before, 1), "after": record.mastery, "delta": round(record.mastery - before, 1)}


def update_skills_for_submission(
    db: Session, student_id: int, experiment: Experiment, ratio: float,
    previous_best_ratio: Optional[float], now=None,
) -> list[dict]:
    """Apply evidence from a graded submission to every skill the experiment exercises."""
    weight = DIFFICULTY_WEIGHT.get(experiment.difficulty, 1.0)
    changes: dict[str, dict] = {}
    for skill in experiment.skills or []:
        change = record_skill_evidence(db, student_id, skill, ratio, weight, now, experiment_id=experiment.id)
        if change:
            changes[skill] = change
    # Debugging: the student improved on an earlier failing attempt, i.e. found and fixed a fault.
    improved = previous_best_ratio is not None and previous_best_ratio < 1.0 and ratio > previous_best_ratio
    if improved and "Debugging" not in changes:
        change = record_skill_evidence(db, student_id, "Debugging", ratio, weight * 0.8, now, experiment_id=experiment.id, source="debugging")
        if change:
            changes["Debugging"] = change
    return [c for c in changes.values() if c["delta"] != 0 or c["after"] > 0]


SOURCE_LABELS = {"submission": "Graded submission", "debugging": "Fixed a failing attempt", "whatif": "Correct What-If prediction", "viva": "AI Viva answer"}


def get_passport(db: Session, student_id: int, now=None) -> dict:
    from app.services.recommendation import MASTERY_THRESHOLD, best_ratios  # lazy: avoids an import cycle

    now = now or utcnow()
    records = {r.skill: r for r in db.scalars(select(SkillRecord).where(SkillRecord.student_id == student_id))}
    experiments = db.scalars(select(Experiment).where(Experiment.is_published.is_(True)).order_by(Experiment.position, Experiment.id)).all()
    by_id = {e.id: e for e in experiments}
    best = best_ratios(db, student_id)

    def best_percent(exp_id):
        return round(best[exp_id] * 100) if exp_id in best else None

    def status(exp_id):
        return "mastered" if best.get(exp_id, -1) >= MASTERY_THRESHOLD else "attempted" if exp_id in best else "not_started"

    contributors = defaultdict(list)
    for skill, exp_id, source, events, delta, last in db.execute(
        select(SkillEvidence.skill, SkillEvidence.experiment_id, SkillEvidence.source, func.count(), func.sum(SkillEvidence.delta), func.max(SkillEvidence.created_at))
        .where(SkillEvidence.student_id == student_id, SkillEvidence.experiment_id.is_not(None))
        .group_by(SkillEvidence.skill, SkillEvidence.experiment_id, SkillEvidence.source)
    ).all():
        exp = by_id.get(exp_id)
        if exp is None:
            continue
        contributors[skill].append({
            "experiment_id": exp.id, "title": exp.title, "difficulty": exp.difficulty, "source": source,
            "source_label": SOURCE_LABELS.get(source, source), "events": events, "delta": round(delta or 0.0, 1),
            "best_percent": best_percent(exp.id), "last_at": last,
        })
    recent_delta = dict(db.execute(
        select(SkillEvidence.skill, func.sum(SkillEvidence.delta))
        .where(SkillEvidence.student_id == student_id, SkillEvidence.created_at > now - timedelta(days=RECENT_DAYS))
        .group_by(SkillEvidence.skill)
    ).all())

    order = {d: i for i, d in enumerate(DIFFICULTIES)}
    skills = []
    for name, description in SKILLS.items():
        rec = records.get(name)
        mastery = rec.mastery if rec else 0.0
        last = rec.last_evidence_at if rec else None
        trained_by = sorted(
            ({"experiment_id": e.id, "title": e.title, "difficulty": e.difficulty, "best_percent": best_percent(e.id), "status": status(e.id)}
             for e in experiments if name in (e.skills or [])),
            key=lambda t: order.get(t["difficulty"], 0),
        )
        skills.append({
            "skill": name, "description": description, "mastery": mastery, "level": skill_level_label(mastery),
            "evidence_count": rec.evidence_count if rec else 0, "last_evidence_at": last,
            "recently_demonstrated": bool(last and last > now - timedelta(days=RECENT_DAYS)),
            "recent_change": round(recent_delta.get(name) or 0.0, 1),
            "needs_practice": mastery < PRACTICE_BELOW,
            "contributors": sorted(contributors.get(name, []), key=lambda c: -c["delta"]),
            "trained_by": trained_by,
        })

    demonstrated = [s for s in skills if s["evidence_count"] > 0]
    recent = sorted((s for s in skills if s["recently_demonstrated"]), key=lambda s: s["last_evidence_at"], reverse=True)[:4]
    practice = []
    for s in sorted((s for s in skills if s["needs_practice"]), key=lambda s: s["mastery"])[:3]:
        suggestion = next((t for t in s["trained_by"] if t["status"] != "mastered"), None)
        practice.append({"skill": s["skill"], "mastery": s["mastery"], "level": s["level"], "suggestion": suggestion})
    overall = round(sum(s["mastery"] for s in skills) / len(skills), 1) if skills else 0.0
    return {
        "skills": skills,
        "overall": overall,
        "strongest": max(demonstrated, key=lambda s: s["mastery"])["skill"] if demonstrated else None,
        "weakest": min(demonstrated, key=lambda s: s["mastery"])["skill"] if demonstrated else None,
        "recent": [{"skill": s["skill"], "level": s["level"], "mastery": s["mastery"], "last_evidence_at": s["last_evidence_at"], "recent_change": s["recent_change"]} for s in recent],
        "practice": practice,
    }


# ---------------------------------------------------------------------------------------------------------------
# Skill Passport page: one view over data that already exists (submissions, mastery, skill evidence, Mistake DNA).
# Nothing here is stored or invented; every number is derived on read.
# ---------------------------------------------------------------------------------------------------------------
STATUS_ORDER = ["Developing", "Practicing", "Strong", "Mastered"]
STRONG_AT = 45      # the mastery the passport already calls Proficient
MASTERED_AT = 70    # the mastery the passport already calls Advanced


def skill_status(skill: dict, mastered_experiment: bool, recurring_mistake: bool) -> str:
    """A plain status from evidence the student actually produced.

    Mastered needs both the mastery level and a mastered experiment that trains the skill, so the label always
    has something concrete behind it. A mistake pattern that keeps coming back holds the status at Practicing.
    """
    if skill["evidence_count"] == 0:
        return "Developing"
    if recurring_mistake:
        return "Practicing" if skill["mastery"] >= STRONG_AT else "Developing"
    if skill["mastery"] >= MASTERED_AT and mastered_experiment:
        return "Mastered"
    if skill["mastery"] >= STRONG_AT:
        return "Strong"
    return "Practicing"


def _achievements(db: Session, student_id: int, experiments, best, now) -> list[dict]:
    """Real events, newest first: mastered experiments, perfect scores and skills that crossed a level."""
    from app.models import Submission
    from app.services.recommendation import MASTERY_THRESHOLD

    titles = {e.id: e.title for e in experiments}
    out = []
    first_pass = {}
    for exp_id, ratio, score, max_score, when in db.execute(
        select(Submission.experiment_id, Submission.score / func.nullif(Submission.max_score, 0), Submission.score, Submission.max_score, Submission.created_at)
        .where(Submission.student_id == student_id, Submission.kind == "submit")
        .order_by(Submission.created_at)
    ).all():
        if exp_id not in titles or ratio is None:
            continue
        if float(ratio) >= MASTERY_THRESHOLD and exp_id not in first_pass:
            first_pass[exp_id] = when
            out.append({"kind": "mastered", "title": f"Mastered {titles[exp_id]}", "detail": f"scored {round(float(ratio) * 100)}%", "at": when, "experiment_id": exp_id})
        if score == max_score and max_score:
            out.append({"kind": "perfect", "title": f"Full marks on {titles[exp_id]}", "detail": f"{score} / {max_score}", "at": when, "experiment_id": exp_id})
    for skill, before, after, when in db.execute(
        select(SkillEvidence.skill, SkillEvidence.before, SkillEvidence.after, SkillEvidence.created_at)
        .where(SkillEvidence.student_id == student_id).order_by(SkillEvidence.created_at)
    ).all():
        for mark in (MASTERED_AT, STRONG_AT):
            # Worded by the mark that was crossed, not by a status: mastery can move again afterwards.
            if before < mark <= after:
                out.append({"kind": "skill", "title": f"{skill} rose above {mark}%", "detail": f"{round(before)}% to {round(after)}%", "at": when, "experiment_id": None})
                break
    seen, unique = set(), []
    for a in sorted(out, key=lambda a: a["at"], reverse=True):
        key = (a["kind"], a["title"])
        if key not in seen:
            seen.add(key)
            unique.append(a)
    return unique[:6]


def passport_page(db: Session, student, now=None) -> dict:
    """Everything the Skill Passport page shows, composed from the existing services."""
    from app.core.constants import SKILL_FOR_CATEGORY
    from app.services import views
    from app.services.mistakes import mistake_profile
    from app.services.recommendation import MASTERY_THRESHOLD, best_ratios

    now = now or utcnow()
    passport = get_passport(db, student.id, now)
    progress = views.experiment_progress(db, student.id)
    profile = mistake_profile(db, student.id, now)
    experiments = db.scalars(
        select(Experiment).where(Experiment.is_published.is_(True)).order_by(Experiment.position, Experiment.id)
    ).all()
    best = best_ratios(db, student.id)

    graded = [e for e in experiments if progress.get(e.id, {}).get("submissions")]
    mastered = [e for e in experiments if best.get(e.id, -1) >= MASTERY_THRESHOLD]
    percents = [progress[e.id]["best_percent"] for e in graded if progress[e.id]["best_percent"] is not None]

    by_difficulty = []
    for level in DIFFICULTIES:
        of_level = [e for e in experiments if e.difficulty == level]
        done = [e for e in of_level if e in mastered]
        tried = [e for e in of_level if e in graded and e not in done]
        scores = [progress[e.id]["best_percent"] for e in of_level if e in graded and progress[e.id]["best_percent"] is not None]
        by_difficulty.append({
            "difficulty": level, "total": len(of_level), "mastered": len(done), "attempted": len(tried),
            "not_started": len(of_level) - len(done) - len(tried),
            "average_percent": round(sum(scores) / len(scores)) if scores else None,
        })

    # Mistake DNA -> skills: a pattern that keeps coming back marks its skill as needing work.
    linked: dict[str, list[dict]] = {}
    for c in profile["categories"]:
        skill = SKILL_FOR_CATEGORY.get(c["category"])
        if skill:
            linked.setdefault(skill, []).append({
                "category": c["category"], "label": c["label"], "count": c["count"],
                "recurring": c["recurring"], "trend": c["trend"], "tip": c["tip"],
            })

    skills = []
    for s in passport["skills"]:
        trains = [t for t in s["trained_by"]]
        mistakes = sorted(linked.get(s["skill"], []), key=lambda m: -m["count"])
        recurring = [m for m in mistakes if m["recurring"]]
        practice = next((t for t in trains if t["status"] != "mastered"), None)
        skills.append({
            **s,
            "status": skill_status(s, any(t["status"] == "mastered" for t in trains), bool(recurring)),
            "mistakes": mistakes,
            "recurring_mistakes": len(recurring),
            "links": {
                "practice": practice,                                        # "Practice this skill"
                "related": [{"experiment_id": t["experiment_id"], "title": t["title"], "status": t["status"]} for t in trains],
                "review_mistakes": [m["category"] for m in mistakes],        # "Review mistakes"
            },
        })

    demonstrated = [s for s in skills if s["evidence_count"] > 0]
    strengths = sorted((s for s in demonstrated if s["status"] in ("Strong", "Mastered")), key=lambda s: -s["mastery"])[:3]
    improving = sorted((s for s in demonstrated if s["recent_change"] > 0), key=lambda s: -s["recent_change"])[:3]
    needs_work = sorted(
        (s for s in skills if s["recurring_mistakes"] or s["needs_practice"]),
        key=lambda s: (-s["recurring_mistakes"], s["mastery"]),
    )[:4]

    return {
        "profile": {
            "full_name": student.user.full_name, "roll_number": student.roll_number, "cohort": student.cohort,
            "member_since": student.created_at,
        },
        "summary": {
            "experiments_total": len(experiments), "completed": len(graded), "mastered": len(mastered),
            "average_percent": round(sum(percents) / len(percents)) if percents else None,
            "overall_progress": round(100 * len(mastered) / len(experiments)) if experiments else 0,
            "skill_average": passport["overall"],
            "graded_submissions": sum(progress[e.id]["submissions"] for e in graded),
        },
        "by_difficulty": by_difficulty,
        "skills": skills,
        "status_order": STATUS_ORDER,
        # carried through so the existing SkillPassport component can render the detailed record unchanged
        "overall": passport["overall"], "recent": passport["recent"], "practice": passport["practice"],
        "strengths": [{"skill": s["skill"], "status": s["status"], "mastery": s["mastery"], "evidence_count": s["evidence_count"]} for s in strengths],
        "improving": [{"skill": s["skill"], "recent_change": s["recent_change"], "status": s["status"]} for s in improving],
        "needs_improvement": [
            {"skill": s["skill"], "status": s["status"], "mastery": s["mastery"], "mistakes": s["mistakes"][:2], "practice": s["links"]["practice"]}
            for s in needs_work
        ],
        "achievements": _achievements(db, student.id, experiments, best, now),
        "mistake_dna": {
            "total": profile["total"],
            "improvement": profile["improvement"],
            "top": [
                {**{k: c[k] for k in ("category", "label", "count", "recurring", "trend")}, "skill": SKILL_FOR_CATEGORY.get(c["category"])}
                for c in profile["categories"][:4]
            ],
        },
    }
