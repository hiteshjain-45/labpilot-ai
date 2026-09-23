"""Post-processing that keeps the Copilot a tutor rather than an answer key."""
import json
import re

FENCE = re.compile(r"```[a-zA-Z0-9_+-]*\n?(.*?)```", re.S)
MAX_FIELD = {"explanation": 700, "hint": 700, "concept_to_review": 160, "next_step": 400}
REQUIRED = ("explanation", "hint")
OMITTED = "[code omitted: LabPilot gives hints, not full solutions]"


def parse_guidance(raw: str) -> dict:
    """Extract the JSON object from a model reply; raises ValueError if unusable."""
    text = (raw or "").strip()
    data = None
    try:
        data = json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                data = json.loads(text[start : end + 1])
            except ValueError:
                data = None
    if not isinstance(data, dict):
        raise ValueError("The AI reply was not a JSON object")
    out = {}
    for key in MAX_FIELD:
        value = data.get(key, "")
        out[key] = value.strip() if isinstance(value, str) else ""
    if any(not out[k] for k in REQUIRED):
        raise ValueError("The AI reply is missing required fields")
    return out


def strip_long_code(text: str, max_lines: int = 3) -> str:
    """Replace fenced code blocks longer than `max_lines` lines."""

    def repl(match: re.Match) -> str:
        body = match.group(1).strip("\n")
        return match.group(0) if len(body.splitlines()) <= max_lines else OMITTED

    return FENCE.sub(repl, text)


def _normalise_line(line: str) -> str:
    return re.sub(r"\s+", "", line)


def leaks_solution(text: str, reference: str, starter_code: str = "", min_lines: int = 3) -> bool:
    """True if the text reproduces the substantive lines of the reference solution.

    Lines that already appear in the starter code are ignored (the student has them). Short solutions are
    protected too: with fewer than `min_lines` substantive lines, all of them must appear to count as a leak.
    """
    boilerplate = {_normalise_line(l) for l in (starter_code or "").splitlines()}
    ref_lines = {
        n for n in (_normalise_line(l) for l in (reference or "").splitlines()) if len(n) >= 8 and n not in boilerplate
    }
    if not ref_lines:
        return False
    text_lines = {_normalise_line(l) for l in (text or "").replace("`", "\n").splitlines()}
    matched = ref_lines & text_lines
    required = max(min(min_lines, len(ref_lines)), int(0.6 * len(ref_lines)))
    return len(matched) >= required


def clean_fields(guidance: dict) -> dict:
    cleaned = {}
    for key, limit in MAX_FIELD.items():
        value = strip_long_code(guidance.get(key, ""))
        cleaned[key] = value[: limit - 1] + "…" if len(value) > limit else value
    return cleaned
