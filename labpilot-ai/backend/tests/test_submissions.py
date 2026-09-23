import pytest

from tests.helpers import code, run, submit


def test_run_uses_visible_tests_only_and_is_not_graded(client, student, exp_ids):
    body = run(client, student.headers, exp_ids["factorial"], code("factorial", "correct"))
    sub = body["submission"]
    assert sub["kind"] == "run" and sub["status"] == "passed"
    assert sub["total_count"] == 3 and all(not r["is_hidden"] for r in sub["results"])
    assert body["attempt"]["status"] == "in_progress" and body["attempt"]["run_count"] == 1
    assert body["skill_changes"] == [] and body["recommendation"] is None


def test_submit_grades_all_cases_including_hidden_and_closes_the_attempt(client, student, exp_ids):
    body = submit(client, student.headers, exp_ids["factorial"], code("factorial", "correct"))
    sub = body["submission"]
    assert sub["kind"] == "submit" and sub["status"] == "passed"
    assert sub["total_count"] == 6 and sub["passed_count"] == 6 and sub["score"] == sub["max_score"] == 100
    assert body["attempt"]["status"] == "submitted" and body["attempt"]["score"] == 100
    assert {c["skill"] for c in body["skill_changes"]} == {"Python Basics", "Loops"}
    assert body["recommendation"] and body["recommendation"]["reason"]


def test_hidden_test_data_is_concealed_from_students(client, student, exp_ids):
    body = submit(client, student.headers, exp_ids["factorial"], code("factorial", "off_by_one"))
    hidden = [r for r in body["submission"]["results"] if r["is_hidden"]]
    assert hidden, "the experiment has hidden tests"
    for r in hidden:
        assert r["stdin"] is None and r["expected_output"] is None and r["actual_output"] is None and r["stderr"] is None
        assert r["passed"] in (True, False) and r["status"]
    visible = [r for r in body["submission"]["results"] if not r["is_hidden"]]
    assert all(r["expected_output"] is not None for r in visible)
    # the same holds when the submission is fetched again later
    again = client.get(f"/api/submissions/{body['submission']['id']}", headers=student.headers).json()
    assert all(r["expected_output"] is None for r in again["results"] if r["is_hidden"])


def test_partial_submission_scores_by_weight_and_records_mistakes(client, student, exp_ids):
    body = submit(client, student.headers, exp_ids["factorial"], code("factorial", "off_by_one"))
    assert body["submission"]["status"] == "partial"
    assert body["submission"]["passed_count"] == 2 and body["submission"]["score"] == pytest.approx(33.3, abs=0.1)
    assert [m["category"] for m in body["mistakes"]] == ["loop_condition"]
    assert body["mistakes"][0]["tip"] and body["mistakes"][0]["concept"]


def test_syntax_error_is_reported_per_test(client, student, exp_ids):
    body = run(client, student.headers, exp_ids["factorial"], code("factorial", "syntax"))
    assert body["submission"]["status"] == "failed"
    assert {r["status"] for r in body["submission"]["results"]} == {"syntax_error"}
    assert body["mistakes"][0]["category"] == "syntax"
    assert "SyntaxError" in body["submission"]["results"][0]["stderr"]


def test_runtime_error_and_timeout_are_reported(client, student, exp_ids):
    boom = run(client, student.headers, exp_ids["factorial"], "n = int(input())\nprint(n // 0)\n")
    assert {r["status"] for r in boom["submission"]["results"]} == {"runtime_error"}
    assert boom["submission"]["results"][0]["error_type"] == "ZeroDivisionError"
    loop = run(client, student.headers, exp_ids["factorial"], "while True:\n    pass\n")
    assert {r["status"] for r in loop["submission"]["results"]} == {"timeout"}


def test_attempt_numbers_advance_after_each_submission(client, student, exp_ids):
    first = submit(client, student.headers, exp_ids["factorial"], code("factorial", "off_by_one"))
    second = submit(client, student.headers, exp_ids["factorial"], code("factorial", "correct"))
    assert (first["attempt"]["attempt_number"], second["attempt"]["attempt_number"]) == (1, 2)
    detail = client.get(f"/api/experiments/{exp_ids['factorial']}", headers=student.headers).json()
    assert detail["progress"]["status"] == "mastered" and detail["progress"]["best_percent"] == 100
    assert detail["current_attempt"]["attempt_number"] == 3


def test_history_is_private_to_each_student(client, student, exp_ids):
    mine = submit(client, student.headers, exp_ids["factorial"], code("factorial", "correct"))["submission"]["id"]
    other = client.post("/api/auth/register", json={"email": "other-" + student.email, "password": "Password1!", "full_name": "Other Student"}).json()
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}
    assert client.get(f"/api/submissions/{mine}", headers=other_headers).status_code == 404
    assert client.get(f"/api/experiments/{exp_ids['factorial']}/submissions", headers=other_headers).json() == []
    history = client.get(f"/api/experiments/{exp_ids['factorial']}/submissions", headers=student.headers).json()
    assert [h["id"] for h in history] == [mine] and "code" not in history[0]


@pytest.mark.parametrize("payload", [{"code": ""}, {"code": "   \n"}, {"code": "x" * 50_000}, {}])
def test_invalid_code_is_rejected(client, student, exp_ids, payload):
    assert client.post(f"/api/experiments/{exp_ids['factorial']}/run", json=payload, headers=student.headers).status_code == 422


def test_code_over_the_configured_limit_is_rejected(client, student, exp_ids):
    too_long = "print(1)\n" + "#" * 21_000
    assert client.post(f"/api/experiments/{exp_ids['factorial']}/submit", json={"code": too_long}, headers=student.headers).status_code == 422


def test_malicious_code_cannot_read_files_or_import_os(client, student, exp_ids):
    for source in ("import os\nprint(os.listdir('/'))\n", "print(open('/etc/passwd').read())\n", "import subprocess\nsubprocess.run(['id'])\n"):
        body = run(client, student.headers, exp_ids["factorial"], source)
        outputs = " ".join(r["actual_output"] or "" for r in body["submission"]["results"])
        assert body["submission"]["status"] == "failed" and "root:" not in outputs and "uid=" not in outputs


def test_execution_rate_limit(client, student, exp_ids, monkeypatch):
    from app.core import limits

    monkeypatch.setattr(limits.execution_limiter, "max_events", 3)
    statuses = [client.post(f"/api/experiments/{exp_ids['factorial']}/run", json={"code": "print(1)"}, headers=student.headers).status_code for _ in range(5)]
    assert statuses == [200, 200, 200, 429, 429]


def test_submit_requires_a_student(client, teacher_headers, exp_ids):
    assert client.post(f"/api/experiments/{exp_ids['factorial']}/submit", json={"code": "print(1)"}, headers=teacher_headers).status_code == 403


def test_debugging_credit_is_awarded_after_fixing_a_failed_attempt(client, student, exp_ids):
    submit(client, student.headers, exp_ids["factorial"], code("factorial", "off_by_one"))
    body = submit(client, student.headers, exp_ids["factorial"], code("factorial", "correct"))
    assert "Debugging" in {c["skill"] for c in body["skill_changes"]}
