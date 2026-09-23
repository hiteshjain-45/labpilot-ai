"""Small text utilities shared by services."""
import re


def normalize_output(text: str) -> str:
    """Normalise program output for comparison.

    Line endings are unified, trailing whitespace on each line is removed and trailing
    blank lines are dropped. Leading whitespace and inner spacing are significant.
    """
    lines = [ln.rstrip() for ln in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def truncate(text: str, limit: int) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n… [truncated {len(text) - limit} characters]"


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "experiment"
