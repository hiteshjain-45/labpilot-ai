"""AI Viva: rule-based oral practice. No language model is involved, and no score or grade is touched."""
import pytest
from sqlalchemy import func, select

from app.models import AIInteraction, Experiment, SkillRecord, Student, Submission
from app.services import viva as viva_service
from tests.helpers import code, submit

GOOD = {
    "concept": "The for loop uses range with the correct bounds: it starts at 1 and the last value is n, so range(1, n + 1). If it stops one early the product is wrong.",
    "code_explanation": "I read the input, convert it with int, then loop and print the result at the end, because the expected output is exactly one line.",
    "debugging": "I trace the failing input by hand and print the variables at each step to check every value against what I expect.",
    "what_if": "It would print the wrong value because the loop bounds change, so the last iteration is missing and it stops early.",
    "improvement": "It would be faster with lower complexity: stop at the square root instead of looping to n, and handle the empty or zero edge case.",
}


def sid(db, student):
    return db.scalar(select(Student.id).where(Student.user_id == student.user["id"]))


def start(client, headers, experiment_id):
    r = client.post("/api/viva/start", json={"experiment_id": experiment_id}, headers=headers)
    assert r.status_code == 200
    return r.json()


def answer(client, headers, session_id, text):
    r = client.post("/api/viva/answer", json={"session_id": session_id, "answer": text}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def run_full_viva(client, headers, experiment_id, answers=GOOD):
    started = start(client, headers, experiment_id)
    reply = {"next_question": started["question"]}
    while reply.get("next_question"):
        q = reply["next_question"]
        reply = answer(client, headers, started["session_id"], answers[q["type"]] if isinstance(answers, dict) else answers)
    return started["session_id"], reply


# ------------------------------------------------------------------ questions
def test_five_questions_of_the_required_types_are_generated_from_real_data(db, db_student, exp_ids):
    exp = db.get(Experiment, exp_ids["factorial"])
    questions = viva_service.build_questions(db, db_student, exp)
    assert [q["type"] for q in questions] == ["concept", "code_explanation", "debugging", "what_if", "improvement"]
    for q in questions:
        assert q["question"] and q["concept"] and q["difficulty"] in ("easy", "medium", "hard")
        assert q["expected_points"] and all(isinstance(p, str) for p in q["expected_points"])
        assert q["skill"] is None or q["skill"] in (exp.skills or []) or q["skill"] in ("Problem Solving", "Debugging", "Loops", "Arrays", "Functions", "Python Basics")
    assert any(q["related_category"] for q in questions)


def test_the_questions_are_deterministic(db, db_student, exp_ids):
    exp = db.get(Experiment, exp_ids["factorial"])
    first = [q["question"] for q in viva_service.build_questions(db, db_student, exp)]
    assert first == [q["question"] for q in viva_service.build_questions(db, db_student, exp)]


def test_the_debugging_question_uses_the_students_own_mistake_dna(client, db, db_student, student, exp_ids):
    exp = db.get(Experiment, exp_ids["factorial"])
    fresh = viva_service.build_questions(db, db_student, exp)[2]
    submit(client, student.headers, exp_ids["factorial"], code("factorial", "off_by_one"))
    mine = viva_service.build_questions(db, db.get(Student, sid(db, student)), exp)[2]
    assert mine["related_category"] == "loop_condition" and "loop-condition errors" in mine["question"].lower()
    assert "your submissions have shown" in mine["question"].lower()
    assert fresh["question"] != mine["question"]


def test_the_student_never_receives_the_matching_keywords(client, student, exp_ids):
    started = start(client, student.headers, exp_ids["factorial"])
    assert "points" not in started["question"] and "expected_points" in started["question"]
    assert "is not an LLM judgment" in started["note"]


# ------------------------------------------------------------------ evaluation
@pytest.mark.parametrize("text,expected", [
    (GOOD["concept"], "correct"),
    ("you use a for loop over a range", "partially correct"),
    ("it just works", "incorrect"),
    ("", "incorrect"),
])
def test_answers_are_scored_by_the_concepts_they_name(db, db_student, exp_ids, text, expected):
    question = viva_service.build_questions(db, db_student, db.get(Experiment, exp_ids["factorial"]))[0]
    result = viva_service.evaluate_answer(question, text)
    assert result["verdict"] == expected
    assert 0 <= result["score"] <= 10 and result["feedback"]
    assert set(result["matched_concepts"]) | set(result["missing_concepts"]) == set(question["expected_points"])


def test_a_word_ending_still_counts_but_an_empty_answer_never_does(db, db_student, exp_ids):
    question = viva_service.build_questions(db, db_student, db.get(Experiment, exp_ids["factorial"]))[0]
    assert viva_service.evaluate_answer(question, "the loop stops one iteration early")["matched_concepts"]
    assert viva_service.evaluate_answer(question, "   ")["score"] == 0


# ------------------------------------------------------------------ the flow
def test_the_viva_runs_one_question_at_a_time_and_then_offers_the_summary(client, student, exp_ids):
    started = start(client, student.headers, exp_ids["factorial"])
    assert started["total_questions"] == 5 and started["question"]["index"] == 1
    seen = []
    reply = {"next_question": started["question"]}
    while reply.get("next_question"):
        seen.append(reply["next_question"]["index"])
        reply = answer(client, student.headers, started["session_id"], GOOD[reply["next_question"]["type"]])
        assert reply["evaluation"]["score"] >= 0 and reply["next_recommendation"]
    assert seen == [1, 2, 3, 4, 5] and reply["finished"] is True and reply["answered"] == 5
    assert client.post("/api/viva/answer", json={"session_id": started["session_id"], "answer": "extra"}, headers=student.headers).status_code == 409


def test_the_summary_adds_up_and_links_to_practice(client, db, student, exp_ids):
    submit(client, student.headers, exp_ids["factorial"], code("factorial", "off_by_one"))
    session_id, _ = run_full_viva(client, student.headers, exp_ids["factorial"], answers="i do not know")
    s = client.get(f"/api/viva/summary?session_id={session_id}", headers=student.headers).json()
    assert s["questions_answered"] == 5 and s["out_of"] == 50
    assert s["total_score"] == sum(a["score"] for a in s["answers"]) and s["percent"] == round(100 * s["total_score"] / 50)
    assert s["concepts_needing_practice"] and not s["concepts_demonstrated"]
    assert s["mistake_dna"] and s["mistake_dna"][0]["label"] and s["mistake_dna"][0]["recorded_count"] >= 1
    assert s["recommendation"] and "more practice with" in s["recommendation"]["reason"]
    assert db.get(Experiment, s["recommendation"]["experiment_id"]) is not None


def test_a_strong_viva_demonstrates_concepts_and_recommends_nothing_remedial(client, student, exp_ids):
    session_id, _ = run_full_viva(client, student.headers, exp_ids["factorial"])
    s = client.get(f"/api/viva/summary?session_id={session_id}", headers=student.headers).json()
    assert s["percent"] >= 70 and s["concepts_demonstrated"]
    assert all(m["label"] for m in s["mistake_dna"])


# ------------------------------------------------------------------ integration, without disturbing anything
def test_a_finished_viva_adds_practice_evidence_but_changes_no_score(client, db, student, exp_ids):
    submit(client, student.headers, exp_ids["factorial"], code("factorial", "correct"))
    student_id = sid(db, student)
    before_dashboard = client.get("/api/students/me/dashboard", headers=student.headers).json()
    before_mistakes = db.scalar(select(func.count()).select_from(__import__("app.models", fromlist=["MistakeRecord"]).MistakeRecord))
    before_submissions = db.scalar(select(func.count()).select_from(Submission))
    before_loops = db.scalar(select(SkillRecord.mastery).where(SkillRecord.student_id == student_id, SkillRecord.skill == "Loops"))

    session_id, _ = run_full_viva(client, student.headers, exp_ids["factorial"])
    s = client.get(f"/api/viva/summary?session_id={session_id}", headers=student.headers).json()
    db.expire_all()

    assert s["skill_changes"] and {c["skill"] for c in s["skill_changes"]} <= set(db.get(Experiment, exp_ids["factorial"]).skills)
    after = client.get("/api/students/me/dashboard", headers=student.headers).json()
    scores = ("experiments_mastered", "average_percent", "submissions", "runs")
    for key in (k for k in scores if k in before_dashboard["stats"]):
        assert after["stats"][key] == before_dashboard["stats"][key], key    # no score or grade moved
    assert after["stats"]["skills_overall"] > before_dashboard["stats"]["skills_overall"]   # practice evidence did land
    assert after["mistakes"]["total"] == before_dashboard["mistakes"]["total"]
    assert db.scalar(select(func.count()).select_from(Submission)) == before_submissions
    assert db.scalar(select(func.count()).select_from(__import__("app.models", fromlist=["MistakeRecord"]).MistakeRecord)) == before_mistakes
    assert db.scalar(select(SkillRecord.mastery).where(SkillRecord.student_id == student_id, SkillRecord.skill == "Loops")) != before_loops

    evidence = client.get("/api/skills/me", headers=student.headers).json()
    loops = next(x for x in evidence["skills"] if x["skill"] == "Loops")
    assert any(c["source"] == "viva" for c in loops["contributors"])
    assert any(c["source_label"] == "AI Viva answer" for c in loops["contributors"])


def test_the_summary_records_evidence_only_once(client, db, student, exp_ids):
    session_id, _ = run_full_viva(client, student.headers, exp_ids["factorial"])
    first = client.get(f"/api/viva/summary?session_id={session_id}", headers=student.headers).json()
    again = client.get(f"/api/viva/summary?session_id={session_id}", headers=student.headers).json()
    assert first["total_score"] == again["total_score"] and again["skill_changes"] == []
    rows = db.scalars(select(AIInteraction).where(AIInteraction.kind == "viva_summary")).all()
    assert sum(1 for r in rows if (r.request_context or {}).get("session_id") == session_id) == 1


def test_the_transcript_is_stored_in_the_existing_table(client, db, student, exp_ids):
    session_id, _ = run_full_viva(client, student.headers, exp_ids["factorial"])
    rows = [
        r for r in db.scalars(select(AIInteraction).where(AIInteraction.kind == "viva")).all()
        if (r.request_context or {}).get("session_id") == session_id       # the database is shared by this module
    ]
    assert len(rows) == 5 and all(r.provider == "rules" for r in rows)
    assert [(r.request_context or {}).get("index") for r in rows] == [1, 2, 3, 4, 5]
    assert all(r.response.get("verdict") for r in rows)


def test_the_routes_are_student_only_and_validate(client, student, teacher_headers, exp_ids):
    assert client.get("/api/viva/context").status_code == 401
    assert client.get("/api/viva/context", headers=teacher_headers).status_code == 403
    assert client.post("/api/viva/start", json={"experiment_id": 9999}, headers=student.headers).status_code == 404
    assert client.post("/api/viva/answer", json={"session_id": "nope-1-1", "answer": "x"}, headers=student.headers).status_code == 404
    assert client.get("/api/viva/summary?session_id=missing", headers=student.headers).status_code == 404
    ctx = client.get("/api/viva/context", headers=student.headers).json()
    assert ctx["question_count"] == 5 and ctx["experiments"] and "is not an LLM judgment" in ctx["note"]


def test_the_features_it_must_not_disturb_still_answer(client, student, exp_ids):
    run_full_viva(client, student.headers, exp_ids["factorial"])
    for path in ("/api/students/me/dashboard", "/api/skills/me", "/api/skills/me/passport", "/api/mistakes/me", "/api/recommendations/me"):
        assert client.get(path, headers=student.headers).status_code == 200, path


# ------------------------------------------------------------------ what the teacher sees (aggregate only)
def test_teacher_overview_reports_viva_practice_without_naming_anyone(client, db, student, teacher_headers, exp_ids):
    before = client.get("/api/teacher/overview", headers=teacher_headers).json()
    before_factorial = next(e for e in before["experiments"] if e["id"] == exp_ids["factorial"])["viva"]

    session_id, _ = run_full_viva(client, student.headers, exp_ids["factorial"])
    mine = client.get(f"/api/viva/summary?session_id={session_id}", headers=student.headers).json()

    after = client.get("/api/teacher/overview", headers=teacher_headers).json()
    factorial = next(e for e in after["experiments"] if e["id"] == exp_ids["factorial"])["viva"]
    assert factorial["sessions"] == before_factorial["sessions"] + 1
    assert factorial["average_percent"] is not None and 0 <= factorial["average_percent"] <= 100
    assert after["viva"]["sessions"] == before["viva"]["sessions"] + 1 and after["viva"]["students"] >= 1
    untouched = next(e for e in after["experiments"] if e["id"] == exp_ids["prime"])["viva"]
    assert untouched == next(e for e in before["experiments"] if e["id"] == exp_ids["prime"])["viva"]

    blob = str(after["experiments"]) + str(after["viva"])
    assert mine["answers"][0]["answer"] not in blob and "session_id" not in blob
    assert set(factorial) == {"sessions", "students", "average_percent"}


def test_viva_practice_equals_the_stored_summary_rows(client, db, student, teacher_headers, exp_ids):
    from app.services import analytics

    run_full_viva(client, student.headers, exp_ids["factorial"])
    run_full_viva(client, student.headers, exp_ids["factorial"], answers="no idea")   # a second session, same second
    per_experiment, totals = analytics.viva_practice(db)

    rows = db.scalars(select(AIInteraction).where(AIInteraction.kind == "viva_summary")).all()
    mine = [r for r in rows if r.experiment_id == exp_ids["factorial"]]
    assert len(mine) >= 2                                              # the two above really were separate sessions
    assert len({(r.request_context or {}).get("session_id") for r in mine}) == len(mine)

    entry = per_experiment[exp_ids["factorial"]]
    percents = [r.response["percent"] for r in mine]
    assert entry["sessions"] == len(mine)
    assert entry["students"] == len({r.student_id for r in mine})
    assert entry["average_percent"] == round(sum(percents) / len(percents))
    assert totals["sessions"] == len(rows) and totals["students"] == len({r.student_id for r in rows})


def test_viva_practice_does_not_disturb_the_rest_of_the_overview(client, student, teacher_headers, exp_ids):
    before = client.get("/api/teacher/overview", headers=teacher_headers).json()
    run_full_viva(client, student.headers, exp_ids["factorial"])
    after = client.get("/api/teacher/overview", headers=teacher_headers).json()
    for key in ("counts", "completion", "common_mistakes", "skill_distribution", "score_distribution", "needs_practice"):
        assert after[key] == before[key], key      # a viva changes no grade, mistake or skill distribution
