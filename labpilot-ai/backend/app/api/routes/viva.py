"""AI Viva: rule-based oral practice. All routes are student-only and never change a score."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_student
from app.database import get_db
from app.core.errors import NotFound
from app.models import Experiment, Student
from app.services import viva as viva_service

router = APIRouter(prefix="/api/viva", tags=["viva"])


def _published(db: Session, experiment_id: int) -> Experiment:
    experiment = db.get(Experiment, experiment_id)
    if experiment is None or not experiment.is_published:
        raise NotFound("Experiment not found")
    return experiment


class StartRequest(BaseModel):
    experiment_id: int


class AnswerRequest(BaseModel):
    session_id: str = Field(min_length=3, max_length=80)
    answer: str = Field(default="", max_length=4000)


@router.get("/context")
def viva_context(student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    """Experiments the student can be examined on, plus their recent vivas."""
    return viva_service.context(db, student)


@router.post("/start")
def viva_start(body: StartRequest, student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    return viva_service.start(db, student, _published(db, body.experiment_id))


@router.post("/answer")
def viva_answer(body: AnswerRequest, student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    result = viva_service.answer(db, student, body.session_id, body.answer)
    db.commit()      # the transcript must be visible to the next question
    return result


@router.get("/summary")
def viva_summary(session_id: str, student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    result = viva_service.summary(db, student, session_id)
    db.commit()      # skill evidence and the summary record are written once, here
    return result
