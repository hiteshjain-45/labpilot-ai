"""Experiment catalogue as seen by students (no solutions, no hidden test data)."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_student
from app.core.errors import NotFound
from app.database import get_db
from app.models import Experiment, Student
from app.services import views

router = APIRouter(prefix="/api/experiments", tags=["experiments"])


def get_published_experiment(
    experiment_id: int,
    student: Student = Depends(get_current_student),  # authenticate first: unknown ids must not leak to anonymous or wrong-role callers
    db: Session = Depends(get_db),
) -> Experiment:
    exp = db.get(Experiment, experiment_id)
    if exp is None or not exp.is_published:
        raise NotFound("Experiment not found")
    return exp


@router.get("")
def list_experiments(student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    progress = views.experiment_progress(db, student.id)
    exps = db.scalars(select(Experiment).where(Experiment.is_published.is_(True)).order_by(Experiment.position, Experiment.id)).all()
    return [views.student_experiment_summary(e, progress.get(e.id)) for e in exps]


@router.get("/{experiment_id}")
def get_experiment(
    exp: Experiment = Depends(get_published_experiment),
    student: Student = Depends(get_current_student), db: Session = Depends(get_db),
):
    progress = views.experiment_progress(db, student.id).get(exp.id)
    return views.student_experiment_detail(db, student.id, exp, progress)
