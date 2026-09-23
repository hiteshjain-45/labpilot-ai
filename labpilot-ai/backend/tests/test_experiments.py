from app.seed.catalogue import PRIME
from tests.helpers import code


def test_students_see_all_published_experiments_in_order(client, student):
    r = client.get("/api/experiments", headers=student.headers)
    assert r.status_code == 200
    items = r.json()
    assert [e["difficulty"] for e in items] == ["beginner", "beginner", "intermediate", "intermediate", "advanced"]
    assert all(e["progress"]["status"] == "not_started" for e in items)
    assert all(e["test_count"] >= 6 for e in items)


def test_student_detail_never_exposes_secrets(client, student, exp_ids):
    r = client.get(f"/api/experiments/{exp_ids['prime']}", headers=student.headers)
    assert r.status_code == 200
    body = r.json()
    assert "reference_solution" not in body and "hints" not in body
    assert body["hidden_test_count"] == sum(1 for t in PRIME["test_cases"] if t["is_hidden"])
    assert len(body["visible_tests"]) == sum(1 for t in PRIME["test_cases"] if not t["is_hidden"])
    text = r.text
    assert PRIME["reference_solution"].strip().splitlines()[1] not in text  # a line of the solution
    assert "999999937" not in text  # the hidden performance case
    assert body["starter_code"] and body["current_attempt"]["attempt_number"] == 1


def test_unknown_experiment_is_404(client, student):
    assert client.get("/api/experiments/999999", headers=student.headers).status_code == 404


def test_experiments_require_login(client):
    assert client.get("/api/experiments").status_code == 401


def test_student_detail_returns_last_code_after_a_run(client, student, exp_ids):
    source = code("factorial", "correct") + "# my edit\n"
    client.post(f"/api/experiments/{exp_ids['factorial']}/run", json={"code": source}, headers=student.headers)
    body = client.get(f"/api/experiments/{exp_ids['factorial']}", headers=student.headers).json()
    assert body["last_code"] == source and body["progress"]["status"] == "in_progress"


# ---------------------------------------------------------------- teacher management
def _draft(**extra):
    base = {
        "title": "Sum of Two Numbers", "difficulty": "beginner", "skills": ["Python Basics"],
        "problem_statement": "Read two integers and print their sum.", "starter_code": "a = int(input())\n",
        "reference_solution": "a = int(input())\nb = int(input())\nprint(a + b)\n", "is_published": False,
    }
    base.update(extra)
    return base


def test_teacher_creates_publishes_and_deletes_an_experiment(client, teacher_headers, student):
    created = client.post("/api/teacher/experiments", json=_draft(), headers=teacher_headers)
    assert created.status_code == 201
    exp = created.json()
    exp_id = exp["id"]
    assert exp["slug"] == "sum-of-two-numbers" and exp["is_published"] is False

    # drafts are invisible to students
    assert client.get(f"/api/experiments/{exp_id}", headers=student.headers).status_code == 404
    # cannot publish without a test case
    assert client.patch(f"/api/teacher/experiments/{exp_id}", json={"is_published": True}, headers=teacher_headers).status_code == 422

    tc = client.post(f"/api/teacher/experiments/{exp_id}/test-cases", json={"name": "basic", "stdin": "2\n3\n", "expected_output": "5\n"}, headers=teacher_headers)
    assert tc.status_code == 201
    hidden = client.post(f"/api/teacher/experiments/{exp_id}/test-cases", json={"name": "negatives", "stdin": "-2\n-3\n", "expected_output": "-5\n", "is_hidden": True, "kind": "edge"}, headers=teacher_headers)
    assert hidden.status_code == 201

    check = client.post(f"/api/teacher/experiments/{exp_id}/validate", headers=teacher_headers).json()
    assert check["all_passed"] is True and len(check["results"]) == 2

    assert client.patch(f"/api/teacher/experiments/{exp_id}", json={"is_published": True, "title": "Adding Two Numbers"}, headers=teacher_headers).json()["slug"] == "adding-two-numbers"
    visible = client.get(f"/api/experiments/{exp_id}", headers=student.headers).json()
    assert visible["hidden_test_count"] == 1 and [t["name"] for t in visible["visible_tests"]] == ["basic"]

    assert client.delete(f"/api/teacher/experiments/{exp_id}", headers=teacher_headers).status_code == 204
    assert client.get(f"/api/experiments/{exp_id}", headers=student.headers).status_code == 404


def test_publishing_a_new_experiment_needs_test_cases(client, teacher_headers):
    r = client.post("/api/teacher/experiments", json=_draft(is_published=True), headers=teacher_headers)
    assert r.status_code == 422


def test_reference_validation_catches_a_wrong_expected_output(client, teacher_headers):
    body = _draft(test_cases=[{"name": "wrong", "stdin": "2\n3\n", "expected_output": "6\n"}])
    exp_id = client.post("/api/teacher/experiments", json=body, headers=teacher_headers).json()["id"]
    result = client.post(f"/api/teacher/experiments/{exp_id}/validate", headers=teacher_headers).json()
    assert result["all_passed"] is False and result["results"][0]["actual_output"].strip() == "5"
    client.delete(f"/api/teacher/experiments/{exp_id}", headers=teacher_headers)


def test_reference_validation_needs_a_solution(client, teacher_headers):
    body = _draft(reference_solution="", test_cases=[{"name": "t", "stdin": "1\n1\n", "expected_output": "2\n"}])
    exp_id = client.post("/api/teacher/experiments", json=body, headers=teacher_headers).json()["id"]
    assert client.post(f"/api/teacher/experiments/{exp_id}/validate", headers=teacher_headers).status_code == 400
    client.delete(f"/api/teacher/experiments/{exp_id}", headers=teacher_headers)


def test_test_case_edit_and_last_case_protection(client, teacher_headers):
    body = _draft(is_published=True, test_cases=[{"name": "only", "stdin": "1\n2\n", "expected_output": "3\n"}])
    exp = client.post("/api/teacher/experiments", json=body, headers=teacher_headers).json()
    exp_id, test_id = exp["id"], exp["test_cases"][0]["id"]
    edited = client.patch(f"/api/teacher/experiments/{exp_id}/test-cases/{test_id}", json={"expected_output": "3", "weight": 3}, headers=teacher_headers)
    assert edited.status_code == 200 and edited.json()["weight"] == 3
    assert client.delete(f"/api/teacher/experiments/{exp_id}/test-cases/{test_id}", headers=teacher_headers).status_code == 400
    assert client.patch(f"/api/teacher/experiments/{exp_id}/test-cases/999999", json={"weight": 2}, headers=teacher_headers).status_code == 404
    client.delete(f"/api/teacher/experiments/{exp_id}", headers=teacher_headers)


def test_experiment_validation_rejects_bad_taxonomy(client, teacher_headers):
    for bad in ({"difficulty": "impossible"}, {"skills": ["Telepathy"]}, {"focus_categories": ["nonsense"]}, {"title": "ab"}):
        assert client.post("/api/teacher/experiments", json=_draft(**bad), headers=teacher_headers).status_code == 422


def test_teacher_list_includes_drafts_and_stats(client, teacher_headers):
    items = client.get("/api/teacher/experiments", headers=teacher_headers).json()
    assert len(items) >= 5 and {"test_count", "hidden_test_count", "students_attempted", "pass_rate"} <= set(items[0])
