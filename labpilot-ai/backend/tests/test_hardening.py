"""Small regression tests from the final hardening pass."""
import pytest
from fastapi.testclient import TestClient

from app.ai.copilot import redact_hidden
from app.ai.rules import build_rule_based_guidance
from app.config import Settings, validate_settings
from app.main import create_app
from app.services.evaluation import TestOutcome


def outcome(name, stdin, expected, hidden):
    return TestOutcome(test_case_id=None, name=name, kind="normal", is_hidden=hidden, stdin=stdin, expected_output=expected, weight=1,
                       passed=False, status="wrong_answer", actual_output="", stderr="", error_type=None, runtime_ms=1, timed_out=False)


def test_redaction_hides_hidden_values_but_keeps_ordinary_words_and_case_names():
    outcomes = [
        outcome("Prime: 17", "17\n", "Prime\n", hidden=False),
        outcome("Zero is not prime", "0\n", "Not prime\n", hidden=False),
        outcome("Secret parse", "abc999\n", "0\n", hidden=True),
        outcome("Hidden big", "999983\n", "Prime\n", hidden=True),
    ]
    text = "Only edge cases fail ('Zero is not prime', 'Prime: 17'); ValueError: invalid literal: 'abc999'; saw 999983"
    result = redact_hidden(text, outcomes)
    assert "abc999" not in result and "999983" not in result and result.count("[hidden]") == 2
    assert "Zero is not prime" in result and "Prime: 17" in result and "Only edge cases fail" in result


def test_the_diagnosis_is_a_complete_sentence_before_the_next_one_is_added():
    ctx = {
        "category": "boundary", "hint_level": 1, "experiment": {"concepts": ["divisibility"], "teacher_hints": []},
        "category_detail": "Only edge cases fail ('One is not prime'); ordinary inputs pass", "student_code": "",
        "latest_run": {"failing_tests": [{"status": "wrong_answer", "expected": "Not prime", "actual": "Prime", "stdin": "1", "stderr": ""}]},
    }
    explanation = build_rule_based_guidance(ctx)["explanation"]
    assert "ordinary inputs pass. For input `1`" in explanation


def test_production_refuses_a_missing_or_weak_secret_key():
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        validate_settings(Settings(environment="production"))
    with pytest.raises(RuntimeError):
        validate_settings(Settings(environment="production", secret_key="too-short"))
    validate_settings(Settings(environment="production", secret_key="x" * 40))
    validate_settings(Settings())  # development keeps working with no configuration


def test_unexpected_errors_return_json_without_internals():
    app = create_app()

    @app.get("/api/_boom")
    def boom():
        raise RuntimeError("secret internal detail")

    response = TestClient(app, raise_server_exceptions=False).get("/api/_boom")
    assert response.status_code == 500
    assert response.json() == {"detail": "Something went wrong on the server. Please try again."}
    assert "secret" not in response.text and "Traceback" not in response.text
