"""Teacher-side experiment management: create/update/delete, test cases and reference validation."""
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFound
from app.models import Experiment, ExperimentTestCase, Teacher
from app.schemas.experiment import ExperimentCreate, ExperimentUpdate, TestCaseIn, TestCaseUpdate
from app.services.evaluation import evaluate_code, score_ratio
from app.services.submissions import validate_code
from app.utils.text import slugify


def get_experiment(db: Session, experiment_id: int) -> Experiment:
    exp = db.get(Experiment, experiment_id)
    if exp is None:
        raise NotFound("Experiment not found")
    return exp


def _unique_slug(db: Session, title: str, exclude_id: Optional[int] = None) -> str:
    base = slugify(title)[:100]
    slug, n = base, 2
    while True:
        found = db.scalar(select(Experiment.id).where(Experiment.slug == slug))
        if found is None or found == exclude_id:
            return slug
        slug, n = f"{base}-{n}", n + 1


def _new_test_case(data: TestCaseIn, position: int) -> ExperimentTestCase:
    return ExperimentTestCase(
        name=data.name, stdin=data.stdin, expected_output=data.expected_output, kind=data.kind,
        is_hidden=data.is_hidden, weight=data.weight, position=position,
    )


def create_experiment(db: Session, teacher: Optional[Teacher], data: ExperimentCreate) -> Experiment:
    if data.is_published and not data.test_cases:
        raise AppError(422, "A published experiment needs at least one test case (add one, or save it as a draft)")
    payload = data.model_dump(exclude={"test_cases", "what_if_scenarios"})
    exp = Experiment(
        **payload,
        slug=_unique_slug(db, data.title),
        what_if_scenarios=[s.model_dump() for s in data.what_if_scenarios],
        created_by_id=teacher.id if teacher else None,
    )
    for i, tc in enumerate(data.test_cases):
        exp.test_cases.append(_new_test_case(tc, i))
    db.add(exp)
    db.flush()
    return exp


def update_experiment(db: Session, exp: Experiment, data: ExperimentUpdate) -> Experiment:
    changes = data.model_dump(exclude_unset=True)
    if "what_if_scenarios" in changes and changes["what_if_scenarios"] is not None:
        changes["what_if_scenarios"] = [s if isinstance(s, dict) else s.model_dump() for s in changes["what_if_scenarios"]]
    for key in ("title", "difficulty", "max_score", "position", "estimated_minutes", "is_published"):
        if key in changes and changes[key] is None:
            changes.pop(key)  # these columns are not nullable
    for key in ("skills", "focus_categories", "concepts", "hints", "what_if_scenarios"):
        if key in changes and changes[key] is None:
            changes[key] = []
    if changes.get("is_published") and not exp.test_cases:
        raise AppError(422, "Add at least one test case before publishing this experiment")
    for key, value in changes.items():
        setattr(exp, key, value)
    if "title" in changes:
        exp.slug = _unique_slug(db, exp.title, exclude_id=exp.id)
    db.flush()
    return exp


def delete_experiment(db: Session, exp: Experiment) -> None:
    db.delete(exp)
    db.flush()


def add_test_case(db: Session, exp: Experiment, data: TestCaseIn) -> ExperimentTestCase:
    position = (db.scalar(select(func.max(ExperimentTestCase.position)).where(ExperimentTestCase.experiment_id == exp.id)) or 0) + 1
    tc = _new_test_case(data, position)
    tc.experiment_id = exp.id
    db.add(tc)
    db.flush()
    db.refresh(exp)
    return tc


def get_test_case(db: Session, exp: Experiment, test_id: int) -> ExperimentTestCase:
    tc = db.get(ExperimentTestCase, test_id)
    if tc is None or tc.experiment_id != exp.id:
        raise NotFound("Test case not found")
    return tc


def update_test_case(db: Session, exp: Experiment, test_id: int, data: TestCaseUpdate) -> ExperimentTestCase:
    tc = get_test_case(db, exp, test_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(tc, key, value)
    db.flush()
    return tc


def delete_test_case(db: Session, exp: Experiment, test_id: int) -> None:
    tc = get_test_case(db, exp, test_id)
    if exp.is_published and len(exp.test_cases) <= 1:
        raise AppError(400, "A published experiment needs at least one test case; unpublish it first")
    db.delete(tc)
    db.flush()
    db.refresh(exp)


def validate_reference(exp: Experiment, sandbox=None) -> dict:
    """Run the teacher's reference solution against every test case (catches wrong expected outputs)."""
    if not exp.reference_solution.strip():
        raise AppError(400, "Add a reference solution first")
    if not exp.test_cases:
        raise AppError(400, "Add at least one test case first")
    code = validate_code(exp.reference_solution)
    outcomes = evaluate_code(code, list(exp.test_cases), sandbox)
    return {
        "all_passed": all(o.passed for o in outcomes),
        "score_percent": round(score_ratio(outcomes) * 100),
        "results": [
            {
                "test_case_id": o.test_case_id, "name": o.name, "passed": o.passed, "status": o.status,
                "expected_output": o.expected_output, "actual_output": o.actual_output,
                "stderr": o.stderr[-600:], "runtime_ms": o.runtime_ms,
            }
            for o in outcomes
        ],
    }
