"""Seed the database with the experiment catalogue and a demo cohort.

    python -m app.seed             # seed if the database is empty
    python -m app.seed --reset     # drop every table, then seed
    python -m app.seed --minimal   # teacher account + experiments only, no demo students
    python -m app.seed --check     # verify reference solutions against the sandbox (no database changes)
"""
import logging
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import copilot as copilot_service
from app.ai.providers import MockProvider
from app.models import Experiment, User
from app.schemas.experiment import ExperimentCreate
from app.seed import catalogue, demo
from app.seed.snippets import SNIPPETS
from app.services import accounts
from app.services import experiments as experiment_service
from app.services import recommendation as reco_service
from app.services import submissions as submission_service
from app.services import whatif as whatif_service
from app.services.evaluation import TestSpec, evaluate_code
from app.utils.timeutil import utcnow

log = logging.getLogger("labpilot.seed")
EXPERIMENT_KEYS = ["factorial", "liststats", "debug", "prime", "sort"]


def check_references() -> list[str]:
    """Return a list of problems (empty when every reference solution passes every test case)."""
    problems = []
    for data in catalogue.EXPERIMENTS:
        outcomes = evaluate_code(data["reference_solution"], [TestSpec(**t) for t in data["test_cases"]])
        for o in outcomes:
            if not o.passed:
                problems.append(f"{data['title']}: '{o.name}' -> {o.status}")
    return problems


def seed_catalogue(db: Session, teacher) -> dict[str, Experiment]:
    by_key = {}
    for key, data in zip(EXPERIMENT_KEYS, catalogue.EXPERIMENTS):
        by_key[key] = experiment_service.create_experiment(db, teacher, ExperimentCreate(**data))
    return by_key


def _at(now, days_ago: int, hhmm: str):
    hour, minute = (int(x) for x in hhmm.split(":"))
    return (now - timedelta(days=days_ago)).replace(hour=hour, minute=minute, second=0, microsecond=0)


def replay_journey(db: Session, student, steps, experiments: dict[str, Experiment], now) -> None:
    provider = MockProvider()  # seeded hints are always rule-based, so seeding never calls a paid API
    for kind, exp_key, variant, days_ago, hhmm, prediction in steps:
        exp, ts = experiments[exp_key], _at(now, days_ago, hhmm)
        if kind == "whatif":
            whatif_service.run_whatif(db, student, exp, variant, prediction, provider=provider, now=ts)
            continue
        code = SNIPPETS[exp_key][variant]
        if kind == "run":
            submission_service.run_visible_tests(db, student, exp, code, now=ts)
        elif kind == "submit":
            submission_service.submit_solution(db, student, exp, code, now=ts)
        elif kind == "hint":
            copilot_service.get_hint(db, student, exp, code, provider=provider, now=ts)
        else:
            raise ValueError(f"Unknown journey step '{kind}'")
    db.flush()


def seed_all(db: Session, minimal: bool = False) -> dict:
    accounts.ensure_roles(db)
    if db.scalar(select(func.count()).select_from(User)):
        return {"seeded": False}
    now = utcnow()
    t = demo.TEACHER
    teacher = accounts.create_teacher(db, t["email"], t["password"], t["full_name"], t["department"])
    experiments = seed_catalogue(db, teacher)
    students = {}
    if not minimal:
        for s in demo.STUDENTS:
            students[s["key"]] = accounts.create_student(db, s["email"], s["password"], s["full_name"], s["roll_number"], s["cohort"])
        for key, steps in demo.JOURNEYS.items():
            log.info("Replaying study history for %s (%d steps)", key, len(steps))
            replay_journey(db, students[key], steps, experiments, now)
            reco_service.refresh_recommendation(db, students[key].id, now)
    db.commit()
    return {"seeded": True, "experiments": len(experiments), "students": len(students)}
