"""What-If Experiment: predict, run a modified program, compare and explain."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.routes.experiments import get_published_experiment
from app.core.deps import execution_guard, get_current_student
from app.database import get_db
from app.models import Experiment, Student
from app.schemas.activity import WhatIfExploreRequest, WhatIfRequest
from app.services import views
from app.services import whatif as whatif_service
from app.services import whatif_explore as explore_service

router = APIRouter(prefix="/api/experiments/{experiment_id}/whatif", tags=["what-if"])


@router.get("")
def scenarios(
    exp: Experiment = Depends(get_published_experiment), limit: int = Query(default=10, ge=1, le=50),
    student: Student = Depends(get_current_student), db: Session = Depends(get_db),
):
    return {
        "scenarios": views.whatif_scenarios(exp),
        "history": whatif_service.history(db, student.id, exp.id, limit),
    }


@router.post("/run")
def run(
    body: WhatIfRequest, exp: Experiment = Depends(get_published_experiment),
    student: Student = Depends(execution_guard), db: Session = Depends(get_db),
):
    result = whatif_service.run_whatif(db, student, exp, body.scenario_id, body.prediction, body.stdin)
    db.commit()
    return result


@router.get("/explore")
def explore_conditions(
    exp: Experiment = Depends(get_published_experiment),
    student: Student = Depends(get_current_student), db: Session = Depends(get_db),
):
    """The hypothetical questions that fit this experiment and the student's current code."""
    return explore_service.conditions_for(db, student, exp)


@router.post("/explore")
def explore_run(
    body: WhatIfExploreRequest, exp: Experiment = Depends(get_published_experiment),
    student: Student = Depends(execution_guard), db: Session = Depends(get_db),
):
    # execution_guard: exploring runs the sandbox several times, so it shares the per-student budget.
    return explore_service.explore(db, student, exp, body.condition_id, body.option, body.code)
