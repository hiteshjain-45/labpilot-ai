from tests.helpers import code, submit


def test_overview_reports_class_wide_numbers(client, teacher_headers, student, exp_ids):
    submit(client, student.headers, exp_ids["factorial"], code("factorial", "off_by_one"))
    submit(client, student.headers, exp_ids["factorial"], code("factorial", "correct"))
    o = client.get("/api/teacher/overview", headers=teacher_headers).json()
    assert o["counts"]["students"] >= 1 and o["counts"]["published_experiments"] >= 5
    assert o["counts"]["graded_submissions"] >= 2 and o["average_percent"] is not None
    assert set(o["submission_status"]) == {"passed", "partial", "failed"}
    assert len(o["activity"]) == 14 and sum(d["submissions"] for d in o["activity"]) >= 2
    factorial = next(e for e in o["experiments"] if e["id"] == exp_ids["factorial"])
    assert factorial["students_attempted"] >= 1 and factorial["first_attempt_percent"] is not None
    assert [b["range"] for b in o["score_distribution"]] == ["0-39%", "40-59%", "60-79%", "80-100%"]


def test_common_mistakes_are_aggregate_only(client, teacher_headers, student, exp_ids):
    submit(client, student.headers, exp_ids["factorial"], code("factorial", "prompt"))
    rows = client.get("/api/teacher/mistakes", headers=teacher_headers).json()
    assert rows and all(set(r) == {"category", "label", "count", "students_affected"} for r in rows)
    overview = client.get("/api/teacher/overview", headers=teacher_headers).json()
    assert student.email not in str(overview) and student.user["full_name"] not in str(overview["common_mistakes"])


def test_roster_shows_performance_but_not_mistake_or_ai_data(client, teacher_headers, student, exp_ids):
    submit(client, student.headers, exp_ids["factorial"], code("factorial", "correct"))
    roster = client.get("/api/teacher/students", headers=teacher_headers).json()
    me = next(s for s in roster if s["email"] == student.email)
    assert me["experiments_submitted"] == 1 and me["average_percent"] == 100 and me["graded_submissions"] == 1
    assert not any(k for k in me if "mistake" in k or "hint" in k or "ai" == k)
    detail = client.get(f"/api/teacher/students/{me['id']}", headers=teacher_headers).json()
    assert not any("mistake" in k for k in detail) and detail["submissions"][0]["experiment_title"] == "Factorial Calculator"
    assert "code" not in detail["submissions"][0]
    assert client.get("/api/teacher/students/999999", headers=teacher_headers).status_code == 404


def test_teachers_can_review_submissions_including_hidden_results(client, teacher_headers, student, exp_ids):
    sub = submit(client, student.headers, exp_ids["factorial"], code("factorial", "off_by_one"))["submission"]
    detail = client.get(f"/api/teacher/submissions/{sub['id']}", headers=teacher_headers).json()
    assert detail["code"] == code("factorial", "off_by_one") and detail["student_name"] == "Test Student"
    hidden = [r for r in detail["results"] if r["is_hidden"]]
    assert hidden and all(r["expected_output"] is not None and r["stdin"] is not None for r in hidden)
    assert detail["attempt"]["attempt_number"] == 1


def test_submission_listing_filters(client, teacher_headers, student, exp_ids):
    submit(client, student.headers, exp_ids["factorial"], code("factorial", "off_by_one"))
    submit(client, student.headers, exp_ids["factorial"], code("factorial", "correct"))
    user_id = client.get("/api/teacher/students", headers=teacher_headers).json()
    student_id = next(s["id"] for s in user_id if s["email"] == student.email)
    base = f"/api/teacher/submissions?student_id={student_id}"
    everything = client.get(base, headers=teacher_headers).json()
    assert everything["total"] == 2 and [i["status"] for i in everything["items"]] == ["passed", "partial"]
    partial = client.get(base + "&status=partial", headers=teacher_headers).json()
    assert partial["total"] == 1 and partial["items"][0]["student_name"] == "Test Student"
    assert client.get(base + "&status=bogus", headers=teacher_headers).status_code == 422
    assert client.get("/api/teacher/submissions/999999", headers=teacher_headers).status_code == 404


def test_system_status_is_honest_about_the_ai_mode(client, student):
    body = client.get("/api/system/status", headers=student.headers).json()
    assert body["ai"]["provider"] == "mock" and body["ai"]["is_real"] is False
    assert body["sandbox"]["mode"] == "subprocess"
    assert client.get("/api/health").json()["status"] == "ok"


def test_taxonomy_endpoint_matches_the_backend_constants(client, teacher_headers):
    from app.core.constants import CATEGORIES, SKILLS

    body = client.get("/api/system/taxonomy", headers=teacher_headers).json()
    assert body["skills"] == list(SKILLS) and [c["key"] for c in body["categories"]] == list(CATEGORIES)
    assert body["difficulties"] == ["beginner", "intermediate", "advanced"]
    assert client.get("/api/system/taxonomy").status_code == 401


# ---------------------------------------------------------------- teacher review of a submission (the feedback loop)
def test_a_teacher_can_review_a_graded_submission_and_the_student_sees_it(client, student, teacher_headers, exp_ids):
    from tests.helpers import code, submit

    graded = submit(client, student.headers, exp_ids["factorial"], code("factorial", "off_by_one"))
    sub_id = graded["submission"]["id"]
    assert client.get(f"/api/submissions/{sub_id}", headers=student.headers).json()["review"] is None

    saved = client.put(
        f"/api/teacher/submissions/{sub_id}/review",
        json={"status": "needs_rework", "remark": "Check the loop bound, then resubmit."}, headers=teacher_headers,
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["status"] == "needs_rework" and body["label"] == "Needs rework" and body["teacher_name"]

    seen = client.get(f"/api/submissions/{sub_id}", headers=student.headers).json()
    assert seen["review"]["remark"] == "Check the loop bound, then resubmit."
    assert seen["review"]["label"] == "Needs rework" and seen["score"] == graded["submission"]["score"]

    history = client.get(f"/api/experiments/{exp_ids['factorial']}/submissions", headers=student.headers).json()
    assert next(h for h in history if h["id"] == sub_id)["review"]["status"] == "needs_rework"


def test_reviewing_never_changes_the_score_or_the_learning_data(client, db, student, teacher_headers, exp_ids):
    from tests.helpers import code, submit

    graded = submit(client, student.headers, exp_ids["factorial"], code("factorial", "off_by_one"))
    before = client.get("/api/students/me/dashboard", headers=student.headers).json()
    client.put(f"/api/teacher/submissions/{graded['submission']['id']}/review", json={"status": "approved", "remark": "Good"}, headers=teacher_headers)
    after = client.get("/api/students/me/dashboard", headers=student.headers).json()
    assert after["stats"] == before["stats"] and after["mistakes"]["total"] == before["mistakes"]["total"]
    assert after["passport"]["overall"] == before["passport"]["overall"]


def test_a_review_is_updated_in_place_and_can_be_removed(client, db, student, teacher_headers, exp_ids):
    from sqlalchemy import func, select

    from app.models import SubmissionReview
    from tests.helpers import code, submit

    sub_id = submit(client, student.headers, exp_ids["factorial"], code("factorial", "correct"))["submission"]["id"]
    for status, remark in (("needs_rework", "Fix the bound"), ("approved", "Fixed, well done")):
        client.put(f"/api/teacher/submissions/{sub_id}/review", json={"status": status, "remark": remark}, headers=teacher_headers)
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(SubmissionReview).where(SubmissionReview.submission_id == sub_id)) == 1
    assert client.get(f"/api/submissions/{sub_id}", headers=student.headers).json()["review"]["remark"] == "Fixed, well done"

    assert client.delete(f"/api/teacher/submissions/{sub_id}/review", headers=teacher_headers).status_code == 204
    assert client.get(f"/api/submissions/{sub_id}", headers=student.headers).json()["review"] is None
    assert client.delete(f"/api/teacher/submissions/{sub_id}/review", headers=teacher_headers).status_code == 404


def test_only_a_teacher_may_review_and_only_graded_work(client, student, teacher_headers, exp_ids):
    from tests.helpers import code, run, submit

    ran = run(client, student.headers, exp_ids["factorial"], code("factorial", "correct"))["submission"]["id"]
    graded = submit(client, student.headers, exp_ids["factorial"], code("factorial", "correct"))["submission"]["id"]
    body = {"status": "approved", "remark": "ok"}
    assert client.put(f"/api/teacher/submissions/{graded}/review", json=body).status_code == 401
    assert client.put(f"/api/teacher/submissions/{graded}/review", json=body, headers=student.headers).status_code == 403
    assert client.put(f"/api/teacher/submissions/{ran}/review", json=body, headers=teacher_headers).status_code == 422
    assert client.put("/api/teacher/submissions/99999/review", json=body, headers=teacher_headers).status_code == 404
    assert client.put(f"/api/teacher/submissions/{graded}/review", json={"status": "nonsense"}, headers=teacher_headers).status_code == 422
