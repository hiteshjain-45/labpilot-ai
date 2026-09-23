"""AI Copilot chat: a student-only conversation about one experiment, with quick actions."""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.ai import chat as chat_service
from app.core.deps import execution_guard, get_current_student
from app.core.errors import NotFound
from app.database import get_db
from app.models import Experiment, Student
from app.schemas.activity import ChatRequest

router = APIRouter(prefix="/api/copilot", tags=["copilot-chat"])


def _published(db: Session, experiment_id: int) -> Experiment:
    exp = db.get(Experiment, experiment_id)
    if exp is None or not exp.is_published:
        raise NotFound("Experiment not found")
    return exp


@router.get("/context")
def chat_context(
    experiment_id: Optional[int] = Query(default=None), student: Student = Depends(get_current_student), db: Session = Depends(get_db),
):
    """The experiments to choose from and what the Copilot knows about the chosen one (score, latest run, recent mistakes)."""
    return chat_service.context_payload(db, student, experiment_id)


@router.get("/messages")
def chat_messages(
    experiment_id: int = Query(), limit: int = Query(default=30, ge=1, le=100),
    student: Student = Depends(get_current_student), db: Session = Depends(get_db),
):
    exp = _published(db, experiment_id)
    return chat_service.conversation(db, student.id, exp.id, limit)


@router.post("/messages")
def chat_send(body: ChatRequest, student: Student = Depends(execution_guard), db: Session = Depends(get_db)):
    # execution_guard: a message can call a paid external API, so it shares the per-student request budget.
    exp = _published(db, body.experiment_id)
    result = chat_service.handle_message(
        db, student, exp, action=body.action, message=body.message, code=body.code, console_output=body.console_output,
    )
    db.commit()
    return result
