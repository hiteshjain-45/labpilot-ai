"""Mistake DNA: classify what went wrong and maintain a per-student mistake profile.

Classification is deterministic (test outcomes + static analysis with `ast`), so it works
without any AI provider and is unit-testable. The AI Copilot *explains* the category; it does
not decide it.
"""
import ast
import re
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import CATEGORIES, CATEGORY_PRIORITY, category_label, practice_tags
from app.models import Attempt, Experiment, MistakeRecord, Submission
from app.services.evaluation import TestOutcome
from app.utils.timeutil import utcnow

SLOW_MS = 1500  # a passing test slower than this is flagged as inefficient
_INPUT_PARSE_ERRORS = re.compile(
    r"invalid literal|could not convert|not enough values to unpack|too many values to unpack", re.I
)


@dataclass
class Mistake:
    category: str
    detail: str

    @property
    def label(self) -> str:
        return category_label(self.category)


# ---------------------------------------------------------------- static analysis helpers
def _parse(code: str) -> Optional[ast.AST]:
    try:
        return ast.parse(code)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None


def has_input_prompt(tree: Optional[ast.AST]) -> bool:
    """input("Enter n: ") prints the prompt to stdout, which breaks output comparison."""
    if tree is None:
        return False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "input"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
            and node.args[0].value.strip()
        ):
            return True
    return False


def has_while_loop(tree: Optional[ast.AST]) -> bool:
    return tree is not None and any(isinstance(n, (ast.While,)) for n in ast.walk(tree))


def _bare_bound(stop: ast.AST) -> bool:
    if isinstance(stop, ast.Name):
        return True
    if isinstance(stop, ast.Call):
        func = stop.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
        return name in {"len", "int", "isqrt"}
    return False


def _uses_previous_item(loop: ast.For) -> bool:
    """True if the loop body looks at the previous position (`i - 1`).

    Starting a loop at 1 is then deliberate, as in insertion sort or comparing neighbours.
    """
    if not isinstance(loop.target, ast.Name):
        return False
    var = loop.target.id
    for node in ast.walk(ast.Module(body=loop.body, type_ignores=[])):
        if (
            isinstance(node, ast.BinOp) and isinstance(node.op, ast.Sub)
            and isinstance(node.left, ast.Name) and node.left.id == var
            and isinstance(node.right, ast.Constant) and node.right.value == 1
        ):
            return True
    return False


def has_suspect_range(tree: Optional[ast.AST]) -> bool:
    """Heuristic for off-by-one loop bounds: range(1, n), range(2, n), range(len(a) - 1) ...

    Loops that start at 1 because the body compares each item with the previous one are not flagged.
    """
    if tree is None:
        return False
    deliberate = {
        id(loop.iter) for loop in ast.walk(tree) if isinstance(loop, ast.For) and _uses_previous_item(loop)
    }
    for node in ast.walk(tree):
        if id(node) in deliberate:
            continue
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "range"):
            continue
        args = node.args
        if len(args) == 2 and isinstance(args[0], ast.Constant) and args[0].value in (1, 2) and _bare_bound(args[1]):
            return True
        if (
            len(args) == 1
            and isinstance(args[0], ast.BinOp)
            and isinstance(args[0].op, ast.Sub)
            and isinstance(args[0].right, ast.Constant)
            and args[0].right.value == 1
        ):
            return True
    return False


def _loop_targets(tree) -> dict:
    """for <name> in range(len(<seq>)) loops, as {loop variable: sequence name}."""
    loops = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.For) and isinstance(node.target, ast.Name)):
            continue
        call = node.iter
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "range" and call.args:
            inner = call.args[-1]
            if (
                isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name) and inner.func.id == "len"
                and inner.args and isinstance(inner.args[0], ast.Name)
            ):
                loops[node.target.id] = (inner.args[0].id, node)
    return loops


def reads_past_the_end(tree: Optional[ast.AST]) -> Optional[str]:
    """seq[i + 1] inside `for i in range(len(seq))`: the last turn of the loop reads one item too far."""
    if tree is None:
        return None
    for var, (seq, loop) in _loop_targets(tree).items():
        for node in ast.walk(loop):
            if not (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == seq):
                continue
            index = node.slice
            if (
                isinstance(index, ast.BinOp) and isinstance(index.op, ast.Add)
                and isinstance(index.left, ast.Name) and index.left.id == var
                and isinstance(index.right, ast.Constant) and index.right.value == 1
            ):
                return f"{seq}[{var} + 1] inside `for {var} in range(len({seq}))` reads one position past the end on the last turn"
    return None


def inclusive_length_bound(tree: Optional[ast.AST]) -> Optional[str]:
    """`while i <= len(seq)` or `range(len(seq) + 1)`: one more turn than there are items."""
    if tree is None:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and node.ops and isinstance(node.ops[0], (ast.LtE, ast.GtE)):
            right = node.comparators[0]
            if isinstance(right, ast.Call) and isinstance(right.func, ast.Name) and right.func.id == "len":
                return "a loop compares with <= len(...), so it runs one turn more than there are items"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "range" and node.args:
            last = node.args[-1]
            if (
                isinstance(last, ast.BinOp) and isinstance(last.op, ast.Add)
                and isinstance(last.left, ast.Call) and isinstance(last.left.func, ast.Name) and last.left.func.id == "len"
                and isinstance(last.right, ast.Constant) and last.right.value == 1
            ):
                return "range(len(...) + 1) gives one index more than the list has"
    return None


_NEUTRAL = {ast.Add: 0, ast.Sub: 0, ast.Mult: 1, ast.Div: 1}


def wrong_accumulator_start(tree: Optional[ast.AST]) -> Optional[str]:
    """total = 1 then total += ..., or result = 0 then result *= ...: the starting value cancels the work."""
    if tree is None:
        return None
    starts = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, (int, float)) and not isinstance(node.value.value, bool):
                starts.setdefault(node.targets[0].id, node.value.value)
    for node in ast.walk(tree):
        if isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
            neutral = _NEUTRAL.get(type(node.op))
            if neutral is None or name not in starts:
                continue
            start = starts[name]
            if start != neutral and start in (0, 1):
                doing = "added to" if neutral == 0 else "multiplied"
                return f"`{name}` starts at {start} but is then {doing}; a running {'sum' if neutral == 0 else 'product'} should start at {neutral}"
    return None


def resets_inside_loop(tree: Optional[ast.AST]) -> Optional[str]:
    """An accumulator assigned inside the same loop that updates it: it is wiped every turn."""
    if tree is None:
        return None
    for loop in (n for n in ast.walk(tree) if isinstance(n, (ast.For, ast.While))):
        assigned = {
            t.id
            for node in ast.walk(loop) if isinstance(node, ast.Assign)
            for t in node.targets if isinstance(t, ast.Name) and isinstance(node.value, ast.Constant)
        }
        updated = {n.target.id for n in ast.walk(loop) if isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name)}
        both = assigned & updated
        if both:
            return f"`{sorted(both)[0]}` is set to a fixed value inside the loop that also updates it, so it restarts every turn"
    return None


def function_problem(tree: Optional[ast.AST]) -> Optional[str]:
    """A defined function that is never called, or that can finish without returning a value."""
    if tree is None:
        return None
    functions = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    if not functions:
        return None
    called = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    for f in functions:
        if f.name not in called and not f.decorator_list:
            return f"the function `{f.name}` is defined but never called"
    for f in functions:
        returns = [n for n in ast.walk(f) if isinstance(n, ast.Return) and n.value is not None]
        if not returns:
            continue  # a procedure that prints is fine
        last = f.body[-1]
        falls_through = not isinstance(last, ast.Return) and not (
            isinstance(last, (ast.If, ast.For, ast.While, ast.Try)) and _always_returns(last)
        )
        if falls_through:
            return f"`{f.name}` returns a value on some paths but not all; a path with no return gives back None"
    return None


def _always_returns(node) -> bool:
    if isinstance(node, ast.Return):
        return True
    if isinstance(node, ast.If):
        return bool(node.orelse) and _always_returns(node.body[-1]) and _always_returns(node.orelse[-1])
    return False


# ---------------------------------------------------------------- classification
def _last_error_line(stderr: str) -> str:
    lines = [ln.strip() for ln in (stderr or "").strip().splitlines() if ln.strip()]
    return lines[-1][:200] if lines else ""


def classify_outcomes(code: str, outcomes: list[TestOutcome]) -> list[Mistake]:
    """Return the distinct mistake categories evidenced by a set of test outcomes."""
    failures = [o for o in outcomes if not o.passed]
    found: dict[str, str] = {}

    def add(category: str, detail: str) -> None:
        found.setdefault(category, detail)

    tree = _parse(code)
    for o in failures:
        if o.status == "syntax_error":
            add("syntax", _last_error_line(o.stderr) or "The code could not be parsed")
            return [Mistake(c, d) for c, d in found.items()]  # nothing else can be judged

    wrong_answers: list[TestOutcome] = []
    for o in failures:
        err = _last_error_line(o.stderr)
        if o.status == "timeout":
            if o.kind != "performance" and has_while_loop(tree):
                add("loop_condition", f"Timed out on '{o.name}': a while loop may never terminate")
            else:
                add("inefficient", f"Timed out on '{o.name}': the approach is too slow for this input")
        elif o.status == "output_limit":
            add("loop_condition", f"Produced endless output on '{o.name}': a loop is not stopping")
        elif o.status == "runtime_error":
            et = o.error_type or ""
            if et == "IndexError":
                add("array_index", f"IndexError on '{o.name}': {err}")
            elif et == "EOFError" or (et == "ValueError" and _INPUT_PARSE_ERRORS.search(o.stderr or "")):
                add("input_handling", f"Could not read the input on '{o.name}': {err}")
            elif et in ("NameError", "UnboundLocalError"):
                add("variable_init", f"{et} on '{o.name}': a variable is used before it is given a value")
            elif et == "TypeError" and "NoneType" in (o.stderr or ""):
                add("function_logic", f"TypeError on '{o.name}': a function returned None, so it has a path with no return")
            elif et in ("ZeroDivisionError", "RecursionError"):
                add("boundary", f"{et} on '{o.name}': a special value or missing base case is not handled")
            elif et == "MemoryError":
                add("inefficient", f"MemoryError on '{o.name}': too much memory used")
            else:
                add("runtime", f"{et or 'Runtime error'} on '{o.name}': {err}")
        elif o.status == "wrong_answer":
            wrong_answers.append(o)

    if wrong_answers:
        names = ", ".join(f"'{o.name}'" for o in wrong_answers[:3])
        # Static checks that name a specific, fixable cause. They are reported alongside the outcome-based
        # category below, so nothing that was already detected changes.
        for detector, category in (
            (wrong_accumulator_start, "variable_init"), (resets_inside_loop, "variable_init"),
            (reads_past_the_end, "off_by_one"), (inclusive_length_bound, "off_by_one"),
            (function_problem, "function_logic"),
        ):
            detail = detector(tree)
            if detail:
                add(category, f"{detail} (seen on {names})")
        if has_input_prompt(tree):
            add("input_handling", "input() is given a prompt string, so extra text is printed with the answer")
        elif all(o.kind == "edge" for o in wrong_answers):
            add("boundary", f"Only edge cases fail ({names}); ordinary inputs pass")
        elif has_suspect_range(tree):
            add("loop_condition", f"Wrong answer on {names}; a range() bound looks off by one")
        else:
            empty = all(not o.actual_output.strip() for o in wrong_answers)
            add("logic", "No output was printed - is print() missing?" if empty else f"Wrong answer on {names}")

    if not failures and any(o.runtime_ms > SLOW_MS for o in outcomes):
        add("inefficient", "All tests pass, but at least one runs slowly")

    return [Mistake(c, d) for c, d in found.items()]


def primary_category(mistakes: list[Mistake]) -> Optional[str]:
    cats = {m.category for m in mistakes}
    for category in CATEGORY_PRIORITY:
        if category in cats:
            return category
    return None


def record_mistakes(
    db: Session, student_id: int, experiment_id: int, submission_id: int, source: str,
    mistakes: list[Mistake], now=None,
) -> None:
    for m in mistakes:
        db.add(MistakeRecord(
            student_id=student_id, experiment_id=experiment_id, submission_id=submission_id,
            category=m.category, detail=m.detail[:300], source=source, created_at=now or utcnow(),
        ))


# ---------------------------------------------------------------- profile & aggregates
def practice_for(db: Session, student_id: int, category: str, limit: int = 2) -> list[dict]:
    from app.services.recommendation import best_ratios, MASTERY_THRESHOLD  # avoid import cycle

    best = best_ratios(db, student_id)
    exps = db.scalars(select(Experiment).where(Experiment.is_published.is_(True))).all()
    order = {"beginner": 0, "intermediate": 1, "advanced": 2}
    tags = set(practice_tags(category))
    matches = [e for e in exps if tags & set(e.focus_categories or [])]
    matches.sort(key=lambda e: (best.get(e.id, 0) >= MASTERY_THRESHOLD, order.get(e.difficulty, 0), e.id))
    return [
        {"experiment_id": e.id, "title": e.title, "difficulty": e.difficulty, "mastered": best.get(e.id, 0) >= MASTERY_THRESHOLD}
        for e in matches[:limit]
    ]


WINDOW_DAYS = 14  # trends compare the last 14 days with the 14 days before


def _occurrences(db: Session, student_id: int) -> list[tuple]:
    """One row per (attempt, category): (category, attempt_id, experiment_id, last_time, last_record_id).

    Re-running the same buggy code several times inside one attempt is one occurrence, not five, so a
    "recurring" pattern means the student made that kind of mistake again in a later attempt.
    """
    return db.execute(
        select(MistakeRecord.category, Submission.attempt_id, MistakeRecord.experiment_id,
               func.max(MistakeRecord.created_at), func.max(MistakeRecord.id))
        .join(Submission, Submission.id == MistakeRecord.submission_id)
        .where(MistakeRecord.student_id == student_id)
        .group_by(MistakeRecord.category, Submission.attempt_id, MistakeRecord.experiment_id)
    ).all()


def _attempts_between(db: Session, student_id: int, start, end) -> int:
    return db.scalar(
        select(func.count()).select_from(Attempt).where(Attempt.student_id == student_id, Attempt.started_at > start, Attempt.started_at <= end)
    ) or 0


def _improvement(db: Session, student_id: int, occurrences: list[tuple], categories: list[dict], now) -> dict:
    recent_cut, prior_cut = now - timedelta(days=WINDOW_DAYS), now - timedelta(days=2 * WINDOW_DAYS)
    recent_n = sum(1 for o in occurrences if recent_cut < o[3] <= now)
    prior_n = sum(1 for o in occurrences if prior_cut < o[3] <= recent_cut)
    recent_a, prior_a = _attempts_between(db, student_id, recent_cut, now), _attempts_between(db, student_id, prior_cut, recent_cut)
    rate_r = recent_n / recent_a if recent_a else None
    rate_p = prior_n / prior_a if prior_a else None
    if recent_a < 2 or prior_a < 2:
        direction = "not_enough_data"
        message = "Not enough activity to show a trend yet. A trend needs at least two attempts in each of the last two 14-day periods."
    elif rate_r < 0.8 * rate_p:
        direction, message = "improving", f"You are making fewer mistakes per attempt: {rate_r:.1f} in the last {WINDOW_DAYS} days, down from {rate_p:.1f} in the {WINDOW_DAYS} days before."
    elif rate_r > 1.25 * rate_p:
        direction, message = "worsening", f"You are making more mistakes per attempt: {rate_r:.1f} in the last {WINDOW_DAYS} days, up from {rate_p:.1f} in the {WINDOW_DAYS} days before."
    else:
        direction, message = "steady", f"Your mistakes per attempt are about the same as before ({rate_r:.1f} against {rate_p:.1f})."
    return {
        "direction": direction, "message": message, "window_days": WINDOW_DAYS,
        "recent": {"attempts": recent_a, "mistakes": recent_n, "per_attempt": None if rate_r is None else round(rate_r, 2)},
        "previous": {"attempts": prior_a, "mistakes": prior_n, "per_attempt": None if rate_p is None else round(rate_p, 2)},
        "improved_categories": [c["label"] for c in categories if c["recurring"] and recent_a and c["trend"] in ("falling", "quiet")],
        "worsening_categories": [c["label"] for c in categories if c["trend"] == "rising" or (c["trend"] == "new" and c["recurring"])],
    }


def mistake_profile(db: Session, student_id: int, now=None, with_practice: bool = True) -> dict:
    now = now or utcnow()
    recent_cut, prior_cut = now - timedelta(days=WINDOW_DAYS), now - timedelta(days=2 * WINDOW_DAYS)
    occurrences = _occurrences(db, student_id)
    by_category: dict[str, list[tuple]] = {}
    for o in occurrences:
        by_category.setdefault(o[0], []).append(o)
    grand = len(occurrences)
    categories = []
    for category, items in sorted(by_category.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        count = len(items)
        r = sum(1 for o in items if recent_cut < o[3] <= now)
        p = sum(1 for o in items if prior_cut < o[3] <= recent_cut)
        trend = "quiet" if r == 0 else "new" if p == 0 else "rising" if r > p else "falling" if r < p else "steady"
        meta = CATEGORIES.get(category, {})
        categories.append({
            "category": category,
            "label": category_label(category),
            "count": count,
            "percent": round(100 * count / grand, 1) if grand else 0.0,
            "recurring": count >= 2,
            "recent_count": r,
            "trend": trend,
            "last_seen": max(o[3] for o in items),
            "experiments_affected": len({o[2] for o in items}),
            "concept": meta.get("concept", ""),
            "tip": meta.get("tip", ""),
            "practice": practice_for(db, student_id, category) if with_practice and count >= 2 else [],
        })
    return {"total": grand, "categories": categories, "improvement": _improvement(db, student_id, occurrences, categories, now)}


def pattern_for(db: Session, student_id: int, category: str, current_attempt_id: Optional[int] = None, experiment_id: Optional[int] = None) -> dict:
    """How often this category appeared in EARLIER attempts (used to tailor Copilot guidance)."""
    earlier = [o for o in _occurrences(db, student_id) if o[0] == category and o[1] != current_attempt_id]
    return {
        "times_before": len(earlier),
        "experiments_affected": len({o[2] for o in earlier}),
        "same_experiment": sum(1 for o in earlier if o[2] == experiment_id),
    }


def recent_mistakes(db: Session, student_id: int, limit: int = 10) -> list[dict]:
    """Newest mistakes, one entry per (attempt, category)."""
    latest = sorted(_occurrences(db, student_id), key=lambda o: (o[3], o[4]), reverse=True)[:limit]
    if not latest:
        return []
    rows = {
        m.id: (m, title)
        for m, title in db.execute(
            select(MistakeRecord, Experiment.title).join(Experiment, Experiment.id == MistakeRecord.experiment_id)
            .where(MistakeRecord.id.in_([o[4] for o in latest]))
        ).all()
    }
    return [
        {
            "id": m.id, "category": m.category, "label": category_label(m.category), "detail": m.detail,
            "experiment_id": m.experiment_id, "experiment_title": title, "source": m.source,
            "submission_id": m.submission_id, "created_at": m.created_at,
        }
        for m, title in (rows[o[4]] for o in latest if o[4] in rows)
    ]


def student_category_counts(db: Session, student_id: int, limit: int = 40) -> Counter:
    """Occurrences per category over the student's most recent mistakes (attempt-level, see _occurrences)."""
    newest = sorted(_occurrences(db, student_id), key=lambda o: o[3], reverse=True)[:limit]
    return Counter(o[0] for o in newest)


def class_mistake_summary(db: Session) -> list[dict]:
    """Class-wide counts per category (distinct attempts). Contains no student identifiers by design."""
    attempts = func.count(func.distinct(Submission.attempt_id))
    rows = db.execute(
        select(MistakeRecord.category, attempts, func.count(func.distinct(MistakeRecord.student_id)))
        .join(Submission, Submission.id == MistakeRecord.submission_id)
        .group_by(MistakeRecord.category)
        .order_by(attempts.desc(), MistakeRecord.category)
    ).all()
    return [{"category": c, "label": category_label(c), "count": n, "students_affected": s} for c, n, s in rows]


def class_top_mistake_by_experiment(db: Session) -> dict[int, dict]:
    """The most common mistake category per experiment, as class totals only."""
    attempts = func.count(func.distinct(Submission.attempt_id))
    rows = db.execute(
        select(MistakeRecord.experiment_id, MistakeRecord.category, attempts, func.count(func.distinct(MistakeRecord.student_id)))
        .join(Submission, Submission.id == MistakeRecord.submission_id)
        .group_by(MistakeRecord.experiment_id, MistakeRecord.category)
    ).all()
    top: dict[int, dict] = {}
    for exp_id, category, n, students in sorted(rows, key=lambda r: (-r[2], r[1])):
        top.setdefault(exp_id, {"category": category, "label": category_label(category), "count": n, "students_affected": students})
    return top
