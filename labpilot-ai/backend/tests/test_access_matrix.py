"""Every API operation is probed as anonymous, student and teacher. Authentication and role checks must run
BEFORE anything else (for example an unknown experiment id must not reveal a 404 to an anonymous caller)."""
import re

PUBLIC = {("post", "/api/auth/login"), ("post", "/api/auth/register"), ("get", "/api/health")}
BOTH = {"/api/auth/me", "/api/users/me", "/api/users/me/password", "/api/system/status", "/api/system/taxonomy"}


def test_every_operation_enforces_authentication_and_roles(client, student, teacher_headers):
    spec = client.get("/openapi.json").json()
    problems, probed = [], 0
    for path, item in sorted(spec["paths"].items()):
        if not path.startswith("/api"):
            continue
        for method in item:
            if method not in ("get", "post", "patch", "put", "delete"):
                continue
            url = re.sub(r"\{[^}]+\}", "999999", path)
            body = {} if method in ("post", "patch", "put") else None
            hit = lambda headers: client.request(method.upper(), url, headers=headers, json=body).status_code  # noqa: E731
            if (method, path) in PUBLIC:
                if hit({}) in (401, 403):
                    problems.append((method, path, "public route rejected an anonymous caller"))
                continue
            probed += 1
            anon, stu, tea = hit({}), hit(student.headers), hit(teacher_headers)
            kind = "teacher" if path.startswith("/api/teacher") else "both" if path in BOTH else "student"
            if anon != 401:
                problems.append((method, path, f"anonymous got {anon}"))
            if kind == "teacher" and not (stu == 403 and tea not in (401, 403)):
                problems.append((method, path, f"student {stu}, teacher {tea}"))
            if kind == "student" and not (tea == 403 and stu not in (401, 403)):
                problems.append((method, path, f"student {stu}, teacher {tea}"))
            if kind == "both" and (stu in (401, 403) or tea in (401, 403)):
                problems.append((method, path, f"student {stu}, teacher {tea}"))
    assert probed >= 38
    assert problems == []
