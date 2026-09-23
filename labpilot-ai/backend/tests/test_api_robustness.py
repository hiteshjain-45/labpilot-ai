"""The API must answer sensibly when it is given nonsense, rather than failing with a server error.

Written after a real bug: an identifier larger than the database's integer column made SQLite raise while
binding the parameter, which surfaced as HTTP 500 instead of 404.
"""
import pytest

HUGE = 99999999999999999999      # beyond a 64-bit column
MISSING = 999999


@pytest.mark.parametrize("path", [
    "/api/experiments/{id}",
    "/api/submissions/{id}",
    "/api/experiments/{id}/submissions",
    "/api/experiments/{id}/whatif",
])
def test_an_out_of_range_identifier_is_not_found_rather_than_a_server_error(client, student, path):
    r = client.get(path.format(id=HUGE), headers=student.headers)
    assert r.status_code == 404, r.text
    assert "detail" in r.json()


def test_out_of_range_identifiers_on_teacher_and_write_routes(client, teacher_headers, student):
    assert client.get(f"/api/teacher/students/{HUGE}", headers=teacher_headers).status_code == 404
    assert client.get(f"/api/teacher/submissions/{HUGE}", headers=teacher_headers).status_code == 404
    assert client.delete(f"/api/teacher/experiments/{HUGE}", headers=teacher_headers).status_code == 404
    assert client.put(f"/api/teacher/submissions/{HUGE}/review", json={"status": "approved", "remark": ""}, headers=teacher_headers).status_code == 404
    assert client.post(f"/api/experiments/{HUGE}/run", json={"code": "print(1)\n"}, headers=student.headers).status_code == 404
    assert client.post("/api/viva/start", json={"experiment_id": HUGE}, headers=student.headers).status_code == 404


@pytest.mark.parametrize("value", ["abc", "1.5", "%20", "null"])
def test_a_non_numeric_identifier_is_rejected_cleanly(client, student, value):
    assert client.get(f"/api/experiments/{value}", headers=student.headers).status_code in (404, 422)


def test_missing_records_and_malformed_bodies_never_crash(client, student, teacher_headers):
    assert client.get(f"/api/experiments/{MISSING}", headers=student.headers).status_code == 404
    assert client.get(f"/api/submissions/{MISSING}", headers=student.headers).status_code == 404
    assert client.post("/api/experiments/1/submit", headers=student.headers).status_code == 422
    assert client.post("/api/experiments/1/run", json={"code": 12345}, headers=student.headers).status_code == 422
    assert client.post("/api/experiments/1/run", json={"code": "x" * 50_000}, headers=student.headers).status_code == 422
    broken = client.post("/api/auth/login", content=b"{not json", headers={"Content-Type": "application/json"})
    assert broken.status_code == 422 and "errors" in broken.json()


def test_bad_sessions_and_tokens_are_refused_not_crashed(client, student):
    assert client.get("/api/students/me/dashboard").status_code == 401
    assert client.get("/api/students/me/dashboard", headers={"Authorization": "Bearer not.a.token"}).status_code == 401
    assert client.get("/api/students/me/dashboard", headers={"Authorization": "Basic abc"}).status_code == 401
    assert client.post("/api/viva/answer", json={"session_id": "x", "answer": "y"}, headers=student.headers).status_code in (404, 422)
    assert client.get("/api/viva/summary?session_id=nope", headers=student.headers).status_code == 404
