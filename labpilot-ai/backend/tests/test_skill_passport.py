"""The Skill Passport page: one read-only view composed from data that already exists."""
import pytest
from sqlalchemy import func, select

from app.core.constants import SKILLS, SKILL_FOR_CATEGORY
from app.models import Experiment, SkillRecord, Student, Submission
from app.services import skills as skill_service
from tests.helpers import code, submit


def page(client, headers):
    r = client.get("/api/skills/me/passport", headers=headers)
    assert r.status_code == 200
    return r.json()


def test_the_page_needs_a_signed_in_student(client, teacher_headers):
    assert client.get("/api/skills/me/passport").status_code == 401
    assert client.get("/api/skills/me/passport", headers=teacher_headers).status_code == 403


def test_the_profile_and_totals_come_from_the_database(client, db, student, exp_ids):
    submit(client, student.headers, exp_ids["factorial"], code("factorial", "correct"))
    p = page(client, student.headers)
    row = db.scalars(select(Student).where(Student.user_id == student.user["id"])).first()
    assert p["profile"]["full_name"] == row.user.full_name
    assert p["profile"]["roll_number"] == row.roll_number and p["profile"]["cohort"] == row.cohort

    published = db.scalar(select(func.count()).select_from(Experiment).where(Experiment.is_published.is_(True)))
    graded = db.scalar(
        select(func.count(func.distinct(Submission.experiment_id)))
        .where(Submission.student_id == row.id, Submission.kind == "submit")
    )
    s = p["summary"]
    assert s["experiments_total"] == published and s["completed"] == graded == 1
    assert s["mastered"] == 1 and s["average_percent"] == 100
    assert s["overall_progress"] == round(100 / published)


def test_the_payload_carries_what_the_detailed_skill_record_needs(client, student):
    p = page(client, student.headers)
    assert {"overall", "recent", "practice"} <= set(p)          # the reused component reads these
    assert isinstance(p["recent"], list) and isinstance(p["practice"], list)


def test_every_skill_has_a_status_drawn_from_the_four_allowed_ones(client, student):
    p = page(client, student.headers)
    assert [s["skill"] for s in p["skills"]] == list(SKILLS)
    assert p["status_order"] == ["Developing", "Practicing", "Strong", "Mastered"]
    for s in p["skills"]:
        assert s["status"] in p["status_order"]
        assert (s["status"] == "Developing") == (s["evidence_count"] == 0 or s["mastery"] < 45 and s["recurring_mistakes"] > 0)


@pytest.mark.parametrize("mastery,evidence,mastered_exp,recurring,expected", [
    (0, 0, False, False, "Developing"),
    (20, 2, False, False, "Practicing"),
    (50, 4, False, False, "Strong"),
    (80, 6, True, False, "Mastered"),
    (80, 6, False, False, "Strong"),      # the level alone is not enough without a mastered experiment
    (60, 5, True, True, "Practicing"),    # a recurring mistake holds the skill back
    (20, 3, False, True, "Developing"),
])
def test_status_rules(mastery, evidence, mastered_exp, recurring, expected):
    skill = {"mastery": mastery, "evidence_count": evidence}
    assert skill_service.skill_status(skill, mastered_exp, recurring) == expected


def test_a_skill_status_rises_with_real_performance(client, db, student, exp_ids):
    before = next(s for s in page(client, student.headers)["skills"] if s["skill"] == "Loops")
    assert before["status"] == "Developing" and before["mastery"] == 0
    for _ in range(3):
        submit(client, student.headers, exp_ids["factorial"], code("factorial", "correct"))
        submit(client, student.headers, exp_ids["liststats"], code("liststats", "correct"))
    after = next(s for s in page(client, student.headers)["skills"] if s["skill"] == "Loops")
    assert after["mastery"] > before["mastery"] and after["status"] in ("Practicing", "Strong", "Mastered")
    stored = db.scalar(select(SkillRecord.mastery).where(SkillRecord.skill == "Loops", SkillRecord.student_id == db.scalar(select(Student.id).where(Student.user_id == student.user["id"]))))
    assert after["mastery"] == stored


def test_a_repeated_mistake_marks_its_skill_as_needing_improvement(client, student, exp_ids):
    for _ in range(2):
        submit(client, student.headers, exp_ids["factorial"], code("factorial", "off_by_one"))
    p = page(client, student.headers)
    loops = next(s for s in p["skills"] if s["skill"] == "Loops")
    assert loops["recurring_mistakes"] >= 1 and loops["status"] in ("Developing", "Practicing")
    assert any(m["label"] == "Loop-condition errors" and m["recurring"] for m in loops["mistakes"])
    assert "Loops" in [g["skill"] for g in p["needs_improvement"]]
    assert SKILL_FOR_CATEGORY["loop_condition"] == "Loops"
    top = p["mistake_dna"]["top"]
    assert top and top[0]["skill"] == "Loops" and p["mistake_dna"]["improvement"]["message"]


def test_useful_links_point_at_real_experiments(client, db, student, exp_ids):
    submit(client, student.headers, exp_ids["factorial"], code("factorial", "correct"))
    p = page(client, student.headers)
    published = {e.id for e in db.scalars(select(Experiment).where(Experiment.is_published.is_(True)))}
    for s in p["skills"]:
        if s["links"]["practice"]:
            assert s["links"]["practice"]["experiment_id"] in published and s["links"]["practice"]["status"] != "mastered"
        assert all(r["experiment_id"] in published for r in s["links"]["related"])
        assert all(c in SKILL_FOR_CATEGORY for c in s["links"]["review_mistakes"])
    loops = next(s for s in p["skills"] if s["skill"] == "Loops")
    assert {r["title"] for r in loops["links"]["related"]} >= {"Factorial Calculator", "List Statistics"}


def test_the_level_distribution_adds_up(client, db, student, exp_ids):
    submit(client, student.headers, exp_ids["factorial"], code("factorial", "correct"))
    p = page(client, student.headers)
    for band in p["by_difficulty"]:
        total = db.scalar(select(func.count()).select_from(Experiment).where(Experiment.is_published.is_(True), Experiment.difficulty == band["difficulty"]))
        assert band["total"] == total == band["mastered"] + band["attempted"] + band["not_started"]
    assert sum(b["mastered"] for b in p["by_difficulty"]) == p["summary"]["mastered"]


def test_achievements_are_real_events_only(client, db, student, exp_ids):
    assert page(client, student.headers)["achievements"] == []
    submit(client, student.headers, exp_ids["factorial"], code("factorial", "correct"))
    achievements = page(client, student.headers)["achievements"]
    kinds = {a["kind"] for a in achievements}
    assert "mastered" in kinds and any("Factorial Calculator" in a["title"] for a in achievements)
    for a in achievements:
        assert a["at"] and a["title"] and a["detail"]
        if a["experiment_id"]:
            assert db.get(Experiment, a["experiment_id"]) is not None


def test_the_pages_it_must_not_disturb_still_answer(client, student, exp_ids):
    submit(client, student.headers, exp_ids["factorial"], code("factorial", "off_by_one"))
    for path in ("/api/students/me/dashboard", "/api/skills/me", "/api/mistakes/me", "/api/recommendations/me", "/api/experiments"):
        assert client.get(path, headers=student.headers).status_code == 200, path
    old = client.get("/api/skills/me", headers=student.headers).json()
    assert "skills" in old and "practice" in old and "recent" in old      # the original endpoint is unchanged
    assert next(s for s in old["skills"] if s["skill"] == "Loops")["level"] in ("Novice", "Developing", "Proficient", "Advanced")
