"""Serialisers: turn ORM rows into the JSON the API returns.

The student view never contains reference solutions, teacher hint ladders or the input/expected
output of hidden test cases.
"""
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import CATEGORIES, category_label

REVIEW_LABELS = {"approved": "Approved", "needs_rework": "Needs rework"}
from app.models import Attempt, Experiment, ExperimentRecommendation, Submission
from app.services import whatif as whatif_service
from app.services.recommendation import MASTERY_THRESHOLD


# ---------------------------------------------------------------- progress per experiment
def experiment_progress(db: Session, student_id: int) -> dict[int, dict]:
    """experiment_id -> {status, best_score, best_percent, submissions, runs, attempts}."""
    progress: dict[int, dict] = {}
    rows = db.execute(
        select(
            Submission.experiment_id, Submission.kind, func.count(),
            func.max(Submission.score / func.nullif(Submission.max_score, 0)), func.max(Submission.score),
        )
        .where(Submission.student_id == student_id)
        .group_by(Submission.experiment_id, Submission.kind)
    ).all()
    for exp_id, kind, count, best_ratio, best_score in rows:
        p = progress.setdefault(exp_id, {"submissions": 0, "runs": 0, "best_score": None, "best_percent": None})
        if kind == "submit":
            p["submissions"], p["best_score"] = count, best_score
            p["best_percent"] = round(float(best_ratio or 0) * 100)
        else:
            p["runs"] = count
    attempts = dict(db.execute(
        select(Attempt.experiment_id, func.count()).where(Attempt.student_id == student_id).group_by(Attempt.experiment_id)
    ).all())
    for exp_id, p in progress.items():
        p["attempts"] = attempts.get(exp_id, 0)
        best = p["best_percent"]
        if best is None:
            p["status"] = "in_progress"
        elif best >= MASTERY_THRESHOLD * 100:
            p["status"] = "mastered"
        else:
            p["status"] = "attempted"
    return progress


EMPTY_PROGRESS = {"status": "not_started", "best_score": None, "best_percent": None, "submissions": 0, "runs": 0, "attempts": 0}


def _visible_tests(exp: Experiment) -> list[dict]:
    return [
        {"id": t.id, "name": t.name, "stdin": t.stdin, "expected_output": t.expected_output, "kind": t.kind}
        for t in exp.test_cases if not t.is_hidden
    ]


def student_experiment_summary(exp: Experiment, progress: Optional[dict] = None) -> dict:
    return {
        "id": exp.id, "slug": exp.slug, "title": exp.title, "objective": exp.objective,
        "difficulty": exp.difficulty, "skills": exp.skills or [], "concepts": exp.concepts or [],
        "max_score": exp.max_score, "estimated_minutes": exp.estimated_minutes, "position": exp.position,
        "test_count": len(exp.test_cases), "progress": progress or dict(EMPTY_PROGRESS),
    }


def current_attempt_info(db: Session, student_id: int, exp: Experiment) -> dict:
    """The open attempt if there is one; otherwise what the next attempt will be (nothing is created)."""
    open_attempt = db.scalar(
        select(Attempt).where(Attempt.student_id == student_id, Attempt.experiment_id == exp.id, Attempt.status == "in_progress")
    )
    if open_attempt:
        return serialize_attempt(open_attempt)
    last = db.scalar(select(func.max(Attempt.attempt_number)).where(Attempt.student_id == student_id, Attempt.experiment_id == exp.id)) or 0
    return {
        "id": None, "attempt_number": last + 1, "status": "not_started", "run_count": 0, "hints_used": 0,
        "score": None, "max_score": exp.max_score, "started_at": None, "submitted_at": None,
    }


def student_experiment_detail(db: Session, student_id: int, exp: Experiment, progress: Optional[dict] = None) -> dict:
    hidden = sum(1 for t in exp.test_cases if t.is_hidden)
    last = db.scalar(
        select(Submission).where(Submission.student_id == student_id, Submission.experiment_id == exp.id)
        .order_by(Submission.created_at.desc(), Submission.id.desc())
    )
    data = student_experiment_summary(exp, progress)
    data.update(
        problem_statement=exp.problem_statement, instructions=exp.instructions, starter_code=exp.starter_code,
        visible_tests=_visible_tests(exp), hidden_test_count=hidden,
        has_what_if=bool(exp.what_if_scenarios), last_code=last.code if last else None,
        current_attempt=current_attempt_info(db, student_id, exp),
    )
    return data


def teacher_experiment_detail(exp: Experiment) -> dict:
    return {
        "id": exp.id, "slug": exp.slug, "title": exp.title, "objective": exp.objective,
        "problem_statement": exp.problem_statement, "instructions": exp.instructions,
        "starter_code": exp.starter_code, "reference_solution": exp.reference_solution,
        "difficulty": exp.difficulty, "skills": exp.skills or [], "focus_categories": exp.focus_categories or [],
        "concepts": exp.concepts or [], "hints": exp.hints or [], "what_if_scenarios": exp.what_if_scenarios or [],
        "max_score": exp.max_score, "estimated_minutes": exp.estimated_minutes, "is_published": exp.is_published,
        "position": exp.position, "created_at": exp.created_at, "updated_at": exp.updated_at,
        "test_cases": [serialize_test_case(t) for t in exp.test_cases],
    }


def serialize_test_case(t) -> dict:
    return {
        "id": t.id, "name": t.name, "stdin": t.stdin, "expected_output": t.expected_output, "kind": t.kind,
        "is_hidden": t.is_hidden, "weight": t.weight, "position": t.position,
    }


# ---------------------------------------------------------------- attempts & submissions
def serialize_attempt(a: Attempt) -> dict:
    return {
        "id": a.id, "attempt_number": a.attempt_number, "status": a.status, "score": a.score,
        "max_score": a.max_score, "run_count": a.run_count, "hints_used": a.hints_used,
        "started_at": a.started_at, "submitted_at": a.submitted_at,
    }


def serialize_result(r, reveal_hidden: bool) -> dict:
    """One test result. `reveal_hidden` is only True for teachers."""
    concealed = r.is_hidden and not reveal_hidden
    return {
        "id": r.id, "name": r.test_name, "kind": r.test_kind, "is_hidden": r.is_hidden,
        "passed": r.passed, "status": r.status, "error_type": r.error_type, "runtime_ms": r.runtime_ms,
        "timed_out": r.timed_out,
        "stdin": None if concealed else r.stdin,
        "expected_output": None if concealed else r.expected_output,
        "actual_output": None if concealed else r.actual_output,
        "stderr": None if concealed else r.stderr,
    }


def serialize_submission(s: Submission, reveal_hidden: bool = False, include_code: bool = True, include_results: bool = True) -> dict:
    data = {
        "id": s.id, "attempt_id": s.attempt_id, "experiment_id": s.experiment_id, "kind": s.kind,
        "status": s.status, "passed_count": s.passed_count, "total_count": s.total_count, "score": s.score,
        "max_score": s.max_score, "runtime_ms": s.runtime_ms, "created_at": s.created_at,
    }
    if include_code:
        data["code"] = s.code
    if include_results:
        data["results"] = [serialize_result(r, reveal_hidden) for r in s.results]
    data["review"] = serialize_review(s.review)
    return data


def serialize_review(review) -> Optional[dict]:
    """A teacher's sign-off, shown to the student as feedback and to the teacher as the current state."""
    if review is None:
        return None
    return {
        "status": review.status,
        "label": REVIEW_LABELS.get(review.status, review.status),
        "remark": review.remark,
        "teacher_name": review.teacher.user.full_name if review.teacher else None,
        "reviewed_at": review.updated_at,
    }


def serialize_mistake(m) -> dict:
    meta = CATEGORIES.get(m.category, {})
    return {"category": m.category, "label": category_label(m.category), "detail": m.detail, "concept": meta.get("concept", ""), "tip": meta.get("tip", "")}


def serialize_recommendation(db: Session, rec: Optional[ExperimentRecommendation]) -> Optional[dict]:
    if rec is None:
        return None
    exp = db.get(Experiment, rec.experiment_id)
    return {
        "id": rec.id, "experiment_id": rec.experiment_id, "experiment_title": exp.title if exp else "(removed)",
        "difficulty": rec.difficulty, "reason": rec.reason, "signals": rec.signals or {},
        "followed": rec.followed, "followed_at": rec.followed_at, "created_at": rec.created_at,
    }


def whatif_scenarios(exp: Experiment) -> list[dict]:
    return whatif_service.public_scenarios(exp)
