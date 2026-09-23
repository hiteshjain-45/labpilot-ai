"""Teacher functionality: analytics, roster, experiment/test-case management, submission review."""
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from pydantic import BaseModel, Field

from app.core.deps import get_current_teacher
from app.core.errors import NotFound
from app.database import get_db
from app.models import Teacher
from app.schemas.auth import TeacherCreateRequest, UserOut
from app.schemas.experiment import ExperimentCreate, ExperimentUpdate, TestCaseIn, TestCaseUpdate
from app.services import accounts, analytics, views
from app.services import experiments as experiment_service
from app.models import Experiment

router = APIRouter(prefix="/api/teacher", tags=["teacher"], dependencies=[Depends(get_current_teacher)])


# ---------------------------------------------------------------- analytics & roster
@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    return analytics.teacher_overview(db)


@router.get("/students")
def students(db: Session = Depends(get_db)):
    return analytics.teacher_student_list(db)


@router.get("/students/{student_id}")
def student_detail(student_id: int, db: Session = Depends(get_db)):
    return analytics.teacher_student_detail(db, student_id)


@router.get("/mistakes")
def class_mistakes(db: Session = Depends(get_db)):
    """Class-wide mistake categories. Deliberately contains no student identifiers."""
    from app.services import mistakes as mistake_service

    return mistake_service.class_mistake_summary(db)


@router.post("/teachers", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def add_teacher(body: TeacherCreateRequest, db: Session = Depends(get_db)):
    """Teacher accounts cannot self-register; an existing teacher creates them."""
    teacher = accounts.create_teacher(db, body.email, body.password, body.full_name, body.department)
    db.commit()
    return UserOut(**accounts.user_profile(db, teacher.user))


# ---------------------------------------------------------------- experiments
@router.get("/experiments")
def list_experiments(db: Session = Depends(get_db)):
    stats = {e["id"]: e for e in analytics.teacher_overview(db)["experiments"]}
    exps = db.scalars(select(Experiment).order_by(Experiment.position, Experiment.id)).all()
    return [
        {
            "id": e.id, "title": e.title, "difficulty": e.difficulty, "is_published": e.is_published,
            "skills": e.skills or [], "max_score": e.max_score, "estimated_minutes": e.estimated_minutes,
            "test_count": len(e.test_cases), "hidden_test_count": sum(1 for t in e.test_cases if t.is_hidden),
            "updated_at": e.updated_at, **{k: stats[e.id][k] for k in ("students_attempted", "average_percent", "submissions", "pass_rate")},
        }
        for e in exps
    ]


@router.post("/experiments", status_code=status.HTTP_201_CREATED)
def create_experiment(body: ExperimentCreate, teacher: Teacher = Depends(get_current_teacher), db: Session = Depends(get_db)):
    exp = experiment_service.create_experiment(db, teacher, body)
    db.commit()
    return views.teacher_experiment_detail(exp)


@router.get("/experiments/{experiment_id}")
def get_experiment(experiment_id: int, db: Session = Depends(get_db)):
    return views.teacher_experiment_detail(experiment_service.get_experiment(db, experiment_id))


@router.patch("/experiments/{experiment_id}")
def update_experiment(experiment_id: int, body: ExperimentUpdate, db: Session = Depends(get_db)):
    exp = experiment_service.update_experiment(db, experiment_service.get_experiment(db, experiment_id), body)
    db.commit()
    return views.teacher_experiment_detail(exp)


@router.delete("/experiments/{experiment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_experiment(experiment_id: int, db: Session = Depends(get_db)):
    """Deletes the experiment together with its test cases and every student's attempts on it."""
    experiment_service.delete_experiment(db, experiment_service.get_experiment(db, experiment_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/experiments/{experiment_id}/validate")
def validate_reference(experiment_id: int, db: Session = Depends(get_db)):
    """Run the reference solution against every test case to catch wrong expected outputs."""
    return experiment_service.validate_reference(experiment_service.get_experiment(db, experiment_id))


# ---------------------------------------------------------------- test cases
@router.post("/experiments/{experiment_id}/test-cases", status_code=status.HTTP_201_CREATED)
def add_test_case(experiment_id: int, body: TestCaseIn, db: Session = Depends(get_db)):
    exp = experiment_service.get_experiment(db, experiment_id)
    tc = experiment_service.add_test_case(db, exp, body)
    db.commit()
    return views.serialize_test_case(tc)


@router.patch("/experiments/{experiment_id}/test-cases/{test_id}")
def update_test_case(experiment_id: int, test_id: int, body: TestCaseUpdate, db: Session = Depends(get_db)):
    exp = experiment_service.get_experiment(db, experiment_id)
    tc = experiment_service.update_test_case(db, exp, test_id, body)
    db.commit()
    return views.serialize_test_case(tc)


@router.delete("/experiments/{experiment_id}/test-cases/{test_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_test_case(experiment_id: int, test_id: int, db: Session = Depends(get_db)):
    exp = experiment_service.get_experiment(db, experiment_id)
    experiment_service.delete_test_case(db, exp, test_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class ReviewIn(BaseModel):
    status: str = Field(pattern="^(approved|needs_rework)$")
    remark: str = Field(default="", max_length=2000)


# ---------------------------------------------------------------- submissions
@router.get("/submissions")
def submissions(
    experiment_id: Optional[int] = None, student_id: Optional[int] = None,
    kind: Optional[str] = Query(default="submit", pattern="^(run|submit)$"),
    status_filter: Optional[str] = Query(default=None, alias="status", pattern="^(passed|partial|failed)$"),
    limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    return analytics.teacher_submissions(db, experiment_id, student_id, kind, status_filter, limit, offset)


@router.get("/submissions/{submission_id}")
def submission_detail(submission_id: int, db: Session = Depends(get_db)):
    return analytics.teacher_submission_detail(db, submission_id)


@router.put("/submissions/{submission_id}/review")
def review_submission(
    submission_id: int, body: ReviewIn,
    teacher: Teacher = Depends(get_current_teacher), db: Session = Depends(get_db),
):
    """Leave or update a remark on a graded submission. This never changes the score."""
    review = analytics.review_submission(db, teacher, submission_id, body.status, body.remark)
    db.commit()
    return views.serialize_review(review)


@router.delete("/submissions/{submission_id}/review", status_code=204)
def delete_review(
    submission_id: int, teacher: Teacher = Depends(get_current_teacher), db: Session = Depends(get_db),
):
    if not analytics.clear_review(db, submission_id):
        raise NotFound("Review not found")
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
