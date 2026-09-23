"""The LabPilot AI intelligence layer: Mistake DNA, Skill Passport, Adaptive Engine, Copilot context, What-If, teacher analytics."""
import json
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.ai import copilot as copilot_service
from app.ai.base import AIProvider
from app.ai.providers import MockProvider
from app.core.constants import CATEGORIES
from app.models import ExecutionResult, Experiment, MistakeRecord, SkillEvidence, SkillRecord, Student, Submission
from app.services import analytics
from app.services import mistakes as mistake_service
from app.services import skills as skill_service
from app.services import submissions as submission_service
from app.utils.timeutil import utcnow
from tests.helpers import code, run, submit


def days_ago(n):
    return utcnow() - timedelta(days=n)


def sid_of(db, api_student):
    return db.scalar(select(Student.id).where(Student.user_id == api_student.user["id"]))


class Capture(AIProvider):
    name, label, is_real, model = "capture", "Capture", True, "c"

    def __init__(self):
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        return json.dumps({"explanation": "e", "hint": "h", "concept_to_review": "c", "next_step": "n"})


# ------------------------------------------------------------------------------------ Mistake DNA
def test_the_same_bug_rerun_inside_one_attempt_counts_once(db, db_student, exp_ids):
    exp = db.get(Experiment, exp_ids["factorial"])
    for _ in range(3):
        submission_service.run_visible_tests(db, db_student, exp, code("factorial", "off_by_one"))
    rows = db.scalar(select(func.count()).select_from(MistakeRecord).where(MistakeRecord.student_id == db_student.id))
    assert rows == 3, "every run is still stored as evidence"
    profile = mistake_service.mistake_profile(db, db_student.id)
    assert profile["total"] == 1 and profile["categories"][0]["count"] == 1 and profile["categories"][0]["recurring"] is False
    submission_service.submit_solution(db, db_student, exp, code("factorial", "off_by_one"))  # same attempt, graded
    assert mistake_service.mistake_profile(db, db_student.id)["categories"][0]["count"] == 1
    submission_service.submit_solution(db, db_student, exp, code("factorial", "off_by_one"))  # a NEW attempt
    again = mistake_service.mistake_profile(db, db_student.id)["categories"][0]
    assert again["count"] == 2 and again["recurring"] is True and again["experiments_affected"] == 1 and again["practice"]


def test_recent_mistakes_feed_has_one_entry_per_attempt_and_category(db, db_student, exp_ids):
    exp = db.get(Experiment, exp_ids["factorial"])
    for _ in range(2):
        submission_service.run_visible_tests(db, db_student, exp, code("factorial", "off_by_one"))
    submission_service.submit_solution(db, db_student, exp, code("factorial", "prompt"))
    feed = mistake_service.recent_mistakes(db, db_student.id)
    assert [f["category"] for f in feed] == ["input_handling", "loop_condition"]
    assert feed[0]["experiment_title"] == "Factorial Calculator" and feed[0]["detail"]


def test_improvement_compares_the_last_two_14_day_periods(db, db_student, exp_ids):
    exp = db.get(Experiment, exp_ids["factorial"])
    for d in (22, 21, 20):
        submission_service.submit_solution(db, db_student, exp, code("factorial", "off_by_one"), now=days_ago(d))
    assert mistake_service.mistake_profile(db, db_student.id)["improvement"]["direction"] == "not_enough_data"
    for d in (3, 2, 1):
        submission_service.submit_solution(db, db_student, exp, code("factorial", "correct"), now=days_ago(d))
    profile = mistake_service.mistake_profile(db, db_student.id)
    imp = profile["improvement"]
    assert imp["direction"] == "improving" and imp["previous"]["per_attempt"] == 1.0 and imp["recent"]["per_attempt"] == 0.0
    assert "fewer mistakes" in imp["message"] and imp["improved_categories"] == ["Loop-condition errors"]
    assert profile["categories"][0]["trend"] == "quiet"


def test_worsening_and_steady_directions(db, db_student, exp_ids):
    exp = db.get(Experiment, exp_ids["factorial"])
    for d in (22, 21, 20):
        submission_service.submit_solution(db, db_student, exp, code("factorial", "correct"), now=days_ago(d))
    for d in (3, 2, 1):
        submission_service.submit_solution(db, db_student, exp, code("factorial", "off_by_one"), now=days_ago(d))
    imp = mistake_service.mistake_profile(db, db_student.id)["improvement"]
    assert imp["direction"] == "worsening" and imp["worsening_categories"] == ["Loop-condition errors"]


def test_dashboard_carries_top_recurring_recent_trend_and_practice(client, student, exp_ids):
    for variant in ("off_by_one", "off_by_one", "prompt"):
        submit(client, student.headers, exp_ids["factorial"], code("factorial", variant))
    m = client.get("/api/students/me/dashboard", headers=student.headers).json()["mistakes"]
    top = m["categories"][0]
    assert top["category"] == "loop_condition" and top["recurring"] and top["count"] == 2 and top["practice"]
    assert [r["category"] for r in m["recent"]][:2] == ["input_handling", "loop_condition"]
    assert m["improvement"]["direction"] in {"not_enough_data", "improving", "steady", "worsening"} and m["improvement"]["message"]


# ------------------------------------------------------------------------------------ Copilot
def test_copilot_context_reports_recurrence_and_recent_mistakes(db, db_student, exp_ids):
    exp = db.get(Experiment, exp_ids["factorial"])
    submission_service.submit_solution(db, db_student, exp, code("factorial", "off_by_one"))
    submission_service.submit_solution(db, db_student, exp, code("factorial", "off_by_one"))
    provider = Capture()
    copilot_service.get_hint(db, db_student, exp, code("factorial", "off_by_one"), provider=provider)
    request = provider.requests[0]
    assert request.context["pattern"] == {"times_before": 1, "experiments_affected": 1, "same_experiment": 1}
    assert request.context["recent_mistakes"][0] == {"label": "Loop-condition errors", "experiment": "Factorial Calculator"}
    assert "also appeared in 1 earlier attempt" in request.user_prompt and "Recent mistakes, newest first" in request.user_prompt


def test_rule_based_guidance_mentions_a_recurring_pattern(db, db_student, exp_ids):
    exp = db.get(Experiment, exp_ids["factorial"])
    first = submission_service.submit_solution(db, db_student, exp, code("factorial", "prompt"))
    assert first.mistakes
    fresh = copilot_service.get_hint(db, db_student, exp, code("factorial", "prompt"), provider=MockProvider())
    assert "earlier attempt" not in fresh["explanation"]
    submission_service.submit_solution(db, db_student, exp, code("factorial", "prompt"))
    repeated = copilot_service.get_hint(db, db_student, exp, code("factorial", "prompt"), provider=MockProvider())
    assert "1 earlier attempt too" in repeated["explanation"] and repeated["error_category"] == "input_handling"
    assert repeated["hint"] and repeated["concept_to_review"] and repeated["next_step"]


def test_hidden_data_echoed_by_an_error_message_is_redacted(client, db, db_student, teacher_headers):
    body = {
        "title": "Parse an Integer", "difficulty": "beginner", "skills": ["Python Basics"], "objective": "Read an integer.",
        "problem_statement": "Read one integer and print it.", "starter_code": "", "reference_solution": "print(int(input()))\n",
        "is_published": True,
        "test_cases": [{"name": "plain", "stdin": "5\n", "expected_output": "5\n"},
                       {"name": "secret", "stdin": "abc999\n", "expected_output": "0\n", "is_hidden": True}],
    }
    exp_id = client.post("/api/teacher/experiments", json=body, headers=teacher_headers).json()["id"]
    exp = db.get(Experiment, exp_id)
    submission_service.submit_solution(db, db_student, exp, "print(int(input()))\n")
    provider = Capture()
    copilot_service.get_hint(db, db_student, exp, "print(int(input()))\n", provider=provider)
    db.commit()  # release the write lock before the API deletes the experiment
    request = provider.requests[0]
    everything = json.dumps(request.context) + request.user_prompt
    assert "abc999" not in everything
    client.delete(f"/api/teacher/experiments/{exp_id}", headers=teacher_headers)


# ------------------------------------------------------------------------------------ Skill Passport
def test_every_skill_change_is_logged_and_adds_up(client, db, student, exp_ids):
    submit(client, student.headers, exp_ids["factorial"], code("factorial", "off_by_one"))
    submit(client, student.headers, exp_ids["factorial"], code("factorial", "correct"))
    client.post(f"/api/experiments/{exp_ids['factorial']}/whatif/run", json={"scenario_id": "range-off-by-one", "prediction": "24"}, headers=student.headers)
    sid = sid_of(db, student)
    events = db.scalars(select(SkillEvidence).where(SkillEvidence.student_id == sid)).all()
    assert {e.source for e in events} == {"submission", "debugging", "whatif"}
    assert all(e.experiment_id == exp_ids["factorial"] for e in events)
    for record in db.scalars(select(SkillRecord).where(SkillRecord.student_id == sid)):
        total = sum(e.delta for e in events if e.skill == record.skill)
        assert total == pytest.approx(record.mastery, abs=0.6), record.skill
        assert sum(1 for e in events if e.skill == record.skill) == record.evidence_count


def test_passport_shows_contributing_experiments_recent_skills_and_practice(client, student, exp_ids):
    submit(client, student.headers, exp_ids["factorial"], code("factorial", "correct"))
    passport = client.get("/api/skills/me", headers=student.headers).json()
    loops = next(s for s in passport["skills"] if s["skill"] == "Loops")
    assert loops["recently_demonstrated"] and loops["recent_change"] > 0
    assert [(c["title"], c["source"], c["events"], c["best_percent"]) for c in loops["contributors"]] == [("Factorial Calculator", "submission", 1, 100)]
    assert {t["title"] for t in loops["trained_by"]} >= {"Factorial Calculator", "List Statistics"}
    assert "Loops" in [r["skill"] for r in passport["recent"]]
    sorting = next(s for s in passport["skills"] if s["skill"] == "Sorting & Searching")
    assert sorting["contributors"] == [] and not sorting["recently_demonstrated"] and sorting["needs_practice"]
    practice = {p["skill"]: p for p in passport["practice"]}
    assert "Sorting & Searching" in practice and practice["Sorting & Searching"]["suggestion"]["status"] == "not_started"
    assert loops["mastery"] < 45 and loops["needs_practice"]  # one experiment does not make a skill proficient


def test_old_evidence_is_not_recently_demonstrated(db, db_student, exp_ids):
    exp = db.get(Experiment, exp_ids["factorial"])
    submission_service.submit_solution(db, db_student, exp, code("factorial", "correct"), now=days_ago(30))
    passport = skill_service.get_passport(db, db_student.id)
    loops = next(s for s in passport["skills"] if s["skill"] == "Loops")
    assert loops["evidence_count"] == 1 and not loops["recently_demonstrated"] and passport["recent"] == []
    assert loops["contributors"][0]["last_at"] < days_ago(29)


def test_deleting_an_experiment_keeps_mastery_but_drops_its_contribution(client, db, student, teacher_headers):
    body = {"title": "Echo a Number", "difficulty": "beginner", "skills": ["Loops"], "objective": "x", "problem_statement": "Echo.",
            "starter_code": "", "reference_solution": "print(input())\n", "is_published": True,
            "test_cases": [{"name": "t", "stdin": "1\n", "expected_output": "1\n"}]}
    exp_id = client.post("/api/teacher/experiments", json=body, headers=teacher_headers).json()["id"]
    submit(client, student.headers, exp_id, "print(input())\n")
    before = next(s for s in client.get("/api/skills/me", headers=student.headers).json()["skills"] if s["skill"] == "Loops")
    assert [c["title"] for c in before["contributors"]] == ["Echo a Number"]
    client.delete(f"/api/teacher/experiments/{exp_id}", headers=teacher_headers)
    after = next(s for s in client.get("/api/skills/me", headers=student.headers).json()["skills"] if s["skill"] == "Loops")
    assert after["mastery"] == before["mastery"] and after["contributors"] == []


# ------------------------------------------------------------------------------------ Adaptive engine
def test_reason_names_the_recent_struggle_and_is_kept_in_history(client, student, exp_ids):
    for _ in range(2):
        submit(client, student.headers, exp_ids["factorial"], code("factorial", "off_by_one"))
    rec = client.get("/api/recommendations/me", headers=student.headers).json()["recommendation"]
    assert "Recommended because you recently struggled with loop-condition errors (2x)" in rec["reason"]
    history = client.get("/api/recommendations/me/history", headers=student.headers).json()
    assert history[0]["reason"] == rec["reason"] and history[0]["signals"]["top_mistakes"][0][0] == "loop_condition"


def test_failed_test_cases_are_counted_from_the_stored_results(client, db, student, exp_ids):
    submit(client, student.headers, exp_ids["liststats"], code("liststats", "max_zero"))
    signals = client.get("/api/recommendations/me", headers=student.headers).json()["recommendation"]["signals"]
    sid = sid_of(db, student)

    def failed(kind):
        return db.scalar(select(func.count()).select_from(ExecutionResult).join(Submission, Submission.id == ExecutionResult.submission_id)
                         .where(Submission.student_id == sid, ExecutionResult.passed.is_(False), ExecutionResult.test_kind == kind))
    assert signals["failed_cases"]["edge"] == failed("edge") >= 1
    assert signals["failed_cases"]["normal"] == failed("normal")


# ------------------------------------------------------------------------------------ What-If
def whatif(client, student, exp_id, prediction, stdin):
    return client.post(f"/api/experiments/{exp_id}/whatif/run", json={"scenario_id": "range-off-by-one", "prediction": prediction, "stdin": stdin}, headers=student.headers).json()


def test_only_the_first_try_at_a_scenario_and_input_earns_credit(client, db, student, exp_ids):
    exp = exp_ids["factorial"]
    sid = sid_of(db, student)
    mastery = lambda: db.scalar(select(SkillRecord.mastery).where(SkillRecord.student_id == sid, SkillRecord.skill == "Problem Solving")) or 0.0  # noqa: E731
    miss = whatif(client, student, exp, "99", "4\n")
    assert miss["matched"] is False and miss["credited"] is False
    copied = whatif(client, student, exp, "6", "4\n")  # right answer, but after seeing the result for this input
    assert copied["matched"] is True and copied["credited"] is False and copied["skill_change"] is None
    assert "already tried this input" in copied["explanation"]
    db.expire_all()
    assert mastery() == 0.0
    fresh = whatif(client, student, exp, "24", "5\n")  # a different input, predicted before running
    assert fresh["matched"] is True and fresh["credited"] is True and fresh["skill_change"]["delta"] > 0
    db.expire_all()
    assert mastery() > 0
    history = client.get(f"/api/experiments/{exp}/whatif", headers=student.headers).json()["history"]
    assert [(h["matched"], h["credited"]) for h in history] == [(True, True), (True, False), (False, False)]
    assert all(h["prediction"] and h["actual_output"] and h["explanation"] for h in history)


# ------------------------------------------------------------------------------------ Teacher intelligence
def test_skill_distribution_and_completion_equal_sql(client, db, student, teacher_headers, exp_ids):
    submit(client, student.headers, exp_ids["factorial"], code("factorial", "correct"))
    o = client.get("/api/teacher/overview", headers=teacher_headers).json()
    students_total = db.scalar(select(func.count()).select_from(Student))
    for entry in o["skill_distribution"]:
        with_evidence = db.scalar(select(func.count()).select_from(SkillRecord).where(SkillRecord.skill == entry["skill"], SkillRecord.evidence_count > 0))
        assert entry["students_with_evidence"] == with_evidence == sum(entry["levels"].values())
        assert entry["not_started"] == students_total - with_evidence
    assert [e["skill"] for e in o["skill_distribution"]][:2] == ["Python Basics", "Loops"]
    for exp in o["experiments"]:
        c = exp["completion"]
        assert c["mastered"] + c["attempted"] + c["in_progress"] + c["not_started"] == students_total
        best = db.execute(select(Submission.student_id, func.max(Submission.score / func.nullif(Submission.max_score, 0)))
                          .where(Submission.kind == "submit", Submission.experiment_id == exp["id"]).group_by(Submission.student_id)).all()
        assert c["mastered"] == sum(1 for _, r in best if r >= 0.8) and c["mastered"] + c["attempted"] == len(best)
    assert o["completion"]["possible"] == students_total * o["counts"]["published_experiments"]


def test_difficulty_label_uses_the_first_attempt_score():
    assert analytics._difficulty_label(30, 5) == "Hard" and analytics._difficulty_label(60, 5) == "Moderate"
    assert analytics._difficulty_label(90, 5) == "Easy" and analytics._difficulty_label(30, 1) == "Not enough data"
    assert analytics._difficulty_label(None, 0) == "Not enough data"


def test_top_mistake_per_experiment_is_class_level_only(client, student, teacher_headers, exp_ids):
    submit(client, student.headers, exp_ids["factorial"], code("factorial", "off_by_one"))
    o = client.get("/api/teacher/overview", headers=teacher_headers).json()
    factorial = next(e for e in o["experiments"] if e["id"] == exp_ids["factorial"])
    assert set(factorial["top_mistake"]) == {"category", "label", "count", "students_affected"}


def test_support_list_flags_struggling_students_using_scores_and_attempts_only(client, db, db_student, teacher_headers, exp_ids):
    exp = db.get(Experiment, exp_ids["factorial"])
    for variant in ("syntax", "off_by_one", "off_by_one"):
        submission_service.submit_solution(db, db_student, exp, code("factorial", variant), now=days_ago(2))
    db.commit()
    flagged = {f["student_id"]: f for f in analytics.students_needing_practice(db, limit=10_000)}
    mine = flagged[db_student.id]
    assert mine["priority"] == "high"
    assert any("without mastering Factorial Calculator" in r for r in mine["reasons"]) and any("Average best score is 33%" in r for r in mine["reasons"])
    api = client.get("/api/teacher/overview", headers=teacher_headers).json()["needs_practice"]
    assert api and set(api[0]) == {"student_id", "full_name", "roll_number", "priority", "reasons", "average_percent", "graded_submissions", "last_active"}
    labels = {v["label"].lower() for v in CATEGORIES.values()}
    assert not any(label in reason.lower() for f in api for reason in f["reasons"] for label in labels)


def test_a_student_who_mastered_everything_quickly_is_not_flagged(db, db_student, exp_ids):
    exp = db.get(Experiment, exp_ids["factorial"])
    submission_service.submit_solution(db, db_student, exp, code("factorial", "correct"), now=days_ago(1))
    db.commit()
    assert db_student.id not in {f["student_id"] for f in analytics.students_needing_practice(db, limit=10_000)}


def test_inactive_students_with_unmastered_work_are_flagged(db, db_student, exp_ids):
    exp = db.get(Experiment, exp_ids["factorial"])
    submission_service.submit_solution(db, db_student, exp, code("factorial", "correct"), now=days_ago(12))
    db.commit()
    mine = {f["student_id"]: f for f in analytics.students_needing_practice(db, limit=10_000)}[db_student.id]
    assert any("No submissions for 12 days" in r for r in mine["reasons"])


# ------------------------------------------------------------------------------------ the whole learning loop
def test_the_complete_learning_loop_through_the_api(client, db, student, exp_ids):
    exp = exp_ids["factorial"]
    sid = sid_of(db, student)
    detail = client.get(f"/api/experiments/{exp}", headers=student.headers).json()                       # 1 open the experiment
    assert detail["current_attempt"]["attempt_number"] == 1
    ran = run(client, student.headers, exp, code("factorial", "off_by_one"))                              # 2 attempt it
    assert ran["submission"]["status"] != "passed"
    graded = submit(client, student.headers, exp, code("factorial", "off_by_one"))                        # 3 submit
    assert graded["submission"]["total_count"] == 6 and graded["submission"]["passed_count"] == 2          # 4 test results
    assert [m["category"] for m in graded["mistakes"]] == ["loop_condition"]                              # 6 mistake recorded
    hint = client.post(f"/api/experiments/{exp}/copilot/hint", json={"code": code("factorial", "off_by_one")}, headers=student.headers).json()
    assert hint["error_category"] == "loop_condition" and hint["hint"] and hint["concept_to_review"]     # 5 Copilot guidance
    dna = client.get("/api/students/me/dashboard", headers=student.headers).json()["mistakes"]           # 7 Mistake DNA updates
    assert dna["categories"][0]["category"] == "loop_condition" and dna["recent"][0]["submission_id"] == graded["submission"]["id"]
    loops = next(s for s in client.get("/api/skills/me", headers=student.headers).json()["skills"] if s["skill"] == "Loops")
    assert loops["mastery"] > 0 and loops["contributors"][0]["experiment_id"] == exp                    # 8 skill progress updates
    rec = client.get("/api/recommendations/me", headers=student.headers).json()["recommendation"]        # 9 next experiment
    assert rec["signals"]["top_mistakes"][0][0] == "loop_condition" and "loop-condition errors" in rec["reason"]
    stored = client.get("/api/recommendations/me/history", headers=student.headers).json()
    assert stored and stored[0]["id"] == rec["id"]
    wi = whatif(client, student, exp, "6", "4\n")                                                         # 10 What-If
    assert wi["matched"] and wi["actual_output"] == "6" and wi["explanation"]
    assert db.scalar(select(func.count()).select_from(MistakeRecord).where(MistakeRecord.student_id == sid)) >= 2
    fixed = submit(client, student.headers, exp, code("factorial", "correct"))                            # ...and the loop closes
    assert fixed["submission"]["status"] == "passed" and "Debugging" in {c["skill"] for c in fixed["skill_changes"]}
    assert fixed["recommendation"]["experiment_id"] != exp
