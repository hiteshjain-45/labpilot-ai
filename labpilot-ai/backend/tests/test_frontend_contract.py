"""Every endpoint the React client calls must exist in the API, with a method the API allows."""
import re
from pathlib import Path

from app.main import app

API_JS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "api.js"


def _client_calls():
    source = API_JS.read_text()
    calls = []
    for helper, path in re.findall(r"\b(get|post|patch|del)\(\s*[`\"](/api/[^`\"]*)[`\"]", source):
        path = re.sub(r"\$\{query\([^}]*\)\}", "", path.split("?")[0])
        calls.append(({"del": "delete"}.get(helper, helper), re.sub(r"\$\{[^}]+\}", "{}", path)))
    return calls


def _api_routes():
    routes = set()
    for path, item in app.openapi()["paths"].items():
        for method in item:
            routes.add((method, re.sub(r"\{[^}]+\}", "{}", path)))
    return routes


def test_the_client_calls_a_meaningful_number_of_endpoints():
    assert len(_client_calls()) >= 35


def test_every_client_call_matches_an_api_route():
    routes = _api_routes()
    missing = [c for c in _client_calls() if c not in routes]
    assert missing == []


def test_frontend_display_thresholds_match_the_backend():
    from app.core.constants import SKILL_LEVELS
    from app.services.recommendation import MASTERY_THRESHOLD

    viz = (API_JS.parent / "components" / "viz.jsx").read_text()
    marks = [int(x) for x in re.search(r"marks = \[([0-9, ]+)\]", viz).group(1).split(",")]
    assert sorted(marks) == sorted(t for t, _ in SKILL_LEVELS if t > 0)
    assert int(re.search(r"threshold = (\d+)", viz).group(1)) == round(MASTERY_THRESHOLD * 100)
