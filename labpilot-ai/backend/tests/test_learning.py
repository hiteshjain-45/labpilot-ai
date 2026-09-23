"""Mistake DNA, Skill Passport and the Adaptive Experiment Engine."""
import pytest
from sqlalchemy import select

from app.models import Experiment, ExperimentRecommendation
from app.seed.catalogue import EXPERIMENTS
from app.services import mistakes as mistake_service
from app.services import recommendation as reco
from app.services import skills as skill_service
from app.services import submissions as submission_service
from app.services.evaluation import TestSpec, evaluate_code
from tests.helpers import code, submit

KEYS = ["factorial", "liststats", "debug", "prime", "sort"]


def _classify(exp_key, variant):
    source = code(exp_key, variant)
    tests = [TestSpec(**t) for t in EXPERIMENTS[KEYS.index(exp_key)]["test_cases"]]
    found = mistake_service.classify_outcomes(source, evaluate_code(source, tests))
    return mistake_service.primary_category(found), {m.category for m in found}


# ---------------------------------------------------------------- Mistake DNA
@pytest.mark.parametrize(
    "exp_key, variant, expected",
    [
        ("factorial", "syntax", "syntax"),
        ("factorial", "prompt", "input_handling"),
        ("factorial", "off_by_one", "loop_condition"),
        ("liststats", "index_error", "array_index"),
        ("liststats", "max_zero", "boundary"),
        ("liststats", "floor_div", "logic"),
        ("debug", "starter", "input_handling"),
        ("debug", "tie_picks_last", "logic"),
        ("prime", "sqrt_exclusive", "loop_condition"),
        ("sort", "descending", "logic"),
    ],
)
def test_common_mistakes_are_classified(exp_key, variant, expected):
    assert _classify(exp_key, variant)[0] == expected


@pytest.mark.parametrize("exp_key", KEYS)
def test_correct_solutions_produce_no_mistakes(exp_key):
    assert _classify(exp_key, "correct") == (None, set())


def test_slow_correct_solution_is_flagged_as_inefficient():
    primary, all_cats = _classify("prime", "naive")
    assert primary == "inefficient" and all_cats == {"inefficient"}


def test_loops_that_start_at_one_on_purpose_are_not_flagged():
    # insertion sort compares each item with the previous one, so range(1, n) is deliberate
    assert not mistake_service.has_suspect_range(mistake_service._parse(code("sort", "correct")))
    assert mistake_service.has_suspect_range(mistake_service._parse(code("factorial", "off_by_one")))


def test_syntax_errors_short_circuit_other_categories():
    _, cats = _classify("factorial", "syntax")
    assert cats == {"syntax"}


def test_mistake_profile_counts_trends_and_practice(db, db_student, exp_ids):
    exps = {e.id: e for e in db.scalars(select(Experiment))}
    for variant in ("off_by_one", "off_by_one", "prompt"):
        submission_service.submit_solution(db, db_student, exps[exp_ids["factorial"]], code("factorial", variant))
    db.commit()
    profile = mistake_service.mistake_profile(db, db_student.id)
    by_cat = {c["category"]: c for c in profile["categories"]}
    assert profile["total"] == 3 and by_cat["loop_condition"]["count"] == 2 and by_cat["loop_condition"]["recurring"]
    assert by_cat["loop_condition"]["percent"] == pytest.approx(66.7, abs=0.1)
    assert by_cat["loop_condition"]["trend"] == "new" and by_cat["input_handling"]["recurring"] is False
    assert by_cat["loop_condition"]["practice"], "recurring mistakes come with practice suggestions"
    assert by_cat["loop_condition"]["concept"] and by_cat["loop_condition"]["tip"]


def test_class_summary_contains_no_student_identifiers(db, db_student, exp_ids):
    exp = db.get(Experiment, exp_ids["factorial"])
    submission_service.submit_solution(db, db_student, exp, code("factorial", "off_by_one"))
    db.commit()
    summary = mistake_service.class_mistake_summary(db)
    assert summary and all(set(row) == {"category", "label", "count", "students_affected"} for row in summary)


# ---------------------------------------------------------------- Skill Passport
def test_evidence_moves_mastery_faster_up_than_down():
    up = skill_service.apply_evidence(0, 1.0, 1.0)
    down = 100 - skill_service.apply_evidence(100, 0.0, 1.0)
    assert up == 30.0 and down == 10.0 and up > down


def test_evidence_is_clamped_and_weighted():
    assert skill_service.apply_evidence(95, 5.0, 1.0) <= 100
    assert skill_service.apply_evidence(5, -3.0, 1.0) >= 0
    assert skill_service.apply_evidence(0, 1.0, 1.25) > skill_service.apply_evidence(0, 1.0, 0.8)


def test_unknown_skills_are_ignored(db, db_student):
    assert skill_service.record_skill_evidence(db, db_student.id, "Telepathy", 1.0, 1.0) is None


def test_passport_lists_every_skill_with_levels(db, db_student):
    passport = skill_service.get_passport(db, db_student.id)
    assert len(passport["skills"]) == 7 and passport["overall"] == 0 and passport["strongest"] is None
    skill_service.record_skill_evidence(db, db_student.id, "Loops", 1.0, 1.0)
    skill_service.record_skill_evidence(db, db_student.id, "Loops", 1.0, 1.0)
    skill_service.record_skill_evidence(db, db_student.id, "Arrays", 1.0, 0.8)
    passport = skill_service.get_passport(db, db_student.id)
    loops = next(s for s in passport["skills"] if s["skill"] == "Loops")
    assert loops["mastery"] == 51.0 and loops["evidence_count"] == 2 and loops["level"] == "Proficient"
    assert passport["strongest"] == "Loops" and passport["weakest"] == "Arrays"


def test_skills_endpoint_reflects_submissions(client, student, exp_ids):
    submit(client, student.headers, exp_ids["liststats"], code("liststats", "correct"))
    passport = client.get("/api/skills/me", headers=student.headers).json()
    trained = {s["skill"] for s in passport["skills"] if s["mastery"] > 0}
    assert trained == {"Arrays", "Loops", "Python Basics"} and passport["overall"] > 0


# ---------------------------------------------------------------- Adaptive Experiment Engine
def test_new_student_is_recommended_the_first_beginner_experiment(db, db_student, exp_ids):
    rec = reco.compute_recommendation(db, db_student.id)
    assert rec.experiment.id == exp_ids["factorial"] and rec.difficulty == "beginner"
    assert rec.signals["decision"] == "new" and "not submitted anything yet" in rec.reason


def test_strong_results_advance_the_student_to_the_next_level(db, db_student, exp_ids):
    for key in ("factorial", "liststats"):
        submission_service.submit_solution(db, db_student, db.get(Experiment, exp_ids[key]), code(key, "correct"))
    rec = reco.compute_recommendation(db, db_student.id)
    assert rec.difficulty == "intermediate" and rec.signals["decision"] == "advance"
    assert "average 100%" in rec.reason and "intermediate" in rec.reason


def test_finishing_a_level_before_advancing(db, db_student, exp_ids):
    submission_service.submit_solution(db, db_student, db.get(Experiment, exp_ids["factorial"]), code("factorial", "correct"))
    rec = reco.compute_recommendation(db, db_student.id)
    assert rec.experiment.id == exp_ids["liststats"] and rec.signals["decision"] == "consolidate"


def test_weak_results_ease_the_difficulty(db, db_student, exp_ids):
    submission_service.submit_solution(db, db_student, db.get(Experiment, exp_ids["debug"]), code("debug", "starter"))
    rec = reco.compute_recommendation(db, db_student.id)
    assert rec.signals["decision"] == "ease" and rec.difficulty == "beginner"
    assert "steps back" in rec.reason


def test_recurring_mistakes_influence_the_choice(db, db_student, exp_ids):
    for _ in range(3):
        submission_service.submit_solution(db, db_student, db.get(Experiment, exp_ids["factorial"]), code("factorial", "off_by_one"))
    rec = reco.compute_recommendation(db, db_student.id)
    assert "loop-condition errors (3x)" in rec.reason
    assert list(rec.signals["top_mistakes"][0]) == ["loop_condition", 3]


def test_recommendation_refresh_does_not_create_duplicates(db, db_student, exp_ids):
    first = reco.refresh_recommendation(db, db_student.id)
    second = reco.refresh_recommendation(db, db_student.id)
    db.commit()
    assert first.id == second.id
    assert len(db.scalars(select(ExperimentRecommendation).where(ExperimentRecommendation.student_id == db_student.id)).all()) == 1


def test_following_a_recommendation_is_recorded(client, student, exp_ids):
    before = client.get("/api/recommendations/me", headers=student.headers).json()["recommendation"]
    assert before["experiment_id"] == exp_ids["factorial"] and before["followed"] is False
    submit(client, student.headers, exp_ids["factorial"], code("factorial", "correct"))
    history = client.get("/api/recommendations/me/history", headers=student.headers).json()
    assert any(h["experiment_id"] == exp_ids["factorial"] and h["followed"] for h in history)
    after = client.get("/api/recommendations/me", headers=student.headers).json()["recommendation"]
    assert after["experiment_id"] != exp_ids["factorial"]


def test_no_recommendation_once_everything_is_mastered(db, db_student, exp_ids):
    for key in ("factorial", "liststats", "debug", "prime", "sort"):
        submission_service.submit_solution(db, db_student, db.get(Experiment, exp_ids[key]), code(key, "correct"))
    assert reco.compute_recommendation(db, db_student.id) is None


def test_dashboard_aggregates_the_learning_layers(client, student, exp_ids):
    submit(client, student.headers, exp_ids["factorial"], code("factorial", "off_by_one"))
    submit(client, student.headers, exp_ids["factorial"], code("factorial", "correct"))
    d = client.get("/api/students/me/dashboard", headers=student.headers).json()
    assert d["stats"]["experiments_mastered"] == 1 and d["stats"]["submissions"] == 2
    assert [p["percent"] for p in d["score_history"]] == [33, 100]
    assert d["recommendation"] and d["passport"]["overall"] > 0
    assert d["mistakes"]["categories"][0]["category"] == "loop_condition"
    assert [a["attempt_number"] for a in d["recent_attempts"]] == [2, 1]
    mine = client.get("/api/mistakes/me", headers=student.headers).json()
    assert mine["total"] == 1 and mine["recent"][0]["experiment_title"] == "Factorial Calculator"


def test_running_the_recommended_experiment_marks_it_as_followed(client, student, exp_ids):
    from tests.helpers import run

    before = client.get("/api/recommendations/me", headers=student.headers).json()["recommendation"]
    assert before["followed"] is False
    run(client, student.headers, before["experiment_id"], "print(1)")
    history = client.get("/api/recommendations/me/history", headers=student.headers).json()
    assert any(h["experiment_id"] == before["experiment_id"] and h["followed"] for h in history)
