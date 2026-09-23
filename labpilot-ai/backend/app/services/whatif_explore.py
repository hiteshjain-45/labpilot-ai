"""What-If exploration: change a hypothetical condition and see what happens, and why.

This sits beside the existing predict-and-check What-If (`services/whatif.py`) and does not replace it or the
experiment runner. Nothing is stored: exploring is free and repeatable.

Each condition is one entry in CONDITIONS, so supporting more experiments later means adding a condition, not
touching the route or the page. A condition says when it applies, which choices it offers, and how to build the
variant. Everything then follows the same path: run the student's own program unchanged, run the variant, compare,
and explain the difference from local rules (no AI needed).
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import category_label
from app.core.errors import AppError, NotFound
from app.models import Experiment, Submission
from app.sandbox import get_sandbox
from app.utils.text import normalize_output, truncate

MAX_VARIANT_RUNS = 4          # sandbox runs per request, on top of one baseline run
# A list can be grown far enough for the cost of the algorithm to show up in the clock; a single number cannot,
# because for a program like factorial a big number means enormous arithmetic rather than more steps.
LIST_FACTORS = (10, 100, 1000)
INT_FACTORS = (2, 4, 8)
MEASURABLE_MS = 25            # below this, wall-clock timing is start-up noise, not the program's work
CAP_INT = 5000
CAP_ITEMS = 5000


# ---------------------------------------------------------------------------- reading the experiment's own input
@dataclass
class InputShape:
    """What the experiment's sample input looks like, so a condition can change it sensibly."""

    kind: str                 # int | list | count_list | other
    number: Optional[int] = None
    items: list[str] = field(default_factory=list)
    raw: str = ""

    @property
    def size(self) -> int:
        return self.number if self.kind == "int" and self.number is not None else len(self.items)

    def render(self, number: Optional[int] = None, items: Optional[list[str]] = None) -> str:
        items = self.items if items is None else items
        number = self.number if number is None else number
        if self.kind == "int":
            return f"{number}\n"
        if self.kind == "list":
            return " ".join(items) + "\n"
        if self.kind == "count_list":
            return f"{len(items)}\n" + " ".join(items) + "\n"
        return self.raw


def _parse_module(code: str):
    try:
        return ast.parse(code or "")
    except (SyntaxError, ValueError, RecursionError):
        return None


def read_input(stdin: str) -> InputShape:
    lines = [ln.strip() for ln in (stdin or "").strip().splitlines() if ln.strip()]
    numbers = re.compile(r"^-?\d+(\s+-?\d+)*$")
    if len(lines) == 1 and re.fullmatch(r"-?\d+", lines[0]):
        return InputShape("int", number=int(lines[0]), raw=stdin)
    if len(lines) == 1 and numbers.match(lines[0]):
        return InputShape("list", items=lines[0].split(), raw=stdin)
    if len(lines) == 2 and re.fullmatch(r"\d+", lines[0]) and numbers.match(lines[1]):
        return InputShape("count_list", items=lines[1].split(), raw=stdin)
    return InputShape("other", raw=stdin or "")


def base_case(experiment: Experiment) -> Optional[object]:
    """The visible, ordinary test case to explore from: students may only see visible data."""
    visible = [t for t in experiment.test_cases if not t.is_hidden]
    return next((t for t in visible if t.kind == "normal"), None) or (visible[0] if visible else None)


# ---------------------------------------------------------------------------- conditions
@dataclass
class Variant:
    """One thing to run: a label, the code and the input."""

    label: str
    code: str
    stdin: str
    size: Optional[int] = None


@dataclass
class Condition:
    id: str
    question: str                                    # shown as the student's question
    label: str
    explains: str                                    # what this condition is for
    applies: Callable[[Experiment, str, InputShape], bool]
    options: Callable[[Experiment, str, InputShape], list[dict]]
    build: Callable[..., list[Variant]]
    concept: str = ""                                # the idea the change is about
    risk: str = "Medium"                             # how likely this kind of change is to introduce a bug
    category: Optional[str] = None                   # the Mistake DNA category it belongs to
    skill: Optional[str] = None                      # the Skill Passport skill it exercises
    measures_performance: bool = False


def _ranges(code: str) -> list[tuple[int, str]]:
    return [(m.start(), m.group(0)) for m in re.finditer(r"range\s*\([^()\n]*\)", code)]


COMPARISONS = {"<=": "<", "<": "<=", ">=": ">", ">": ">=", "==": "!=", "!=": "=="}


def _comparisons(code: str) -> list[tuple[int, int, str, str]]:
    """(line number, offset, operator, the line) for every comparison outside a string or comment."""
    found = []
    for n, line in enumerate(code.splitlines(), start=1):
        stripped = line.split("#")[0]
        if '"' in stripped or "'" in stripped:
            continue
        for m in re.finditer(r"(?<![<>=!+\-*/%])(<=|>=|==|!=|<|>)(?!=)", stripped):
            found.append((n, m.start(), m.group(1), line.strip()))
    return found


# ---- what if the input gets bigger
def _size_applies(exp, code, shape):
    return shape.kind in ("int", "list", "count_list") and shape.size > 0


def _factors(shape: InputShape) -> tuple[int, ...]:
    return INT_FACTORS if shape.kind == "int" else LIST_FACTORS


def _size_options(exp, code, shape):
    return [
        {"id": str(f), "label": f"{f} times bigger", "detail": f"up to {_grow(shape, f)[1]}" + ("" if shape.kind == "int" else " values")}
        for f in _factors(shape)
    ]


def _grow(shape: InputShape, factor: int) -> tuple[str, int]:
    if shape.kind == "int":
        value = min(shape.number * factor, CAP_INT)
        return shape.render(number=value), value
    wanted = min(len(shape.items) * factor, CAP_ITEMS)
    items = (shape.items * (wanted // len(shape.items) + 1))[:wanted]
    return shape.render(items=items), len(items)


def _size_build(exp, code, shape, option, **_):
    chosen = int(option)
    variants = []
    for factor in _factors(shape):
        if factor > chosen:
            break
        stdin, size = _grow(shape, factor)
        variants.append(Variant(f"{factor} times bigger", code, stdin, size))
    return variants


# ---- what if the loop runs more times
def _loop_applies(exp, code, shape):
    return bool(_ranges(code))


def _loop_options(exp, code, shape):
    return [{"id": str(n), "label": f"{n} more times", "detail": f"the first loop, {_ranges(code)[0][1]}"} for n in (1, 5, 10)]


def _loop_build(exp, code, shape, option, **_):
    extra = int(option)
    start, text = _ranges(code)[0]
    inner = text[text.index("(") + 1 : text.rindex(")")]
    parts = [p.strip() for p in inner.split(",")]
    parts[1 if len(parts) > 1 else 0] = f"({parts[1 if len(parts) > 1 else 0]}) + {extra}"
    changed = code[:start] + f"range({', '.join(parts)})" + code[start + len(text) :]
    return [Variant(f"loop runs {extra} more time{'s' if extra != 1 else ''}", changed, shape.raw)]


# ---- what if the condition is changed
def _cond_applies(exp, code, shape):
    return bool(_comparisons(code))


def _cond_options(exp, code, shape):
    return [
        {"id": f"{n}:{off}", "label": f"line {n}: {op} becomes {COMPARISONS[op]}", "detail": truncate(line, 70)}
        for n, off, op, line in _comparisons(code)[:6]
    ]


def _cond_build(exp, code, shape, option, **_):
    try:
        want_line, want_off = (int(p) for p in option.split(":"))
    except ValueError:
        raise AppError(422, "Choose one of the offered conditions")
    match = next((c for c in _comparisons(code) if c[0] == want_line and c[1] == want_off), None)
    if match is None:
        raise AppError(422, "That condition is no longer in your code. Reset the scenario and choose again.")
    n, off, op, _line = match
    lines = code.splitlines(keepends=True)
    line = lines[n - 1]
    lines[n - 1] = line[:off] + COMPARISONS[op] + line[off + len(op) :]
    return [Variant(f"{op} becomes {COMPARISONS[op]} on line {n}", "".join(lines), shape.raw)]


# ---- what if the input has duplicate values
def _dup_applies(exp, code, shape):
    return shape.kind in ("list", "count_list") and len(shape.items) >= 2


def _dup_options(exp, code, shape):
    return [
        {"id": "repeat_first", "label": "every value repeated", "detail": "the same length, but each value appears twice"},
        {"id": "all_same", "label": "every value identical", "detail": "the most extreme case of duplication"},
    ]


def _dup_build(exp, code, shape, option, **_):
    items = shape.items
    if option == "all_same":
        changed = [items[0]] * len(items)
        label = "every value the same"
    else:
        half = items[: (len(items) + 1) // 2]
        changed = [v for v in half for _ in (0, 1)][: len(items)]
        label = "every value repeated twice"
    return [Variant(label, code, shape.render(items=changed))]


# ---- what if the accumulator started from the other value
def _init_targets(code: str):
    """(line, offset, name, value) for `name = 0` / `name = 1` that is later updated in place."""
    tree = _parse_module(code)
    if tree is None:
        return []
    updated = {n.target.id for n in ast.walk(tree) if isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name)}
    found = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Constant) and node.value.value in (0, 1)
            and not isinstance(node.value.value, bool) and node.targets[0].id in updated
        ):
            found.append((node.value.lineno, node.value.col_offset, node.targets[0].id, node.value.value))
    return found


def _init_applies(exp, code, shape):
    return bool(_init_targets(code))


def _init_options(exp, code, shape):
    return [
        {"id": f"{line}:{off}", "label": f"`{name}` starts at {1 - value} instead of {value}", "detail": f"line {line}"}
        for line, off, name, value in _init_targets(code)[:4]
    ]


def _init_build(exp, code, shape, option, **_):
    line, off = (int(x) for x in option.split(":"))
    match = next((t for t in _init_targets(code) if t[0] == line and t[1] == off), None)
    if match is None:
        raise AppError(422, "That starting value is no longer in your code. Reset the scenario and choose again.")
    _, _, name, value = match
    lines = code.splitlines(keepends=True)
    text = lines[line - 1]
    lines[line - 1] = text[:off] + str(1 - value) + text[off + len(str(value)):]
    return [Variant(f"`{name}` starts at {1 - value}", "".join(lines), shape.raw)]


# ---- what if the function returned something else
def _return_targets(code: str):
    tree = _parse_module(code)
    if tree is None:
        return []
    found = []
    for func in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
        for node in ast.walk(func):
            if isinstance(node, ast.Return) and node.value is not None:
                text = ast.unparse(node.value) if hasattr(ast, "unparse") else "its value"
                found.append((node.lineno, func.name, text))
    return found


def _return_applies(exp, code, shape):
    return bool(_return_targets(code))


def _return_options(exp, code, shape):
    out = []
    for line, func, text in _return_targets(code)[:4]:
        flipped = {"True": "False", "False": "True"}.get(text)
        out.append({"id": str(line), "label": f"`{func}` returns {flipped or 'nothing'} on line {line}", "detail": f"currently returns {text}"})
    return out


def _return_build(exp, code, shape, option, **_):
    line = int(option)
    match = next((t for t in _return_targets(code) if t[0] == line), None)
    if match is None:
        raise AppError(422, "That return is no longer in your code. Reset the scenario and choose again.")
    _, func, text = match
    lines = code.splitlines(keepends=True)
    original = lines[line - 1]
    indent = original[: len(original) - len(original.lstrip())]
    flipped = {"True": "False", "False": "True"}.get(text)
    lines[line - 1] = f"{indent}return {flipped}\n" if flipped else f"{indent}return\n"
    return [Variant(f"`{func}` returns {flipped or 'None'}", "".join(lines), shape.raw)]


# ---- what if the input were not validated
def _validation_applies(exp, code, shape):
    return "int(input(" in code.replace(" ", "")


def _validation_options(exp, code, shape):
    return [{"id": "no_int", "label": "the input is used without converting it to a number", "detail": "int(input()) becomes input()"}]


def _validation_build(exp, code, shape, option, **_):
    changed = re.sub(r"int\s*\(\s*input\s*\(([^()]*)\)\s*\)", r"input(\1)", code, count=1)
    if changed == code:
        raise AppError(422, "There is no int(input()) left to change. Reset the scenario and choose again.")
    return [Variant("the input stays text", changed, shape.raw)]


CONDITIONS: list[Condition] = [
    Condition("input_size", "What if I increase the input size?", "Bigger input",
              "Runs the same program on larger and larger input and times each run.",
              _size_applies, _size_options, _size_build,
              concept="Algorithmic complexity", risk="Low", category="inefficient", skill="Problem Solving",
              measures_performance=True),
    Condition("extra_iterations", "What if this loop runs more times?", "Longer loop",
              "Adds iterations to the first loop and shows what the program prints then.",
              _loop_applies, _loop_options, _loop_build,
              concept="Loop boundaries", risk="High", category="off_by_one", skill="Loops"),
    Condition("condition_change", "What if the condition is changed?", "Flipped condition",
              "Turns one comparison into its neighbour (< becomes <=, and so on). This covers loop, boundary and "
              "sorting or searching comparisons, since they are all the same kind of change.",
              _cond_applies, _cond_options, _cond_build,
              concept="Boundary and comparison conditions", risk="High", category="boundary", skill="Problem Solving"),
    Condition("duplicate_values", "What if the input contains duplicate values?", "Duplicate values",
              "Keeps the input the same length but makes values repeat.",
              _dup_applies, _dup_options, _dup_build,
              concept="Data that is not distinct", risk="Medium", category="logic", skill="Arrays"),
    Condition("variable_init_change", "What if the starting value were different?", "Different starting value",
              "Changes an accumulator's starting value from 0 to 1, or the other way round.",
              _init_applies, _init_options, _init_build,
              concept="Variable initialisation", risk="High", category="variable_init", skill="Python Basics"),
    Condition("return_change", "What if the function returned something else?", "Different return",
              "Makes a function return nothing, or the opposite boolean, on one path.",
              _return_applies, _return_options, _return_build,
              concept="Return values", risk="High", category="function_logic", skill="Functions"),
    Condition("input_validation_change", "What if the input were not validated?", "Unvalidated input",
              "Uses the input as text instead of converting it to a number.",
              _validation_applies, _validation_options, _validation_build,
              concept="Reading and converting input", risk="High", category="input_handling", skill="Python Basics"),
]
BY_ID = {c.id: c for c in CONDITIONS}


# ---------------------------------------------------------------------------- running and explaining
def student_code(db: Session, student_id: int, experiment: Experiment) -> tuple[str, str]:
    """The student's own latest code for this experiment, or the starter code."""
    latest = db.scalars(
        select(Submission).where(Submission.student_id == student_id, Submission.experiment_id == experiment.id)
        .order_by(Submission.created_at.desc(), Submission.id.desc()).limit(1)
    ).first()
    if latest and latest.code.strip():
        return latest.code, "your latest code"
    return experiment.starter_code or "", "the starter code"


def _describe(outcome) -> dict:
    return {
        "output_truncated": outcome.output_truncated,
        "output": truncate(outcome.stdout.strip(), 400),
        "error_type": outcome.error_type,
        "timed_out": outcome.timed_out,
        "runtime_ms": outcome.runtime_ms,
        "crashed": outcome.exit_code != 0,
    }


def _same(a: dict, b: dict) -> bool:
    return not a["crashed"] and not b["crashed"] and normalize_output(a["output"]) == normalize_output(b["output"])


def _performance(runs: list[dict], sizes: list[int], startup_ms: int) -> Optional[dict]:
    """Growth from measured wall-clock time, honest about what is too fast to measure."""
    points = [
        {"size": s, "runtime_ms": r["runtime_ms"], "work_ms": max(0, r["runtime_ms"] - startup_ms), "timed_out": r["timed_out"]}
        for s, r in zip(sizes, runs)
    ]
    if any(p["timed_out"] for p in points):
        first_over = next(p for p in points if p["timed_out"])
        finished = [p for p in points if not p["timed_out"]]
        return {
            "points": points, "startup_ms": startup_ms, "verdict": "timed_out",
            "summary": (
                f"At {first_over['size']} values the program no longer finishes in time"
                + (f", although {finished[-1]['size']} values took only {finished[-1]['runtime_ms']} ms" if finished else "")
                + ". That jump is what an inefficient approach looks like: it is fine on small input and hopeless on large input."
            ),
        }
    # A run is only worth timing if it is clearly above the noise: starting Python costs a variable ~30-60 ms, so a
    # small run's "work" is mostly jitter. Comparing two jittery numbers is how a bubble sort gets called efficient.
    floor = startup_ms * 1.5 + MEASURABLE_MS
    measurable = [p for p in points if p["runtime_ms"] >= floor]
    if not measurable:
        return {
            "points": points, "startup_ms": startup_ms, "verdict": "too_fast",
            "summary": "Every size finishes almost instantly, so these timings are mostly the fixed cost of starting Python, not the work your program does.",
        }
    top = measurable[-1]
    if len(measurable) >= 2:
        base, exact = measurable[0], True
        base_work = max(1, base["work_ms"])
    else:
        # Only the largest run rises above the noise. Its smaller neighbour did less work than the floor, so the
        # growth below is a lower bound: the truth is at least this steep, never gentler.
        base, exact = points[max(0, points.index(top) - 1)], False
        base_work = max(1, int(floor - startup_ms))
    size_ratio = top["size"] / max(1, base["size"])
    time_ratio = top["work_ms"] / base_work
    if size_ratio <= 1:
        return {"points": points, "startup_ms": startup_ms, "verdict": "unknown", "summary": "Not enough different sizes to judge growth."}
    if not exact and time_ratio < size_ratio * 1.8:
        # A lower bound can prove growth is steep, never that it is gentle, so do not guess a shape here.
        return {
            "points": points, "startup_ms": startup_ms, "verdict": "needs_bigger_input", "exact": False,
            "summary": (
                f"Only {top['size']} values does enough work to time reliably ({top['runtime_ms']} ms against a start-up cost of about "
                f"{startup_ms} ms), so the shape of the growth cannot be judged yet. Everything smaller finishes within the noise."
            ),
        }
    if time_ratio < size_ratio * 0.6:
        verdict, shape = "sub_linear", "grows more slowly than the input"
    elif time_ratio < size_ratio * 1.8:
        verdict, shape = "linear", "grows roughly in step with the input (about linear)"
    elif time_ratio < size_ratio * size_ratio * 1.6:
        verdict, shape = "quadratic", "grows much faster than the input (closer to the square of it)"
    else:
        verdict, shape = "steep", "grows very steeply, faster even than the square of the input"
    about = f"about {time_ratio:.1f}" if exact else f"at least {time_ratio:.0f}"
    return {
        "points": points, "startup_ms": startup_ms, "verdict": verdict, "exact": exact,
        "summary": (
            f"Going from {base['size']} to {top['size']} values ({size_ratio:.0f} times bigger) took {about} times as long, so the work {shape}."
            + (" On a big input this is the part that will time out." if verdict in ("quadratic", "steep") else "")
        ),
    }


WHY = {
    "variable_init_change": {
        "same": "The starting value happens not to matter for this input, but it usually does: a running sum must start at 0 and a running product at 1.",
        "different": "The starting value is part of the answer. A sum that starts at 1 is one too big; a product that starts at 0 stays 0 forever.",
        "crash": "The changed starting value leads the program into a step it cannot complete.",
    },
    "return_change": {
        "same": "The caller does not depend on that return on this input, so nothing visible changed. Another input would tell them apart.",
        "different": "The caller uses what the function hands back, so changing the return changes the answer. A path with no return hands back None.",
        "crash": "The caller tried to use the returned value, and None (or the opposite answer) cannot be used that way.",
    },
    "input_validation_change": {
        "same": "Nothing arithmetic was done with the value on this input, so text behaved like a number here. That is luck, not safety.",
        "different": "Without the conversion the value stays text, so comparisons and arithmetic behave differently.",
        "crash": "Text cannot be used where a number is expected, so the program stops. This is why input is converted and checked.",
    },
    "input_size": {
        "same": "The answer follows the same rule whatever the size, so only the time taken changes.",
        "different": "A bigger input means more values to process, so the result itself changes as well as the time.",
        "crash": "The larger input pushes the program past a limit it never reached on the sample input.",
    },
    "extra_iterations": {
        "same": "The extra turns of the loop do not change what is printed: the work they do is either repeated or thrown away.",
        "different": "Each turn of the loop contributes to the result, so more turns means a different answer. This is exactly how an off-by-one error behaves.",
        "crash": "The extra turns run past the end of the data, so the program asks for something that is not there.",
    },
    "condition_change": {
        "same": "No value in this input sits exactly on the boundary, so both versions of the condition choose the same branch. A different input would tell them apart.",
        "different": "The comparison decides what happens at the boundary, so changing it changes which values are included.",
        "crash": "The changed comparison lets the program reach a case it was written to avoid.",
    },
    "duplicate_values": {
        "same": "Your program handles each value on its own, so repeats make no difference here.",
        "different": "Repeated values are counted more than once, or collapse together, so the answer moves.",
        "crash": "The repeated values reach a step that assumed every value was different.",
    },
}


def conditions_for(db: Session, student, experiment: Experiment) -> dict:
    code, source = student_code(db, student.id, experiment)
    case = base_case(experiment)
    shape = read_input(case.stdin if case else "")
    available = []
    for c in CONDITIONS:
        try:
            ok = c.applies(experiment, code, shape)
        except Exception:  # a condition must never break the page for an experiment it does not suit
            ok = False
        if ok:
            available.append({
                "id": c.id, "question": c.question, "label": c.label, "explains": c.explains,
                "concept": c.concept, "risk": c.risk, "category": c.category, "skill": c.skill,
                "category_label": category_label(c.category) if c.category else None,
                "measures_performance": c.measures_performance, "options": c.options(experiment, code, shape),
            })
    return {
        "code": code, "code_source": source,
        "base_input": {"name": case.name if case else None, "stdin": case.stdin if case else "", "kind": shape.kind, "size": shape.size},
        "conditions": available,
        "note": "Exploring never changes your score and is not stored.",
    }


def _risk(condition: Condition, outcome: str) -> tuple[str, str]:
    """How dangerous this change is, judged from what actually happened rather than from the type alone."""
    if outcome == "crash":
        return "High", "The program stopped instead of answering, so this change would break it outright."
    if outcome == "different":
        level = "High" if condition.risk == "High" else "Medium"
        return level, "The answer changed, so making this change by accident would be a real bug."
    return "Low", (
        f"The answer did not change on this input, but {condition.concept.lower()} is still a common source of bugs: "
        "another input could tell the two versions apart."
    )


def _learning_links(db: Session, student, condition: Condition) -> dict:
    """Ties the scenario to the student's own Mistake DNA and Skill Passport. Read-only: neither is modified."""
    from app.services.mistakes import mistake_profile, practice_for
    from app.services.skills import get_passport

    mistake = None
    if condition.category:
        recorded = next(
            (c for c in mistake_profile(db, student.id, with_practice=False)["categories"] if c["category"] == condition.category),
            None,
        )
        mistake = {
            "category": condition.category, "label": category_label(condition.category),
            "your_count": recorded["count"] if recorded else 0,
            "recurring": bool(recorded and recorded["recurring"]),
            "practice": practice_for(db, student.id, condition.category, limit=1),
        }
    skill = None
    if condition.skill:
        entry = next((s for s in get_passport(db, student.id)["skills"] if s["skill"] == condition.skill), None)
        if entry:
            skill = {"skill": entry["skill"], "mastery": entry["mastery"], "level": entry["level"],
                     "needs_practice": entry["needs_practice"]}
    return {"mistake": mistake, "skill": skill}


def explore(db: Session, student, experiment: Experiment, condition_id: str, option: str, code: Optional[str] = None) -> dict:
    condition = BY_ID.get(condition_id)
    if condition is None:
        raise NotFound("What-if condition not found")
    source = "the code you are editing"
    if not (code and code.strip()):
        code, source = student_code(db, student.id, experiment)
    if not code.strip():
        raise AppError(422, "There is no code to explore yet. Write something in the editor first.")
    case = base_case(experiment)
    shape = read_input(case.stdin if case else "")
    if not condition.applies(experiment, code, shape):
        raise AppError(422, "That question does not fit this experiment and your current code.")

    variants = condition.build(experiment, code, shape, option)[:MAX_VARIANT_RUNS]
    if not variants:
        raise AppError(422, "Nothing to try for that choice.")

    sandbox = get_sandbox()
    baseline = _describe(sandbox.run(code, shape.raw))
    runs = [
        {
            "label": v.label, "size": v.size, "code_changed": v.code != code, "input_changed": v.stdin != shape.raw,
            "stdin": truncate(v.stdin, 200), **_describe(sandbox.run(v.code, v.stdin)),
        }
        for v in variants
    ]
    last = runs[-1]

    if last["timed_out"]:
        outcome = "crash"
        what = f"With {last['label']}, the program no longer finishes in time."
    elif last["crashed"]:
        outcome = "crash"
        what = f"With {last['label']}, the program stops with {last['error_type'] or 'an error'}."
    elif _same(baseline, last):
        outcome = "same"
        what = f"With {last['label']}, the program still prints the same answer."
    else:
        outcome = "different"
        what = f"With {last['label']}, the program prints `{truncate(last['output'], 60)}` instead of `{truncate(baseline['output'], 60)}`."

    performance = None
    if condition.measures_performance:
        startup = sandbox.run("pass\n", "").runtime_ms  # the fixed cost of starting Python, measured on this machine
        timed = [{**baseline, "size": shape.size}] + [{**r, "size": r["size"] or 0} for r in runs]
        performance = _performance(timed, [t["size"] for t in timed], startup)

    changed_variant = next((v for v in variants if v.code != code), None)
    risk, risk_reason = _risk(condition, outcome)
    links = _learning_links(db, student, condition)
    chosen = next((o for o in condition.options(experiment, code, shape) if o["id"] == option), None)
    return {
        "condition_id": condition.id,
        "question": condition.question,
        "concept": condition.concept,
        "change": {
            "label": (chosen or {}).get("label", variants[-1].label),
            "detail": (chosen or {}).get("detail"),
            "code_changed": bool(changed_variant),
        },
        "risk": risk,
        "risk_reason": risk_reason,
        "can_introduce_bug": outcome != "same",
        "example": {
            "input": truncate(shape.raw, 200),
            "original_result": truncate(baseline["output"], 200) if not baseline["crashed"] else f"stopped with {baseline['error_type'] or 'an error'}",
            "predicted_result": (
                "did not finish in time" if last["timed_out"]
                else f"stops with {last['error_type'] or 'an error'}" if last["crashed"]
                else truncate(last["output"], 200)
            ),
        },
        "mistake": links["mistake"],
        "skill": links["skill"],
        "option": option,
        "code_source": source,
        "what_changes": what,
        "outcome": outcome,
        "why": WHY[condition.id][outcome],
        "baseline": {"label": "your program as it is", "stdin": shape.raw, **baseline},
        "runs": runs,
        "performance": performance,
        "changed_code": changed_variant.code if changed_variant else None,
    }
