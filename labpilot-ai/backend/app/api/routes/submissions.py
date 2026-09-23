"""Run (visible tests) and submit (graded) student code; submission history."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.experiments import get_published_experiment
from app.core.deps import execution_guard, get_current_student
from app.core.errors import NotFound
from app.database import get_db
from app.models import Experiment, Student, Submission
from app.schemas.activity import CodeRequest
from app.services import submissions as submission_service
from app.services import views

router = APIRouter(prefix="/api", tags=["submissions"])


def _report_payload(db: Session, report) -> dict:
    return {
        "submission": views.serialize_submission(report.submission),
        "attempt": views.serialize_attempt(report.attempt),
        "mistakes": [views.serialize_mistake(m) for m in report.mistakes],
        "skill_changes": report.skill_changes,
        "recommendation": views.serialize_recommendation(db, report.recommendation),
    }


@router.post("/experiments/{experiment_id}/run")
def run_code(
    body: CodeRequest, exp: Experiment = Depends(get_published_experiment),
    student: Student = Depends(execution_guard), db: Session = Depends(get_db),
):
    """Run the code against the visible test cases. Not graded, but recorded for history and Mistake DNA."""
    report = submission_service.run_visible_tests(db, student, exp, body.code)
    db.commit()
    return _report_payload(db, report)


@router.post("/experiments/{experiment_id}/submit")
def submit_code(
    body: CodeRequest, exp: Experiment = Depends(get_published_experiment),
    student: Student = Depends(execution_guard), db: Session = Depends(get_db),
):
    """Grade the code against all test cases (including hidden ones) and update the learning profile."""
    report = submission_service.submit_solution(db, student, exp, body.code)
    db.commit()
    return _report_payload(db, report)


@router.get("/experiments/{experiment_id}/submissions")
def experiment_history(
    exp: Experiment = Depends(get_published_experiment),
    kind: str | None = Query(default=None, pattern="^(run|submit)$"),
    limit: int = Query(default=20, ge=1, le=100),
    student: Student = Depends(get_current_student), db: Session = Depends(get_db),
):
    q = select(Submission).where(Submission.student_id == student.id, Submission.experiment_id == exp.id)
    if kind:
        q = q.where(Submission.kind == kind)
    rows = db.scalars(q.order_by(Submission.created_at.desc(), Submission.id.desc()).limit(limit)).all()
    return [views.serialize_submission(s, include_code=False, include_results=False) for s in rows]


@router.get("/submissions/{submission_id}")
def get_submission(submission_id: int, student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    s = db.get(Submission, submission_id)
    if s is None or s.student_id != student.id:  # 404 rather than 403: do not reveal other students' ids
        raise NotFound("Submission not found")
    return views.serialize_submission(s)
