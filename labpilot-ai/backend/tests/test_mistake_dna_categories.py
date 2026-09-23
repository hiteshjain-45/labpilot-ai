"""The mistake categories added for Mistake DNA: off-by-one, variable initialisation and function logic.

Classification stays deterministic: static analysis plus the test outcomes, no AI. These tests also guard the
invariant that every category has the wording the Copilot and the dashboard need.
"""
import pytest

from app.ai.rules import EXPLAIN, HINTS, NEXT_STEP
from app.core.constants import CATEGORIES, CATEGORY_PRIORITY, practice_tags
from app.models import Experiment
from app.services import mistakes as m
from app.services.evaluation import TestOutcome
from tests.helpers import code, submit


def outcome(name="case 1", status="wrong_answer", kind="normal", **kw):
    base = dict(
        test_case_id=1, name=name, kind=kind, is_hidden=False, stdin="", expected_output="", weight=1,
        passed=False, status=status, actual_output="", stderr="", error_type=None, runtime_ms=5, timed_out=False,
    )
    return TestOutcome(**{**base, **kw})


def categories(code_text, outcomes=None):
    return {x.category for x in m.classify_outcomes(code_text, outcomes or [outcome()])}


# ------------------------------------------------------------------ every category is complete
def test_every_category_has_the_wording_the_dashboard_and_copilot_need():
    assert set(CATEGORY_PRIORITY) == set(CATEGORIES)
    for name, meta in CATEGORIES.items():
        assert meta["label"] and meta["concept"] and meta["tip"], name
        assert name in EXPLAIN and name in NEXT_STEP and len(HINTS[name]) == 3, name


def test_the_eight_requested_categories_all_exist():
    requested = {
        "loop_condition": "Loop-condition errors", "off_by_one": "Off-by-one errors",
        "variable_init": "Variable initialisation", "function_logic": "Function logic",
        "input_handling": "Input handling", "array_index": "Array / index errors",
        "syntax": "Syntax errors", "logic": "Logic errors",
    }
    for key, label in requested.items():
        assert CATEGORIES[key]["label"] == label


# ------------------------------------------------------------------ off-by-one
OFF_BY_ONE = {
    "reads one past the end": "vals = [int(x) for x in input().split()]\nfor i in range(len(vals)):\n    print(vals[i + 1])\n",
    "while i <= len(list)": "vals = [1, 2]\ni = 0\nwhile i <= len(vals):\n    i += 1\nprint(i)\n",
    "range(len(list) + 1)": "vals = [1, 2]\nfor i in range(len(vals) + 1):\n    print(i)\n",
}


@pytest.mark.parametrize("name", list(OFF_BY_ONE))
def test_off_by_one_patterns_are_detected(name):
    assert "off_by_one" in categories(OFF_BY_ONE[name])


def test_a_correct_loop_is_not_called_off_by_one():
    fine = "vals = [int(x) for x in input().split()]\nfor i in range(len(vals) - 1):\n    print(vals[i + 1])\n"
    assert "off_by_one" not in categories(fine)
    assert "off_by_one" not in categories("n = int(input())\nfor i in range(1, n + 1):\n    print(i)\n")


# ------------------------------------------------------------------ variable initialisation
def test_an_accumulator_with_the_wrong_starting_value_is_detected():
    assert "variable_init" in categories("total = 1\nfor i in range(3):\n    total += i\nprint(total)\n")
    assert "variable_init" in categories("result = 0\nfor i in range(1, 4):\n    result *= i\nprint(result)\n")


def test_an_accumulator_reset_inside_its_own_loop_is_detected():
    assert "variable_init" in categories("total = 0\nfor i in range(3):\n    total = 0\n    total += i\nprint(total)\n")


def test_correct_starting_values_are_left_alone():
    assert "variable_init" not in categories("total = 0\nfor i in range(3):\n    total += i\nprint(total)\n")
    assert "variable_init" not in categories("n = int(input())\nresult = 1\nfor i in range(1, n + 1):\n    result *= i\nprint(result)\n")


def test_using_a_variable_before_it_exists_is_a_variable_initialisation_mistake():
    crash = outcome(status="runtime_error", error_type="NameError", stderr="NameError: name 'total' is not defined")
    assert "variable_init" in categories("print(total)\n", [crash])


# ------------------------------------------------------------------ function logic
def test_a_function_that_is_never_called_is_detected():
    assert "function_logic" in categories("def is_prime(n):\n    return n > 1\n\nprint(input())\n")


def test_a_path_with_no_return_is_detected():
    assert "function_logic" in categories("def f(n):\n    if n > 0:\n        return 1\n\nprint(f(int(input())))\n")


def test_a_complete_function_is_left_alone():
    complete = "def f(n):\n    if n > 0:\n        return 1\n    return 0\n\nprint(f(int(input())))\n"
    assert "function_logic" not in categories(complete)
    assert "function_logic" not in categories("def show(n):\n    print(n)\n\nshow(int(input()))\n")   # a procedure need not return


def test_a_none_result_reported_by_python_is_a_function_logic_mistake():
    crash = outcome(status="runtime_error", error_type="TypeError", stderr="TypeError: unsupported operand type(s) for +: 'NoneType' and 'int'")
    assert "function_logic" in categories("def f(n):\n    if n:\n        return 1\n\nprint(f(1) + 1)\n", [crash])


# ------------------------------------------------------------------ nothing that already worked changed
def test_the_original_categories_still_classify_the_same_way():
    assert "syntax" in categories("def f(\n", [outcome(status="syntax_error", stderr="SyntaxError: invalid syntax")])
    assert "input_handling" in categories('n = int(input("Enter n: "))\nprint(n)\n')
    assert "array_index" in categories("print([1][5])\n", [outcome(status="runtime_error", error_type="IndexError", stderr="IndexError: list index out of range")])
    assert "boundary" in categories("print(1)\n", [outcome(kind="edge")])
    assert "loop_condition" in categories("n = int(input())\nresult = 1\nfor i in range(1, n):\n    result *= i\nprint(result)\n")


def test_the_seeded_demo_mistakes_keep_their_category(client, student, exp_ids):
    graded = submit(client, student.headers, exp_ids["factorial"], code("factorial", "off_by_one"))
    assert [x["category"] for x in graded["mistakes"]] == ["loop_condition"]


# ------------------------------------------------------------------ the new categories reach the rest of the system
@pytest.mark.parametrize("category", ["off_by_one", "variable_init", "function_logic"])
def test_practice_is_suggested_for_the_new_categories(db, db_student, category):
    assert category in practice_tags(category)
    suggestions = m.practice_for(db, db_student.id, category)
    assert suggestions and all(s["title"] for s in suggestions)
    published = {e.title for e in db.scalars(__import__("sqlalchemy").select(Experiment).where(Experiment.is_published.is_(True)))}
    assert {s["title"] for s in suggestions} <= published


def test_a_new_category_appears_in_the_dashboard_and_can_drive_a_recommendation(client, db, student, exp_ids):
    broken = "def average(values):\n    if values:\n        return sum(values) / len(values)\n\nn = int(input())\nvals = [int(x) for x in input().split()]\nprint(sum(vals), max(vals), min(vals), round(average(vals), 2))\n"
    for _ in range(2):
        submit(client, student.headers, exp_ids["liststats"], broken)
    dna = client.get("/api/students/me/dashboard", headers=student.headers).json()["mistakes"]
    found = {c["category"]: c for c in dna["categories"]}
    assert "function_logic" in found
    assert found["function_logic"]["label"] == "Function logic" and found["function_logic"]["count"] >= 1
    assert dna["total"] >= 1 and dna["improvement"]["message"]

    rec = client.get("/api/recommendations/me", headers=student.headers).json()["recommendation"]
    assert rec["reason"] and rec["experiment_title"]
    assert any(c in dict(rec["signals"]["top_mistakes"]) for c in found)
