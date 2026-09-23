"""Rule-based guidance used by MockProvider (and as the safety net when a real provider fails)."""
import re

from app.core.constants import CATEGORIES

EXPLAIN = {
    "syntax": "Python could not read your code, so nothing ran. {detail}",
    "input_handling": "The program's input or output handling is off. {detail}",
    "array_index": "Your code asked for a list position that does not exist. {detail}",
    "off_by_one": "The program does one step too many or one too few. {detail}",
    "variable_init": "A variable starts with the wrong value, or is reset when it should not be. {detail}",
    "function_logic": "The function itself is not doing its job: it is never called, or it does not return a value on every path. {detail}",
    "runtime": "The program crashed while running. {detail}",
    "boundary": "Ordinary inputs work, but a special case does not. {detail}",
    "loop_condition": "A loop is running the wrong number of times. {detail}",
    "inefficient": "The logic may be right, but the program is too slow or uses too much memory. {detail}",
    "logic": "The program runs without crashing, but its answer differs from the expected output. {detail}",
}

HINTS = {
    "syntax": [
        "Look at the line number Python reports and the line just above it.",
        "Check for a missing colon after if/for/while/def, an unclosed bracket or quote, or inconsistent indentation.",
        "Read the caret (^) in the message: it points at where Python got confused. Fix that one spot and run again before touching anything else.",
    ],
    "input_handling": [
        "Compare exactly what your program prints with what the tests expect, including extra words.",
        "input() prints its prompt to the output, so input('Enter n: ') adds text the checker does not expect. Use input() with no prompt and print only the answer.",
        "Check how each input line is read: one number per line needs int(input()); several numbers on one line need input().split() and a conversion for every item.",
    ],
    "array_index": [
        "Think about which positions a list of n items actually has.",
        "The valid indexes are 0 to n-1. Find the largest index your loop or expression can reach and compare it with n-1.",
        "Trace your loop on a list of just 2 items: write the index value on every pass and mark the pass where it leaves the valid range.",
    ],
    "off_by_one": [
        "Count the turns by hand: what is the first value, and what is the last?",
        "range(a, b) includes a and stops before b, and the last index of a list of length n is n - 1.",
        "Write out the indices your loop touches for a 3-item list. If the last one is 3, or the first is 1, adjust the bound by one.",
    ],
    "variable_init": [
        "Look at the line where the variable is first given a value.",
        "A running sum starts at 0, a running product at 1, and both are set before the loop, not inside it.",
        "Move the starting value above the loop and choose it so the first update leaves the answer unchanged.",
    ],
    "function_logic": [
        "Check the function itself: is it called, and does it hand a value back?",
        "Every path through the function needs a return; a path without one hands back None.",
        "Call your function once with a simple value and print the result. If it prints None, find the path that has no return.",
    ],
    "runtime": [
        "Read the last line of the error: it names the error type and the value involved.",
        "Find the line number in the traceback and look at the values of the variables on that line.",
        "Add a temporary print() of the variables just before the failing line, run once, then compare the values with what that line assumes.",
    ],
    "boundary": [
        "Your code handles typical inputs. Which unusual input might the tests include?",
        "Try the smallest and largest allowed values, zero, a negative number and a single-element list, and see which one your code mishandles.",
        "Run your logic by hand for the failing edge case and note the first line where your result parts ways with the expected one; that line needs a special case or a different starting value.",
    ],
    "loop_condition": [
        "Check where your loop starts and where it stops.",
        "range(a, b) includes a but stops before b. Write out the values the loop variable takes for a small input and check that none is missing or extra.",
        "For one failing input, list the loop variable's values by hand, then list the values you actually need. The difference shows which bound to adjust.",
    ],
    "inefficient": [
        "Estimate how many times your innermost loop runs for the largest input.",
        "If it runs about n times for n up to a very large number, look for a way to stop earlier or to test far fewer candidates.",
        "Ask what the largest number worth checking is, and whether you can leave the loop as soon as the answer is known.",
    ],
    "logic": [
        "Pick one failing test and predict by hand what each variable holds after every line.",
        "Compare your hand trace with the expected output and find the first step where they differ. The fault is on or just before that step.",
        "Check the starting value of each variable, the order of operations, and whether every branch assigns or prints what you intend.",
    ],
}

NEXT_STEP = {
    "syntax": "Fix the highlighted line, then press Run again.",
    "input_handling": "Adjust how input is read or what is printed, then press Run and compare the output.",
    "array_index": "Change the loop bounds or index, then re-run the failing test.",
    "off_by_one": "Adjust one bound by one, then re-run the tests and check the first and last values again.",
    "variable_init": "Fix the starting value and where it is set, then re-run the tests.",
    "function_logic": "Call the function on one example and print what it returns, then re-run the tests.",
    "runtime": "Fix the line named in the error and run again.",
    "boundary": "Add handling for the special case and re-run all visible tests.",
    "loop_condition": "Adjust the range bounds, then run again and compare each failing test.",
    "inefficient": "Improve the approach, then submit to check the hidden performance test.",
    "logic": "Trace one failing input by hand, fix the first wrong step, and run again.",
}


def _failing_line(code: str, stderr: str) -> str:
    matches = re.findall(r'File "<student>", line (\d+)', stderr or "")
    if not matches:
        return ""
    lines = (code or "").splitlines()
    n = int(matches[-1])
    if 1 <= n <= len(lines):
        return f" The problem is reported on line {n}: `{lines[n - 1].strip()[:80]}`."
    return f" The problem is reported on line {n}."


def _first_visible_failure(ctx: dict):
    latest = ctx.get("latest_run") or {}
    for t in latest.get("failing_tests", []):
        if t.get("expected") is not None and t.get("status") == "wrong_answer":
            return t
    return None


def build_rule_based_guidance(ctx: dict) -> dict:
    category, level = ctx["category"], max(1, min(3, int(ctx.get("hint_level", 1))))
    exp = ctx["experiment"]
    concepts = exp.get("concepts") or []
    teacher_hints = exp.get("teacher_hints") or []

    if category == "not_run":
        return {
            "explanation": "There are no results yet, so there is nothing to diagnose.",
            "hint": "Press Run to execute your code against the visible tests, then ask again. The Copilot works from real results.",
            "concept_to_review": concepts[0] if concepts else "Reading the problem statement",
            "next_step": "Write a first version, even an incomplete one, and run it.",
        }
    if category == "none":
        return {
            "explanation": "Your latest run passes every visible test.",
            "hint": "Think about inputs the visible tests do not cover: the smallest, the largest, zero, negative values and repeated values.",
            "concept_to_review": concepts[0] if concepts else "Edge-case testing",
            "next_step": "Submit for grading, or try a What-If scenario to test your understanding of the code.",
        }

    detail = ctx.get("category_detail") or ""
    explanation = EXPLAIN[category].format(detail=detail).strip()
    if explanation and explanation[-1] not in ".!?":
        explanation += "."
    latest = ctx.get("latest_run") or {}
    stderr = next((t.get("stderr", "") for t in latest.get("failing_tests", []) if t.get("stderr")), "")
    if category in ("syntax", "array_index", "runtime", "input_handling"):
        explanation += _failing_line(ctx.get("student_code", ""), stderr)
    failure = _first_visible_failure(ctx)
    if failure and category in ("logic", "loop_condition", "boundary", "input_handling"):
        shown = (failure.get("actual") or "").strip().replace("\n", " / ")[:60]
        want = (failure.get("expected") or "").strip().replace("\n", " / ")[:60]
        given = (failure.get("stdin") or "").strip().replace("\n", " / ")[:40]
        explanation += f" For input `{given}` it printed `{shown}` but `{want}` was expected."

    pattern = ctx.get("pattern") or {}
    earlier = int(pattern.get("times_before") or 0)
    if earlier:
        explanation += (
            f" You have made this kind of mistake in {earlier} earlier attempt{'s' if earlier != 1 else ''} too, "
            "so it is worth learning the pattern and not only fixing this line."
        )

    next_step = NEXT_STEP[category]
    if teacher_hints:
        next_step = f"Experiment tip: {teacher_hints[min(level, len(teacher_hints)) - 1]}"
    meta = CATEGORIES.get(category, {})
    return {
        "explanation": explanation,
        "hint": HINTS[category][level - 1],
        "concept_to_review": concepts[0] if concepts else meta.get("concept", ""),
        "next_step": next_step,
    }
