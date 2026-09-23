"""Checks a new developer depends on: the demo data builds from an empty database, and basic release hygiene."""
import json
import os
import sqlite3
import subprocess
import sys
import textwrap
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
DEMO_ACCOUNTS = [("teacher@labpilot.demo", "Teacher@123", "teacher")] + [
    (f"{name}@labpilot.demo", "Student@123", "student") for name in ("student", "rohan", "priya", "karan", "sneha")
]
TABLES = ["users", "students", "experiments", "experiment_test_cases", "attempts", "submissions", "execution_results",
          "mistake_records", "skill_records", "skill_evidence", "experiment_recommendations", "what_if_predictions", "ai_interactions"]

LOGIN_CHECK = textwrap.dedent('''
    import json, sys
    from fastapi.testclient import TestClient
    from app.main import app
    accounts = json.loads(sys.argv[1])
    with TestClient(app) as client:
        out = {}
        for email, password, role in accounts:
            r = client.post("/api/auth/login", json={"email": email, "password": password})
            body = r.json()
            out[email] = [r.status_code, body.get("user", {}).get("role")]
            if role == "student":
                d = client.get("/api/students/me/dashboard", headers={"Authorization": "Bearer " + body["access_token"]}).json()
                out[email].append([d["stats"]["submissions"], d["mistakes"]["total"], d["recommendation"] is not None])
            else:
                o = client.get("/api/teacher/overview", headers={"Authorization": "Bearer " + body["access_token"]}).json()
                out[email].append([o["counts"]["students"], len(o["experiments"]), len(o["skill_distribution"])])
    print(json.dumps(out))
''')


def _env(db_file, **extra):
    env = {k: v for k, v in os.environ.items() if k not in ("APP_ENV", "DATABASE_URL")}
    env.update(DATABASE_URL=f"sqlite:///{db_file}", AI_PROVIDER="mock", SECRET_KEY="test-secret-key-that-is-comfortably-long-enough", **extra)
    return env


def _run(args, env, **kw):
    return subprocess.run([sys.executable, *args], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=300, **kw)


def test_the_full_demo_builds_from_an_empty_database_and_every_documented_account_works(tmp_path):
    db_file = tmp_path / "fresh.db"
    env = _env(db_file)
    seeded = _run(["-m", "app.seed", "--reset"], env)
    assert seeded.returncode == 0, seeded.stderr
    assert "Seeded 5 experiments and 5 demo students" in seeded.stdout
    for email, password, _ in DEMO_ACCOUNTS:
        assert email in seeded.stdout and password in seeded.stdout  # the credentials printed are the ones in the docs

    with sqlite3.connect(db_file) as conn:
        counts = {t: conn.execute(f"select count(*) from {t}").fetchone()[0] for t in TABLES}
    assert counts["users"] == 6 and counts["students"] == 5 and counts["experiments"] == 5
    assert counts["experiment_test_cases"] >= 25 and counts["submissions"] >= 25
    for learning_table in ("mistake_records", "skill_records", "skill_evidence", "experiment_recommendations", "what_if_predictions"):
        assert counts[learning_table] > 0, f"the demo has no {learning_table}"

    checked = _run(["-c", LOGIN_CHECK, json.dumps(DEMO_ACCOUNTS)], env)
    assert checked.returncode == 0, checked.stderr
    result = json.loads(checked.stdout.strip().splitlines()[-1])
    for email, password, role in DEMO_ACCOUNTS:
        status, actual_role, summary = result[email]
        assert (status, actual_role) == (200, role), email
    ananya = result["student@labpilot.demo"][2]
    assert ananya[0] >= 5 and ananya[1] >= 5 and ananya[2] is True  # graded work, mistake patterns and a recommendation to show
    assert result["teacher@labpilot.demo"][2] == [5, 5, 7]

    again = _run(["-m", "app.seed"], env)  # a second run must not duplicate or damage anything
    assert again.returncode == 0 and "nothing was changed" in again.stdout


def test_demo_accounts_cannot_be_created_in_a_production_environment(tmp_path):
    env = _env(tmp_path / "prod.db", APP_ENV="production")
    env["SECRET_KEY"] = "x" * 48
    refused = _run(["-m", "app.seed"], env)
    assert refused.returncode == 2 and "Refusing to create demo accounts" in refused.stdout
    assert not (tmp_path / "prod.db").exists() or sqlite3.connect(tmp_path / "prod.db").execute("select count(*) from sqlite_master").fetchone()[0] == 0


def test_responses_carry_basic_security_headers_and_api_data_is_not_cached(client):
    api = client.get("/api/health")
    assert api.headers["x-content-type-options"] == "nosniff" and api.headers["x-frame-options"] == "DENY"
    assert api.headers["referrer-policy"] == "same-origin" and api.headers["cache-control"] == "no-store"


def test_no_secrets_or_real_keys_ship_in_the_configuration_examples():
    example = (BACKEND / ".env.example").read_text()
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        assert f"{key}=\n" in example, f"{key} must be empty in .env.example"
    assert "SECRET_KEY=dev-insecure-secret-change-me-before-deploying" in example
