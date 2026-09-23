from app.seed.catalogue import LIST_STATS


def run_whatif(client, headers, exp_id, scenario_id, prediction, **extra):
    return client.post(f"/api/experiments/{exp_id}/whatif/run", json={"scenario_id": scenario_id, "prediction": prediction, **extra}, headers=headers)


def test_scenarios_are_listed_without_the_teacher_explanation(client, student, exp_ids):
    body = client.get(f"/api/experiments/{exp_ids['factorial']}/whatif", headers=student.headers).json()
    assert [s["id"] for s in body["scenarios"]] == ["range-off-by-one", "start-at-zero"]
    assert all("explanation" not in s and s["modified_code"] for s in body["scenarios"])
    assert body["history"] == []


def test_correct_prediction_is_confirmed_and_credited(client, student, exp_ids):
    r = run_whatif(client, student.headers, exp_ids["factorial"], "range-off-by-one", "24")
    assert r.status_code == 200
    body = r.json()
    assert body["matched"] is True and body["actual_output"] == "24"
    assert body["explanation"].startswith("Your prediction matches the real output.")
    assert body["skill_change"]["skill"] == "Problem Solving" and body["skill_change"]["delta"] > 0
    assert body["ai_provider"] == "rule-based"


def test_wrong_prediction_is_explained_with_the_actual_difference(client, student, exp_ids):
    body = run_whatif(client, student.headers, exp_ids["factorial"], "range-off-by-one", "120").json()
    assert body["matched"] is False and body["actual_output"] == "24" and body["skill_change"] is None
    assert "you predicted `120`" in body["explanation"] and "printed `24`" in body["explanation"]
    assert "range(1, n)" in body["explanation"] or "end value" in body["explanation"]


def test_predicting_an_error_counts_when_the_program_crashes(client, student, exp_ids):
    body = run_whatif(client, student.headers, exp_ids["liststats"], "index-past-end", "It crashes with an IndexError").json()
    assert body["matched"] is True and body["actual_output"].startswith("[IndexError]")
    wrong = run_whatif(client, student.headers, exp_ids["liststats"], "index-past-end", "15").json()
    assert wrong["matched"] is False and "IndexError" in wrong["explanation"]


def test_custom_input_can_be_supplied(client, student, exp_ids):
    body = run_whatif(client, student.headers, exp_ids["factorial"], "range-off-by-one", "6", stdin="4\n").json()
    assert body["actual_output"] == "6" and body["matched"] is True and body["stdin"] == "4\n"


def test_history_is_kept_newest_first(client, student, exp_ids):
    for guess in ("1", "24"):
        run_whatif(client, student.headers, exp_ids["factorial"], "range-off-by-one", guess)
    history = client.get(f"/api/experiments/{exp_ids['factorial']}/whatif", headers=student.headers).json()["history"]
    assert [h["prediction"] for h in history] == ["24", "1"]


def test_invalid_requests_are_rejected(client, student, exp_ids):
    assert run_whatif(client, student.headers, exp_ids["factorial"], "range-off-by-one", "   ").status_code == 422
    assert run_whatif(client, student.headers, exp_ids["factorial"], "no-such-scenario", "24").status_code == 404
    assert run_whatif(client, student.headers, exp_ids["factorial"], "range-off-by-one", "x" * 3000).status_code == 422
    assert run_whatif(client, student.headers, 999999, "range-off-by-one", "24").status_code == 404


def test_floor_division_scenario_matches_the_authored_lesson(client, student, exp_ids):
    scenario = next(s for s in LIST_STATS["what_if_scenarios"] if s["id"] == "floor-division")
    body = run_whatif(client, student.headers, exp_ids["liststats"], "floor-division", "25.25").json()
    assert body["matched"] is False and body["actual_output"] == "25.00"
    assert scenario["explanation"] in body["explanation"]
