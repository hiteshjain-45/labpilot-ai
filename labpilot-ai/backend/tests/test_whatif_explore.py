"""What-If exploration: hypothetical conditions, what changes, why, and the performance impact.

Exploring must never touch the student's score, the stored predict-and-check history, or the experiment runner.
"""
import pytest
from sqlalchemy import func, select

from app.core.errors import AppError

from app.models import AIInteraction, Attempt, Experiment, SkillRecord, Student, Submission, WhatIfPrediction
from app.services import whatif_explore as ex
from tests.helpers import code, submit

SLOW_SORT = (
    "n = int(input())\n"
    "vals = [int(x) for x in input().split()]\n"
    "for i in range(len(vals)):\n"
    "    for j in range(len(vals) - 1):\n"
    "        if vals[j] > vals[j + 1]:\n"
    "            vals[j], vals[j + 1] = vals[j + 1], vals[j]\n"
    "print(vals[0], vals[-1])\n"
)
FAST_STATS = "n = int(input())\nvals = [int(x) for x in input().split()]\nprint(min(vals), max(vals))\n"
COUNT_UP = "n = int(input())\ntotal = 0\nfor i in range(1, n + 1):\n    total += i\nprint(total)\n"


def sid(db, api_student):
    return db.scalar(select(Student.id).where(Student.user_id == api_student.user["id"]))


# ------------------------------------------------------------------ reading the experiment's own sample input
@pytest.mark.parametrize("stdin,kind,size", [
    ("5\n", "int", 5), ("  12  ", "int", 12), ("3 1 4 1 5\n", "list", 5),
    ("5\n3 1 4 1 5\n", "count_list", 5), ("hello\nworld\n", "other", 0), ("", "other", 0),
])
def test_input_shape_is_recognised(stdin, kind, size):
    shape = ex.read_input(stdin)
    assert (shape.kind, shape.size) == (kind, size)


def test_growing_an_input_keeps_its_shape_and_respects_the_cap():
    shape = ex.read_input("3\n7 8 9\n")
    stdin, size = ex._grow(shape, 10)
    assert size == 30 and stdin.splitlines()[0] == "30" and len(stdin.splitlines()[1].split()) == 30
    assert ex._grow(shape, 100_000)[1] == ex.CAP_ITEMS
    assert ex._grow(ex.read_input("5\n"), 100_000)[1] == ex.CAP_INT


# ------------------------------------------------------------------ which questions fit which experiment
def test_only_the_questions_that_fit_the_code_and_input_are_offered(db, db_student, exp_ids):
    stats = db.get(Experiment, exp_ids["liststats"])
    offered = {c["id"] for c in ex.conditions_for(db, db_student, stats)["conditions"]}
    assert {"input_size", "duplicate_values"} <= offered              # a list of numbers

    factorial = db.get(Experiment, exp_ids["factorial"])
    info = ex.conditions_for(db, db_student, factorial)
    assert info["base_input"]["kind"] == "int"
    assert "duplicate_values" not in {c["id"] for c in info["conditions"]}   # a single number cannot have duplicates
    assert info["code_source"] in ("your latest code", "the starter code")
    assert all(c["question"].startswith("What if") for c in info["conditions"])


def test_a_condition_that_does_not_fit_is_refused_rather_than_guessed(db, db_student, exp_ids):
    factorial = db.get(Experiment, exp_ids["factorial"])
    with pytest.raises(AppError) as err:
        ex.explore(db, db_student, factorial, "duplicate_values", "all_same", code=COUNT_UP)
    assert err.value.status_code == 422 and "does not fit" in err.value.detail


# ------------------------------------------------------------------ the four questions
def test_bigger_input_reports_growth_for_a_slow_program(db, db_student, exp_ids):
    stats = db.get(Experiment, exp_ids["liststats"])
    result = ex.explore(db, db_student, stats, "input_size", "1000", code=SLOW_SORT)
    sizes = [r["size"] for r in result["runs"]]
    assert sizes == sorted(sizes) and sizes[-1] > sizes[0] * 10
    perf = result["performance"]
    assert perf["verdict"] in ("quadratic", "steep", "timed_out"), perf
    assert perf["summary"] and perf["points"][-1]["size"] == sizes[-1]
    assert result["why"] and result["what_changes"]


def test_bigger_input_says_plainly_when_it_is_too_fast_to_measure(db, db_student, exp_ids):
    stats = db.get(Experiment, exp_ids["liststats"])
    perf = ex.explore(db, db_student, stats, "input_size", "1000", code=FAST_STATS)["performance"]
    # The invariant that must hold on any machine, busy or idle: a program whose work is lost in process
    # start-up must never be given a measured growth shape. Which honest answer it gives instead can vary.
    assert perf["verdict"] not in ("sub_linear", "linear", "quadratic", "steep"), perf
    assert perf.get("exact") is not True
    assert "start" in perf["summary"].lower() and perf["startup_ms"] >= 0
    slowest = max(p["runtime_ms"] for p in perf["points"])
    assert slowest < perf["startup_ms"] * 3 + 200, perf   # this program really is trivial


def test_extra_loop_turns_change_the_answer_the_way_an_off_by_one_does(db, db_student, exp_ids):
    factorial = db.get(Experiment, exp_ids["factorial"])
    result = ex.explore(db, db_student, factorial, "extra_iterations", "1", code=COUNT_UP)
    assert "range(1, (n + 1) + 1)" in result["changed_code"]
    assert result["outcome"] == "different"
    assert result["baseline"]["output"] == "15" and result["runs"][-1]["output"] == "21"   # 1..5 then 1..6
    assert "off-by-one" in result["why"]


def test_flipping_a_comparison_changes_only_that_one(db, db_student, exp_ids):
    code = 'n = int(input())\n# keep > out of comments\nprint("a>b")\nif n > 3:\n    print("big")\nelse:\n    print("small")\n'
    prime = db.get(Experiment, exp_ids["prime"])
    options = [o for o in ex._cond_options(prime, code, ex.read_input("5\n"))]
    assert len(options) == 1 and options[0]["label"].startswith("line 4")   # not the comment, not the string
    result = ex.explore(db, db_student, prime, "condition_change", options[0]["id"], code=code)
    assert ">=" in result["changed_code"].splitlines()[3] and result["changed_code"].splitlines()[2] == 'print("a>b")'
    assert result["outcome"] == "same"                                     # 5 is not on the boundary
    assert "boundary" in result["why"]


def test_duplicate_values_keep_the_length_and_change_the_answer(db, db_student, exp_ids):
    stats = db.get(Experiment, exp_ids["liststats"])
    base = ex.read_input(ex.base_case(stats).stdin)
    result = ex.explore(db, db_student, stats, "duplicate_values", "all_same", code=FAST_STATS)
    changed = result["runs"][-1]["stdin"].strip().splitlines()[-1].split()
    assert len(changed) == len(base.items) and len(set(changed)) == 1
    assert result["outcome"] == "different" and result["baseline"]["output"] != result["runs"][-1]["output"]


def test_a_crash_is_reported_as_a_result_not_an_error(db, db_student, exp_ids):
    stats = db.get(Experiment, exp_ids["liststats"])
    breaks_on_repeats = "n = int(input())\nvals = [int(x) for x in input().split()]\nassert len(set(vals)) == len(vals), 'duplicates!'\nprint(sum(vals))\n"
    result = ex.explore(db, db_student, stats, "duplicate_values", "all_same", code=breaks_on_repeats)
    assert result["outcome"] == "crash" and "AssertionError" in (result["runs"][-1]["error_type"] or "")
    assert "stops with" in result["what_changes"]


# ------------------------------------------------------------------ the API, and leaving everything else alone
def test_the_endpoints_work_and_need_a_signed_in_student(client, student, teacher_headers, exp_ids):
    path = f"/api/experiments/{exp_ids['liststats']}/whatif/explore"
    assert client.get(path).status_code == 401
    assert client.get(path, headers=teacher_headers).status_code == 403
    body = client.get(path, headers=student.headers).json()
    assert body["conditions"] and body["base_input"]["stdin"]

    run = client.post(path, json={"condition_id": "input_size", "option": "10", "code": FAST_STATS}, headers=student.headers)
    assert run.status_code == 200
    payload = run.json()
    assert set(payload) >= {"what_changes", "why", "outcome", "baseline", "runs", "performance", "question"}
    assert client.post(path, json={"condition_id": "nope", "option": "10"}, headers=student.headers).status_code == 404
    assert client.post(path, json={"condition_id": "input_size"}, headers=student.headers).status_code == 422


def test_hidden_test_data_is_not_used_as_the_starting_point(db, client, student, exp_ids):
    exp = db.get(Experiment, exp_ids["prime"])
    hidden = {t.stdin.strip() for t in exp.test_cases if t.is_hidden}
    shown = client.get(f"/api/experiments/{exp.id}/whatif/explore", headers=student.headers).json()["base_input"]["stdin"].strip()
    assert shown not in hidden and ex.base_case(exp).is_hidden is False


def test_exploring_changes_no_score_no_skill_and_stores_nothing(db, client, student, exp_ids):
    exp_id = exp_ids["liststats"]
    before = {
        "submissions": db.scalar(select(func.count()).select_from(Submission)),
        "attempts": db.scalar(select(func.count()).select_from(Attempt)),
        "predictions": db.scalar(select(func.count()).select_from(WhatIfPrediction)),
        "ai": db.scalar(select(func.count()).select_from(AIInteraction)),
        "skills": db.scalar(select(func.count()).select_from(SkillRecord)),
    }
    dashboard = client.get("/api/students/me/dashboard", headers=student.headers).json()["stats"]
    for option in ("10", "100"):
        assert client.post(f"/api/experiments/{exp_id}/whatif/explore", json={"condition_id": "input_size", "option": option, "code": FAST_STATS}, headers=student.headers).status_code == 200
    db.expire_all()
    after = {
        "submissions": db.scalar(select(func.count()).select_from(Submission)),
        "attempts": db.scalar(select(func.count()).select_from(Attempt)),
        "predictions": db.scalar(select(func.count()).select_from(WhatIfPrediction)),
        "ai": db.scalar(select(func.count()).select_from(AIInteraction)),
        "skills": db.scalar(select(func.count()).select_from(SkillRecord)),
    }
    assert after == before
    assert client.get("/api/students/me/dashboard", headers=student.headers).json()["stats"] == dashboard


def test_the_existing_predict_and_check_what_if_still_works(client, student, exp_ids):
    exp_id = exp_ids["factorial"]
    listing = client.get(f"/api/experiments/{exp_id}/whatif", headers=student.headers).json()
    assert listing["scenarios"] and "history" in listing
    run = client.post(
        f"/api/experiments/{exp_id}/whatif/run",
        json={"scenario_id": listing["scenarios"][0]["id"], "prediction": "24", "stdin": "5\n"}, headers=student.headers,
    ).json()
    assert "matched" in run and "actual_output" in run and "explanation" in run


# ------------------------------------------------------------------ the scenario types added for the What-If engine
PRIME = (
    "def is_prime(n):\n    if n < 2:\n        return False\n    d = 2\n    while d * d <= n:\n"
    "        if n % d == 0:\n            return False\n        d += 1\n    return True\n\n"
    "n = int(input())\nprint('Prime' if is_prime(n) else 'Not prime')\n"
)
ACCUMULATOR = "n = int(input())\nvals = [int(x) for x in input().split()]\ntotal = 0\nfor v in vals:\n    total += v\nprint(total)\n"


def options_for(exp, condition_id, code, stdin):
    return ex.BY_ID[condition_id].options(exp, code, ex.read_input(stdin))


def test_every_scenario_type_declares_its_concept_risk_mistake_category_and_skill():
    from app.core.constants import CATEGORIES, SKILLS

    assert len(ex.CONDITIONS) >= 7
    for c in ex.CONDITIONS:
        assert c.concept and c.risk in ("Low", "Medium", "High")
        assert c.category in CATEGORIES and c.skill in SKILLS, c.id
    covered = {c.category for c in ex.CONDITIONS}
    assert {"off_by_one", "boundary", "variable_init", "function_logic", "input_handling", "inefficient"} <= covered


def test_a_different_starting_value_is_simulated(db, db_student, exp_ids):
    stats = db.get(Experiment, exp_ids["liststats"])
    options = options_for(stats, "variable_init_change", ACCUMULATOR, ex.base_case(stats).stdin)
    assert options and "starts at 1" in options[0]["label"]
    r = ex.explore(db, db_student, stats, "variable_init_change", options[0]["id"], code=ACCUMULATOR)
    assert "total = 1" in r["changed_code"] and r["outcome"] == "different"
    assert r["concept"] == "Variable initialisation" and r["risk"] == "High" and r["can_introduce_bug"]
    assert r["mistake"]["category"] == "variable_init" and r["skill"]["skill"] == "Python Basics"
    assert int(r["example"]["predicted_result"]) == int(r["example"]["original_result"]) + 1


def test_a_changed_return_is_simulated(db, db_student, exp_ids):
    prime = db.get(Experiment, exp_ids["prime"])
    options = options_for(prime, "return_change", PRIME, ex.base_case(prime).stdin)
    assert options and any("returns" in o["label"] for o in options)
    r = ex.explore(db, db_student, prime, "return_change", options[0]["id"], code=PRIME)
    assert r["concept"] == "Return values" and r["mistake"]["category"] == "function_logic"
    assert r["skill"]["skill"] == "Functions" and r["changed_code"] != PRIME


def test_dropping_the_input_conversion_is_simulated(db, db_student, exp_ids):
    prime = db.get(Experiment, exp_ids["prime"])
    r = ex.explore(db, db_student, prime, "input_validation_change", "no_int", code=PRIME)
    assert "int(input())" not in r["changed_code"] and "input()" in r["changed_code"]
    assert r["outcome"] == "crash" and r["risk"] == "High"
    assert r["mistake"]["category"] == "input_handling" and "TypeError" in r["example"]["predicted_result"]


def test_the_result_carries_the_example_and_the_learning_links(client, db, db_student, student, exp_ids):
    submit(client, student.headers, exp_ids["factorial"], code("factorial", "off_by_one"))
    factorial = db.get(Experiment, exp_ids["factorial"])
    options = options_for(factorial, "extra_iterations", COUNT_UP, ex.base_case(factorial).stdin)
    r = ex.explore(db, db_student, factorial, "extra_iterations", options[0]["id"], code=COUNT_UP)
    assert r["change"]["label"] and r["risk_reason"] and r["question"].startswith("What if")
    assert r["example"]["input"] and r["example"]["original_result"] and r["example"]["predicted_result"]
    assert r["mistake"]["label"] == "Off-by-one errors" and isinstance(r["mistake"]["your_count"], int)
    assert r["skill"]["skill"] == "Loops" and "level" in r["skill"]


def test_risk_is_judged_from_what_actually_happened(db, db_student, exp_ids):
    stats = db.get(Experiment, exp_ids["liststats"])
    harmless = "n = int(input())\nvals = [int(x) for x in input().split()]\ncount = 0\nfor v in vals:\n    count += 1\nprint(len(vals))\n"
    options = options_for(stats, "variable_init_change", harmless, ex.base_case(stats).stdin)
    r = ex.explore(db, db_student, stats, "variable_init_change", options[0]["id"], code=harmless)
    assert r["outcome"] == "same" and r["risk"] == "Low" and r["can_introduce_bug"] is False
    assert "another input could tell" in r["risk_reason"]


def test_the_listing_offers_the_new_types_with_their_metadata(client, student, exp_ids):
    submit(client, student.headers, exp_ids["prime"], PRIME)   # the offer depends on the student's own code
    body = client.get(f"/api/experiments/{exp_ids['prime']}/whatif/explore", headers=student.headers).json()
    by_id = {c["id"]: c for c in body["conditions"]}
    assert {"condition_change", "return_change", "input_validation_change"} <= set(by_id)
    for c in by_id.values():
        assert c["concept"] and c["risk"] and c["category_label"] and c["skill"] and c["options"]


def test_simulating_still_stores_nothing_and_moves_no_skill(client, db, student, exp_ids):
    from app.models import SkillEvidence

    before = db.scalar(select(func.count()).select_from(SkillEvidence))
    r = client.post(
        f"/api/experiments/{exp_ids['prime']}/whatif/explore",
        json={"condition_id": "input_validation_change", "option": "no_int", "code": PRIME}, headers=student.headers,
    )
    assert r.status_code == 200 and r.json()["risk"] == "High"
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(SkillEvidence)) == before
