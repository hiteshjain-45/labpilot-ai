
from app.seed import catalogue, check_references
from app.seed.snippets import SNIPPETS


def test_every_reference_solution_passes_every_test_case():
    assert check_references() == []


def test_catalogue_has_the_required_shape():
    assert len(catalogue.EXPERIMENTS) == 5
    for e in catalogue.EXPERIMENTS:
        assert e["problem_statement"] and e["starter_code"] and len(e["hints"]) == 3 and len(e["what_if_scenarios"]) == 2
        kinds = {t["kind"] for t in e["test_cases"]}
        assert "edge" in kinds and any(t["is_hidden"] for t in e["test_cases"]) and any(not t["is_hidden"] for t in e["test_cases"])
        assert all(t["stdin"].endswith("\n") for t in e["test_cases"])


def test_snippet_library_matches_the_catalogue():
    assert set(SNIPPETS) == {"factorial", "liststats", "debug", "prime", "sort"}
    assert all("correct" in variants for variants in SNIPPETS.values())


def test_seeding_twice_changes_nothing(db):
    from app.seed import seed_all

    assert seed_all(db, minimal=True) == {"seeded": False}
