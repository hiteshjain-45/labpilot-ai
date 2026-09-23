"""Test configuration. The environment is set BEFORE the app is imported so that every test runs
against a throw-away SQLite file, the rule-based AI provider and a known secret."""
import os
import tempfile
import uuid

_TMP = tempfile.mkdtemp(prefix="labpilot-tests-")
os.environ.update(
    DATABASE_URL=f"sqlite:///{_TMP}/test.db",
    AI_PROVIDER="mock",
    ANTHROPIC_API_KEY="",
    OPENAI_API_KEY="",
    SECRET_KEY="test-secret-key-that-is-comfortably-long-enough",
    SANDBOX_MODE="subprocess",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core import limits  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Experiment  # noqa: E402
from app.seed import seed_all  # noqa: E402
from app.services import accounts  # noqa: E402

PASSWORD = "Password1!"
TEACHER_EMAIL, TEACHER_PASSWORD = "teacher@labpilot.demo", "Teacher@123"


@pytest.fixture(scope="session", autouse=True)
def _database():
    init_db()
    with SessionLocal() as db:
        assert seed_all(db, minimal=True)["seeded"]
    yield


@pytest.fixture(scope="session")
def client(_database):
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    limits.reset_all()
    yield
    limits.reset_all()


@pytest.fixture()
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture(scope="session")
def teacher_headers(client):
    r = client.post("/api/auth/login", json={"email": TEACHER_EMAIL, "password": TEACHER_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def exp_ids(_database):
    """Experiment ids keyed like the seed: factorial, liststats, debug, prime, sort."""
    keys = ["factorial", "liststats", "debug", "prime", "sort"]
    with SessionLocal() as db:
        rows = db.query(Experiment).order_by(Experiment.position).all()
    return {k: e.id for k, e in zip(keys, rows)}


def _unique_email() -> str:
    return f"user-{uuid.uuid4().hex[:10]}@example.test"


@pytest.fixture()
def student(client):
    """A freshly registered student: object with .headers, .email, .id (user id)."""
    email = _unique_email()
    r = client.post("/api/auth/register", json={"email": email, "password": PASSWORD, "full_name": "Test Student", "roll_number": "T-001"})
    assert r.status_code == 201, r.text
    body = r.json()

    class S:
        headers = {"Authorization": f"Bearer {body['access_token']}"}
        user = body["user"]
    S.email = email
    return S


@pytest.fixture()
def db_student(db):
    """A student created directly in the database, for service-level tests."""
    s = accounts.create_student(db, _unique_email(), PASSWORD, "Service Student")
    db.commit()
    return s
