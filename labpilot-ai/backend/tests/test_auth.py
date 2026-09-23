from datetime import datetime, timedelta, timezone

import jwt

from app.config import get_settings
from tests.conftest import PASSWORD, TEACHER_EMAIL, TEACHER_PASSWORD, _unique_email


def test_register_returns_token_and_student_profile(client):
    email = _unique_email()
    r = client.post("/api/auth/register", json={"email": email.upper(), "password": PASSWORD, "full_name": "  Asha   Rao ", "roll_number": "24CS999"})
    assert r.status_code == 201
    body = r.json()
    assert body["token_type"] == "bearer" and body["access_token"]
    assert body["user"]["email"] == email and body["user"]["role"] == "student"
    assert body["user"]["full_name"] == "Asha Rao" and body["user"]["roll_number"] == "24CS999"
    assert "password" not in str(body).lower().replace("password_hash", "")  # nothing password-like is echoed
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200 and me.json()["email"] == email


def test_register_cannot_choose_a_role(client):
    r = client.post("/api/auth/register", json={"email": _unique_email(), "password": PASSWORD, "full_name": "Sneaky User", "role": "teacher"})
    assert r.status_code == 201 and r.json()["user"]["role"] == "student"


def test_register_duplicate_email_is_rejected(client, student):
    r = client.post("/api/auth/register", json={"email": student.email, "password": PASSWORD, "full_name": "Someone Else"})
    assert r.status_code == 409


def test_register_validation_errors_are_readable(client):
    short = client.post("/api/auth/register", json={"email": _unique_email(), "password": "short", "full_name": "Test User"})
    assert short.status_code == 422 and isinstance(short.json()["detail"], str) and "password" in short.json()["detail"]
    bad_email = client.post("/api/auth/register", json={"email": "not-an-email", "password": PASSWORD, "full_name": "Test User"})
    assert bad_email.status_code == 422 and "email" in bad_email.json()["detail"].lower()


def test_login_success_for_student_and_teacher(client, student):
    s = client.post("/api/auth/login", json={"email": student.email, "password": PASSWORD})
    assert s.status_code == 200 and s.json()["user"]["role"] == "student"
    t = client.post("/api/auth/login", json={"email": TEACHER_EMAIL, "password": TEACHER_PASSWORD})
    assert t.status_code == 200 and t.json()["user"]["role"] == "teacher"


def test_login_failure_does_not_reveal_whether_the_email_exists(client, student):
    wrong_password = client.post("/api/auth/login", json={"email": student.email, "password": "Wrong-password1"})
    unknown_email = client.post("/api/auth/login", json={"email": "nobody@example.test", "password": "Wrong-password1"})
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


def test_repeated_failed_logins_are_rate_limited(client, student):
    for _ in range(get_settings().login_max_failures):
        assert client.post("/api/auth/login", json={"email": student.email, "password": "nope-nope-1"}).status_code == 401
    blocked = client.post("/api/auth/login", json={"email": student.email, "password": PASSWORD})
    assert blocked.status_code == 429  # even the correct password is refused while blocked


def test_protected_routes_require_a_valid_token(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    forged = jwt.encode({"sub": "1", "exp": datetime.now(timezone.utc) + timedelta(hours=1)}, "another-secret-key-of-32-bytes-or-more!", algorithm="HS256")
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_expired_token_is_rejected(client, student):
    expired = jwt.encode(
        {"sub": str(student.user["id"]), "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        get_settings().secret_key, algorithm="HS256",
    )
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_roles_are_separated(client, student, teacher_headers):
    assert client.get("/api/teacher/overview", headers=student.headers).status_code == 403
    assert client.get("/api/teacher/students", headers=student.headers).status_code == 403
    assert client.get("/api/students/me/dashboard", headers=teacher_headers).status_code == 403
    assert client.get("/api/experiments", headers=teacher_headers).status_code == 403


def test_teachers_create_teachers_but_students_cannot(client, student, teacher_headers):
    body = {"email": _unique_email(), "password": PASSWORD, "full_name": "New Teacher", "department": "CSE"}
    assert client.post("/api/teacher/teachers", json=body, headers=student.headers).status_code == 403
    created = client.post("/api/teacher/teachers", json=body, headers=teacher_headers)
    assert created.status_code == 201 and created.json()["role"] == "teacher"
    assert client.post("/api/auth/login", json={"email": body["email"], "password": PASSWORD}).status_code == 200


def test_change_password_and_profile(client, student):
    assert client.post("/api/users/me/password", json={"current_password": "wrong-one-1", "new_password": "Another-pass9"}, headers=student.headers).status_code == 400
    assert client.post("/api/users/me/password", json={"current_password": PASSWORD, "new_password": "Another-pass9"}, headers=student.headers).status_code == 204
    assert client.post("/api/auth/login", json={"email": student.email, "password": PASSWORD}).status_code == 401
    assert client.post("/api/auth/login", json={"email": student.email, "password": "Another-pass9"}).status_code == 200
    renamed = client.patch("/api/users/me", json={"full_name": "Renamed Person"}, headers=student.headers)
    assert renamed.status_code == 200 and renamed.json()["full_name"] == "Renamed Person"
