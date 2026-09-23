"""Student dashboard data and teacher analytics (class aggregates, student progress, submissions)."""
from collections import defaultdict
from datetime import timedelta
from statistics import mean
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import SKILLS, skill_level_label
from app.core.errors import AppError, NotFound
from app.models import AIInteraction, Attempt, Experiment, SkillRecord, Student, Submission, User
from app.services import mistakes as mistake_service
from app.services import recommendation as reco_service
from app.services import skills as skill_service
from app.services import views
from app.services.recommendation import MASTERY_THRESHOLD
from app.utils.timeutil import utcnow


# ---------------------------------------------------------------- student dashboard
def student_dashboard(db: Session, student: Student, now=None) -> dict:
    now = now or utcnow()
    progress = views.experiment_progress(db, student.id)
    experiments = db.scalars(
        select(Experiment).where(Experiment.is_published.is_(True)).order_by(Experiment.position, Experiment.id)
    ).all()
    summaries = [views.student_experiment_summary(e, progress.get(e.id)) for e in experiments]
    published_ids = {e.id for e in experiments}
    graded = {i: p for i, p in progress.items() if i in published_ids and p["best_percent"] is not None}

    submits = db.execute(
        select(Submission, Experiment.title)
        .join(Experiment, Experiment.id == Submission.experiment_id)
        .where(Submission.student_id == student.id, Submission.kind == "submit")
        .order_by(Submission.created_at.desc(), Submission.id.desc())
        .limit(12)
    ).all()
    score_history = [
        {
            "submission_id": s.id, "experiment_id": s.experiment_id, "experiment_title": title,
            "percent": round(100 * s.score / s.max_score) if s.max_score else 0, "created_at": s.created_at,
        }
        for s, title in reversed(submits)
    ]

    attempts = db.execute(
        select(Attempt, Experiment.title)
        .join(Experiment, Experiment.id == Attempt.experiment_id)
        .where(Attempt.student_id == student.id)
        .order_by(Attempt.started_at.desc(), Attempt.id.desc())
        .limit(6)
    ).all()
    recent_attempts = [{**views.serialize_attempt(a), "experiment_id": a.experiment_id, "experiment_title": title} for a, title in attempts]

    total_runs = db.scalar(select(func.count()).select_from(Submission).where(Submission.student_id == student.id, Submission.kind == "run")) or 0
    total_submits = db.scalar(select(func.count()).select_from(Submission).where(Submission.student_id == student.id, Submission.kind == "submit")) or 0
    avg_percent = round(mean(p["best_percent"] for p in graded.values())) if graded else None

    rec = reco_service.current_recommendation(db, student.id)
    profile = mistake_service.mistake_profile(db, student.id, now)
    passport = skill_service.get_passport(db, student.id, now)
    return {
        "student": {"id": student.id, "full_name": student.user.full_name, "roll_number": student.roll_number, "cohort": student.cohort},
        "stats": {
            "experiments_total": len(experiments),
            "experiments_mastered": sum(1 for p in graded.values() if p["best_percent"] >= MASTERY_THRESHOLD * 100),
            "experiments_started": len([i for i in progress if i in published_ids]),
            "average_percent": avg_percent, "submissions": total_submits, "runs": total_runs,
            "skills_overall": passport["overall"],
        },
        "experiments": summaries,
        "recommendation": views.serialize_recommendation(db, rec),
        "score_history": score_history,
        "recent_attempts": recent_attempts,
        "passport": passport,
        "mistakes": {
            "total": profile["total"], "categories": profile["categories"][:5],
            "recent": mistake_service.recent_mistakes(db, student.id, limit=5), "improvement": profile["improvement"],
        },
    }


# ---------------------------------------------------------------- teacher analytics
def _student_best_ratios(db: Session) -> dict[tuple[int, int], float]:
    rows = db.execute(
        select(Submission.student_id, Submission.experiment_id, func.max(Submission.score / func.nullif(Submission.max_score, 0)))
        .where(Submission.kind == "submit")
        .group_by(Submission.student_id, Submission.experiment_id)
    ).all()
    return {(s, e): float(r or 0.0) for s, e, r in rows}


def _first_ratios(db: Session) -> dict[tuple[int, int], float]:
    """Score ratio of each student's first graded submission per experiment (how hard it was to get right first time)."""
    first_ids = select(func.min(Submission.id)).where(Submission.kind == "submit").group_by(Submission.student_id, Submission.experiment_id)
    rows = db.execute(
        select(Submission.student_id, Submission.experiment_id, Submission.score / func.nullif(Submission.max_score, 0))
        .where(Submission.id.in_(first_ids))
    ).all()
    return {(s, e): float(r or 0.0) for s, e, r in rows}


STUCK_ATTEMPTS = 3      # graded attempts on one experiment before it counts as a struggle
INACTIVE_DAYS = 7       # no submissions for this long while experiments remain unmastered
NEW_STUDENT_DAYS = 3    # a new account is only flagged for "nothing submitted" after this long


def _difficulty_label(first_attempt_percent, students: int) -> str:
    """Observed difficulty from how the class did on its FIRST graded try (needs at least two students)."""
    if first_attempt_percent is None or students < 2:
        return "Not enough data"
    return "Hard" if first_attempt_percent < 50 else "Moderate" if first_attempt_percent < 75 else "Easy"


def skill_distribution(db: Session, student_count: int) -> list[dict]:
    """How many students sit at each skill level. Counts only; no student is named."""
    per_skill = defaultdict(list)
    for skill, mastery in db.execute(select(SkillRecord.skill, SkillRecord.mastery).where(SkillRecord.evidence_count > 0)).all():
        per_skill[skill].append(mastery)
    result = []
    for name in SKILLS:
        values = per_skill.get(name, [])
        levels = {"Novice": 0, "Developing": 0, "Proficient": 0, "Advanced": 0}
        for v in values:
            levels[skill_level_label(v)] += 1
        result.append({
            "skill": name, "students_with_evidence": len(values), "not_started": max(0, student_count - len(values)),
            "average_mastery": round(mean(values), 1) if values else None, "levels": levels,
        })
    return result


def students_needing_practice(db: Session, now=None, limit: int = 8) -> list[dict]:
    """Students whose SCORES and ATTEMPTS suggest extra support. Deliberately excludes mistake profiles and AI chats."""
    now = now or utcnow()
    published = {e.id: e.title for e in db.scalars(select(Experiment).where(Experiment.is_published.is_(True))).all()}
    best_by_student = defaultdict(dict)
    for (sid, eid), ratio in _student_best_ratios(db).items():
        if eid in published:
            best_by_student[sid][eid] = ratio
    counts = defaultdict(dict)
    for sid, eid, n in db.execute(
        select(Submission.student_id, Submission.experiment_id, func.count()).where(Submission.kind == "submit").group_by(Submission.student_id, Submission.experiment_id)
    ).all():
        if eid in published:
            counts[sid][eid] = n
    last_seen = dict(db.execute(select(Submission.student_id, func.max(Submission.created_at)).group_by(Submission.student_id)).all())

    flagged = []
    for student, user in db.execute(select(Student, User).join(User, User.id == Student.user_id)).all():
        mine, tries = best_by_student.get(student.id, {}), counts.get(student.id, {})
        graded = sum(tries.values())
        avg = round(100 * mean(mine.values())) if mine else None
        reasons, severity = [], 0
        if graded == 0:
            if now - student.created_at >= timedelta(days=NEW_STUDENT_DAYS):
                reasons.append("Has not submitted anything for grading yet")
                severity += 2
        else:
            stuck = [published[e] for e, n in tries.items() if n >= STUCK_ATTEMPTS and mine.get(e, 0) < MASTERY_THRESHOLD]
            retried = [published[e] for e, n in tries.items() if n >= STUCK_ATTEMPTS and mine.get(e, 0) >= MASTERY_THRESHOLD]
            if stuck:
                reasons.append(f"{STUCK_ATTEMPTS}+ graded attempts without mastering {', '.join(stuck)}")
                severity += 3
            if avg is not None and avg < 60:
                reasons.append(f"Average best score is {avg}%")
                severity += 2
            if retried:
                reasons.append(f"Needed {STUCK_ATTEMPTS}+ graded attempts to master {', '.join(retried)}")
                severity += 1
            seen = last_seen.get(student.id)
            if seen and now - seen >= timedelta(days=INACTIVE_DAYS) and any(mine.get(e, 0) < MASTERY_THRESHOLD for e in published):
                reasons.append(f"No submissions for {(now - seen).days} days")
                severity += 2
        if reasons:
            flagged.append({
                "student_id": student.id, "full_name": user.full_name, "roll_number": student.roll_number,
                "priority": "high" if severity >= 3 else "medium" if severity == 2 else "low",
                "reasons": reasons, "average_percent": avg, "graded_submissions": graded,
                "last_active": last_seen.get(student.id), "_severity": severity,
            })
    flagged.sort(key=lambda f: (-f["_severity"], f["average_percent"] if f["average_percent"] is not None else -1, f["full_name"]))
    return [{k: v for k, v in f.items() if k != "_severity"} for f in flagged[:limit]]


def viva_practice(db: Session) -> tuple[dict[int, dict], dict]:
    """Finished AI Vivas per experiment: how many, how many students, and the average score.

    Aggregated from the existing `ai_interactions` rows (kind "viva_summary"); no new table and no student is
    named, in line with the rest of the class analytics. Viva scores are practice and never affect grades.
    """
    rows = db.scalars(select(AIInteraction).where(AIInteraction.kind == "viva_summary")).all()
    per_experiment: dict[int, dict] = defaultdict(lambda: {"sessions": 0, "students": set(), "percents": []})
    for row in rows:
        entry = per_experiment[row.experiment_id]
        entry["sessions"] += 1
        entry["students"].add(row.student_id)
        percent = (row.response or {}).get("percent")
        if percent is not None:
            entry["percents"].append(percent)
    per_experiment_out = {
        experiment_id: {
            "sessions": e["sessions"], "students": len(e["students"]),
            "average_percent": round(mean(e["percents"])) if e["percents"] else None,
        }
        for experiment_id, e in per_experiment.items()
    }
    everyone = {r.student_id for r in rows}
    all_percents = [p for e in per_experiment.values() for p in e["percents"]]
    totals = {
        "sessions": len(rows), "students": len(everyone),
        "average_percent": round(mean(all_percents)) if all_percents else None,
    }
    return per_experiment_out, totals


REVIEW_STATUSES = ("approved", "needs_rework")


def review_submission(db: Session, teacher, submission_id: int, status: str, remark: str, now=None):
    """Record or update a teacher's remark on one graded submission. The score is never touched."""
    from app.models import Submission, SubmissionReview

    if status not in REVIEW_STATUSES:
        raise AppError(422, f"Status must be one of: {', '.join(REVIEW_STATUSES)}")
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise NotFound("Submission not found")
    if submission.kind != "submit":
        raise AppError(422, "Only graded submissions can be reviewed.")
    review = db.scalar(select(SubmissionReview).where(SubmissionReview.submission_id == submission_id))
    if review is None:
        review = SubmissionReview(submission_id=submission_id, teacher_id=teacher.id)
        db.add(review)
    review.teacher_id = teacher.id
    review.status = status
    review.remark = (remark or "").strip()
    review.updated_at = now or utcnow()
    db.flush()
    db.refresh(review)
    return review


def clear_review(db: Session, submission_id: int) -> bool:
    from app.models import SubmissionReview

    review = db.scalar(select(SubmissionReview).where(SubmissionReview.submission_id == submission_id))
    if review is None:
        return False
    db.delete(review)
    db.flush()
    return True


def teacher_overview(db: Session, now=None, days: int = 14) -> dict:
    now = now or utcnow()
    student_count = db.scalar(select(func.count()).select_from(Student)) or 0
    exp_total = db.scalar(select(func.count()).select_from(Experiment)) or 0
    exp_published = db.scalar(select(func.count()).select_from(Experiment).where(Experiment.is_published.is_(True))) or 0
    kinds = dict(db.execute(select(Submission.kind, func.count()).group_by(Submission.kind)).all())
    graded_status = dict(db.execute(select(Submission.status, func.count()).where(Submission.kind == "submit").group_by(Submission.status)).all())
    graded_total = sum(graded_status.values())

    best = _student_best_ratios(db)
    first = _first_ratios(db)
    avg_percent = round(100 * mean(best.values())) if best else None
    first_percent = round(100 * mean(first.values())) if first else None
    active_students = len({s for s, _ in best})

    # Experiment table
    per_exp = defaultdict(list)
    for (_, exp_id), ratio in best.items():
        per_exp[exp_id].append(ratio)
    sub_counts = dict(db.execute(select(Submission.experiment_id, func.count()).where(Submission.kind == "submit").group_by(Submission.experiment_id)).all())
    pass_counts = dict(db.execute(select(Submission.experiment_id, func.count()).where(Submission.kind == "submit", Submission.status == "passed").group_by(Submission.experiment_id)).all())
    hints = dict(db.execute(select(Attempt.experiment_id, func.avg(Attempt.hints_used)).group_by(Attempt.experiment_id)).all())
    experiments = db.scalars(select(Experiment).order_by(Experiment.position, Experiment.id)).all()
    first_per_exp = defaultdict(list)
    for (_, exp_id), ratio in first.items():
        first_per_exp[exp_id].append(ratio)
    experiment_stats = []
    for e in experiments:
        ratios = per_exp.get(e.id, [])
        firsts = first_per_exp.get(e.id, [])
        n_sub = sub_counts.get(e.id, 0)
        experiment_stats.append({
            "id": e.id, "title": e.title, "difficulty": e.difficulty, "is_published": e.is_published,
            "students_attempted": len(ratios),
            "average_percent": round(100 * mean(ratios)) if ratios else None,
            "first_attempt_percent": round(100 * mean(firsts)) if firsts else None,
            "mastery_rate": round(100 * sum(1 for r in ratios if r >= MASTERY_THRESHOLD) / len(ratios)) if ratios else None,
            "submissions": n_sub, "pass_rate": round(100 * pass_counts.get(e.id, 0) / n_sub) if n_sub else None,
            "avg_hints_used": round(float(hints.get(e.id) or 0), 1),
        })

    # Completion, observed difficulty and the most common mistake per experiment (all class-level)
    attempted_pairs = set(db.execute(select(Attempt.student_id, Attempt.experiment_id).distinct()).all())
    best_by_exp = defaultdict(dict)
    for (sid, eid), ratio in best.items():
        best_by_exp[eid][sid] = ratio
    top_mistakes = mistake_service.class_top_mistake_by_experiment(db)
    vivas, viva_totals = viva_practice(db)
    for st in experiment_stats:
        graded_ids = set(best_by_exp.get(st["id"], {}))
        mastered_ids = {sid for sid, r in best_by_exp.get(st["id"], {}).items() if r >= MASTERY_THRESHOLD}
        in_progress = {sid for sid, eid in attempted_pairs if eid == st["id"]} - graded_ids
        attempted_only = graded_ids - mastered_ids
        st["completion"] = {
            "mastered": len(mastered_ids), "attempted": len(attempted_only), "in_progress": len(in_progress),
            "not_started": max(0, student_count - len(mastered_ids | attempted_only | in_progress)),
        }
        st["completion_rate"] = round(100 * len(mastered_ids) / student_count) if student_count else None
        st["difficulty_label"] = _difficulty_label(st["first_attempt_percent"], st["students_attempted"])
        st["top_mistake"] = top_mistakes.get(st["id"])
        st["viva"] = vivas.get(st["id"], {"sessions": 0, "students": 0, "average_percent": None})
    published_ids = {e.id for e in experiments if e.is_published}
    possible = student_count * len(published_ids)
    mastered_pairs = sum(1 for (sid, eid), r in best.items() if eid in published_ids and r >= MASTERY_THRESHOLD)

    # Score distribution over each student's average of best scores
    per_student = defaultdict(list)
    for (sid, _), ratio in best.items():
        per_student[sid].append(ratio)
    buckets = {"0-39%": 0, "40-59%": 0, "60-79%": 0, "80-100%": 0}
    for ratios in per_student.values():
        pct = 100 * mean(ratios)
        buckets["80-100%" if pct >= 80 else "60-79%" if pct >= 60 else "40-59%" if pct >= 40 else "0-39%"] += 1

    # Daily activity (graded submissions and runs)
    since = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    per_day = defaultdict(lambda: {"runs": 0, "submissions": 0})
    for created, kind in db.execute(select(Submission.created_at, Submission.kind).where(Submission.created_at >= since)).all():
        per_day[created.date().isoformat()]["submissions" if kind == "submit" else "runs"] += 1
    activity = []
    for i in range(days):
        d = (since + timedelta(days=i)).date().isoformat()
        activity.append({"date": d, **per_day.get(d, {"runs": 0, "submissions": 0})})

    return {
        "counts": {
            "students": student_count, "active_students": active_students, "experiments": exp_total,
            "published_experiments": exp_published, "graded_submissions": graded_total, "runs": kinds.get("run", 0),
        },
        "average_percent": avg_percent,
        "first_attempt_percent": first_percent,
        "pass_rate": round(100 * graded_status.get("passed", 0) / graded_total) if graded_total else None,
        "submission_status": {k: graded_status.get(k, 0) for k in ("passed", "partial", "failed")},
        "experiments": experiment_stats,
        "score_distribution": [{"range": k, "students": v} for k, v in buckets.items()],
        "activity": activity,
        # Aggregate only: category totals with no student identifiers.
        "common_mistakes": mistake_service.class_mistake_summary(db),
        "completion": {"mastered": mastered_pairs, "possible": possible, "rate": round(100 * mastered_pairs / possible) if possible else None},
        "skill_distribution": skill_distribution(db, student_count),
        "needs_practice": students_needing_practice(db, now),
        "viva": viva_totals,
    }


def teacher_student_list(db: Session) -> list[dict]:
    """Roster with performance numbers only (no mistake profiles or AI conversations)."""
    students = db.execute(select(Student, User).join(User, User.id == Student.user_id).order_by(User.full_name)).all()
    best = _student_best_ratios(db)
    first = _first_ratios(db)
    per_student, first_student = defaultdict(list), defaultdict(list)
    for (sid, _), ratio in best.items():
        per_student[sid].append(ratio)
    for (sid, _), ratio in first.items():
        first_student[sid].append(ratio)
    graded = dict(db.execute(select(Submission.student_id, func.count()).where(Submission.kind == "submit").group_by(Submission.student_id)).all())
    last_seen = dict(db.execute(select(Submission.student_id, func.max(Submission.created_at)).group_by(Submission.student_id)).all())
    runs = dict(db.execute(select(Submission.student_id, func.count()).group_by(Submission.student_id)).all())
    return [
        {
            "id": s.id, "full_name": u.full_name, "email": u.email, "roll_number": s.roll_number, "cohort": s.cohort,
            "experiments_submitted": len(per_student.get(s.id, [])),
            "experiments_mastered": sum(1 for r in per_student.get(s.id, []) if r >= MASTERY_THRESHOLD),
            "average_percent": round(100 * mean(per_student[s.id])) if per_student.get(s.id) else None,
            "first_attempt_percent": round(100 * mean(first_student[s.id])) if first_student.get(s.id) else None,
            "graded_submissions": graded.get(s.id, 0),
            "executions": runs.get(s.id, 0), "last_active": last_seen.get(s.id),
        }
        for s, u in students
    ]


def teacher_student_detail(db: Session, student_id: int) -> dict:
    student = db.get(Student, student_id)
    if student is None:
        raise NotFound("Student not found")
    progress = views.experiment_progress(db, student.id)
    experiments = db.scalars(select(Experiment).order_by(Experiment.position, Experiment.id)).all()
    subs = db.execute(
        select(Submission, Experiment.title).join(Experiment, Experiment.id == Submission.experiment_id)
        .where(Submission.student_id == student.id, Submission.kind == "submit")
        .order_by(Submission.created_at.desc(), Submission.id.desc()).limit(30)
    ).all()
    passport = skill_service.get_passport(db, student.id)
    return {
        "student": {"id": student.id, "full_name": student.user.full_name, "email": student.user.email, "roll_number": student.roll_number, "cohort": student.cohort},
        "experiments": [
            {"id": e.id, "title": e.title, "difficulty": e.difficulty, **{k: v for k, v in (progress.get(e.id) or views.EMPTY_PROGRESS).items()}}
            for e in experiments
        ],
        "submissions": [{**views.serialize_submission(s, include_code=False, include_results=False), "experiment_title": t} for s, t in subs],
        "skills": passport["skills"], "skills_overall": passport["overall"],
    }


def teacher_submissions(
    db: Session, experiment_id: Optional[int] = None, student_id: Optional[int] = None,
    kind: Optional[str] = None, status: Optional[str] = None, limit: int = 50, offset: int = 0,
) -> dict:
    q = (
        select(Submission, Experiment.title, User.full_name, Student.roll_number)
        .join(Experiment, Experiment.id == Submission.experiment_id)
        .join(Student, Student.id == Submission.student_id)
        .join(User, User.id == Student.user_id)
    )
    count_q = select(func.count()).select_from(Submission)
    for cond in (
        (Submission.experiment_id == experiment_id) if experiment_id else None,
        (Submission.student_id == student_id) if student_id else None,
        (Submission.kind == kind) if kind else None,
        (Submission.status == status) if status else None,
    ):
        if cond is not None:
            q, count_q = q.where(cond), count_q.where(cond)
    total = db.scalar(count_q) or 0
    rows = db.execute(q.order_by(Submission.created_at.desc(), Submission.id.desc()).limit(limit).offset(offset)).all()
    items = [
        {**views.serialize_submission(s, include_code=False, include_results=False),
         "experiment_title": title, "student_name": name, "roll_number": roll, "student_id": s.student_id}
        for s, title, name, roll in rows
    ]
    return {"total": total, "items": items, "limit": limit, "offset": offset}


def teacher_submission_detail(db: Session, submission_id: int) -> dict:
    row = db.execute(
        select(Submission, Experiment.title, User.full_name, Student.roll_number)
        .join(Experiment, Experiment.id == Submission.experiment_id)
        .join(Student, Student.id == Submission.student_id)
        .join(User, User.id == Student.user_id)
        .where(Submission.id == submission_id)
    ).first()
    if row is None:
        raise NotFound("Submission not found")
    s, title, name, roll = row
    attempt = db.get(Attempt, s.attempt_id)
    return {
        **views.serialize_submission(s, reveal_hidden=True),
        "experiment_title": title, "student_name": name, "roll_number": roll, "student_id": s.student_id,
        "attempt": views.serialize_attempt(attempt) if attempt else None,
    }
