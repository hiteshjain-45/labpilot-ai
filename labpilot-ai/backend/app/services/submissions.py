"""The run/submit pipeline: execute -> judge -> persist -> classify mistakes -> update skills."""
import logging
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import AppError
from app.models import Attempt, ExecutionResult, Experiment, Student, Submission
from app.services import mistakes as mistake_service
from app.services import recommendation as reco_service
from app.services import skills as skill_service
from app.services.evaluation import TestOutcome, evaluate_code, score_ratio
from app.utils.timeutil import utcnow

log = logging.getLogger("labpilot.submissions")


@dataclass
class ExecutionReport:
    submission: Submission
    attempt: Attempt
    mistakes: list = field(default_factory=list)
    skill_changes: list = field(default_factory=list)
    recommendation: Optional[object] = None


def validate_code(code: str) -> str:
    settings = get_settings()
    if not code or not code.strip():
        raise AppError(422, "Code must not be empty")
    if len(code) > settings.max_code_chars:
        raise AppError(422, f"Code is too long (maximum {settings.max_code_chars} characters)")
    if "\x00" in code:
        raise AppError(422, "Code contains invalid characters")
    return code


def get_open_attempt(db: Session, student_id: int, experiment: Experiment, now=None) -> Attempt:
    attempt = db.scalar(
        select(Attempt)
        .where(Attempt.student_id == student_id, Attempt.experiment_id == experiment.id, Attempt.status == "in_progress")
        .order_by(Attempt.attempt_number.desc())
    )
    if attempt:
        return attempt
    number = (db.scalar(
        select(func.max(Attempt.attempt_number)).where(Attempt.student_id == student_id, Attempt.experiment_id == experiment.id)
    ) or 0) + 1
    attempt = Attempt(
        student_id=student_id, experiment_id=experiment.id, attempt_number=number,
        max_score=experiment.max_score, started_at=now or utcnow(),
    )
    db.add(attempt)
    db.flush()
    return attempt


def _overall_status(outcomes: list[TestOutcome]) -> str:
    passed = sum(1 for o in outcomes if o.passed)
    if outcomes and passed == len(outcomes):
        return "passed"
    return "partial" if passed else "failed"


def _execute(
    db: Session, student: Student, experiment: Experiment, code: str, kind: str, now=None, sandbox=None
) -> ExecutionReport:
    now = now or utcnow()
    code = validate_code(code)
    if kind == "submit":
        tests = list(experiment.test_cases)
    else:  # runs only touch visible tests, so hidden cases stay a surprise until grading
        tests = [t for t in experiment.test_cases if not t.is_hidden] or list(experiment.test_cases)
    if not tests:
        raise AppError(400, "This experiment has no test cases yet")

    outcomes = evaluate_code(code, tests, sandbox)
    ratio = score_ratio(outcomes)
    attempt = get_open_attempt(db, student.id, experiment, now)

    previous_best = None
    if kind == "submit":
        previous_best = db.scalar(
            select(func.max(Submission.score / func.nullif(Submission.max_score, 0))).where(
                Submission.student_id == student.id, Submission.experiment_id == experiment.id, Submission.kind == "submit"
            )
        )

    submission = Submission(
        attempt_id=attempt.id, student_id=student.id, experiment_id=experiment.id, kind=kind, code=code,
        status=_overall_status(outcomes), passed_count=sum(1 for o in outcomes if o.passed),
        total_count=len(outcomes), score=round(ratio * experiment.max_score, 1), max_score=experiment.max_score,
        runtime_ms=max((o.runtime_ms for o in outcomes), default=0), created_at=now,
    )
    db.add(submission)
    db.flush()
    for o in outcomes:
        submission.results.append(ExecutionResult(
            test_case_id=o.test_case_id, test_name=o.name, test_kind=o.kind, is_hidden=o.is_hidden,
            passed=o.passed, status=o.status, stdin=o.stdin, expected_output=o.expected_output,
            actual_output=o.actual_output, stderr=o.stderr, error_type=o.error_type,
            runtime_ms=o.runtime_ms, timed_out=o.timed_out,
        ))

    found = mistake_service.classify_outcomes(code, outcomes)
    mistake_service.record_mistakes(db, student.id, experiment.id, submission.id, kind, found, now)

    report = ExecutionReport(submission=submission, attempt=attempt, mistakes=found)
    if kind == "run":
        attempt.run_count += 1
        db.flush()
        try:  # starting the experiment (not only submitting it) means the recommendation was followed
            reco_service.mark_followed(db, student.id, experiment.id, now)
        except Exception:  # noqa: BLE001
            log.exception("Could not mark the recommendation as followed")
        return report

    attempt.status, attempt.score, attempt.submitted_at = "submitted", submission.score, now
    db.flush()
    # The learning layers must never make a graded submission fail: log and continue.
    try:
        report.skill_changes = skill_service.update_skills_for_submission(
            db, student.id, experiment, ratio, previous_best, now
        )
        reco_service.mark_followed(db, student.id, experiment.id, now)
        report.recommendation = reco_service.refresh_recommendation(db, student.id, now)
    except Exception:  # noqa: BLE001
        log.exception("Learning-layer update failed for submission %s", submission.id)
    return report


def run_visible_tests(db, student, experiment, code, now=None, sandbox=None) -> ExecutionReport:
    return _execute(db, student, experiment, code, "run", now, sandbox)


def submit_solution(db, student, experiment, code, now=None, sandbox=None) -> ExecutionReport:
    return _execute(db, student, experiment, code, "submit", now, sandbox)
