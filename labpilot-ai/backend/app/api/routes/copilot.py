"""AI Practical Copilot: context-aware hints tied to the current experiment."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import copilot as copilot_service
from app.api.routes.experiments import get_published_experiment
from app.core.deps import execution_guard, get_current_student
from app.database import get_db
from app.models import AIInteraction, Experiment, Student
from app.schemas.activity import HintRequest

router = APIRouter(prefix="/api/experiments/{experiment_id}/copilot", tags=["copilot"])


@router.post("/hint")
def request_hint(
    body: HintRequest, exp: Experiment = Depends(get_published_experiment),
    student: Student = Depends(execution_guard), db: Session = Depends(get_db),
):
    # execution_guard: hints can call a paid external API, so they share the per-student request budget.
    result = copilot_service.get_hint(db, student, exp, body.code, body.question, body.console_output)
    db.commit()
    return result


@router.get("/history")
def hint_history(
    exp: Experiment = Depends(get_published_experiment), limit: int = Query(default=20, ge=1, le=50),
    student: Student = Depends(get_current_student), db: Session = Depends(get_db),
):
    rows = db.scalars(
        select(AIInteraction)
        .where(AIInteraction.student_id == student.id, AIInteraction.experiment_id == exp.id, AIInteraction.kind == "hint")
        .order_by(AIInteraction.created_at.desc(), AIInteraction.id.desc())
        .limit(limit)
    ).all()
    return [copilot_service.serialize_interaction(i) for i in rows]
