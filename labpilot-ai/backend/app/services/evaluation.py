"""Run student code against test cases in the sandbox and judge the results."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Optional

from app.sandbox import get_sandbox
from app.utils.text import normalize_output

SYNTAX_ERROR_TYPES = {"SyntaxError", "IndentationError", "TabError"}


@dataclass
class TestSpec:
    """Lightweight stand-in for a stored test case (used for reference validation and tests)."""

    __test__ = False  # not a pytest test class, despite the name

    name: str
    stdin: str
    expected_output: str
    kind: str = "normal"
    is_hidden: bool = False
    weight: int = 1
    id: Optional[int] = None


@dataclass
class TestOutcome:
    __test__ = False

    test_case_id: Optional[int]
    name: str
    kind: str
    is_hidden: bool
    stdin: str
    expected_output: str
    weight: int
    passed: bool
    status: str  # passed | wrong_answer | runtime_error | syntax_error | timeout | output_limit
    actual_output: str
    stderr: str
    error_type: Optional[str]
    runtime_ms: int
    timed_out: bool


def judge(test: Any, outcome) -> TestOutcome:
    if outcome.timed_out:
        status = "timeout"
    elif outcome.error_type == "OutputLimitExceeded":
        status = "output_limit"
    elif outcome.exit_code != 0:
        status = "syntax_error" if outcome.error_type in SYNTAX_ERROR_TYPES else "runtime_error"
    elif normalize_output(outcome.stdout) == normalize_output(test.expected_output):
        status = "passed"
    else:
        status = "wrong_answer"
    return TestOutcome(
        test_case_id=getattr(test, "id", None),
        name=test.name,
        kind=test.kind,
        is_hidden=test.is_hidden,
        stdin=test.stdin,
        expected_output=test.expected_output,
        weight=max(1, test.weight or 1),
        passed=status == "passed",
        status=status,
        actual_output=outcome.stdout,
        stderr=outcome.stderr,
        error_type=outcome.error_type,
        runtime_ms=outcome.runtime_ms,
        timed_out=outcome.timed_out,
    )


def evaluate_code(code: str, tests: list, sandbox=None) -> list[TestOutcome]:
    """Execute `code` once per test case (each in its own sandbox process)."""
    sandbox = sandbox or get_sandbox()

    def run_one(test) -> TestOutcome:
        return judge(test, sandbox.run(code, test.stdin))

    if len(tests) <= 1:
        return [run_one(t) for t in tests]
    with ThreadPoolExecutor(max_workers=min(4, len(tests))) as pool:
        return list(pool.map(run_one, tests))


def score_ratio(outcomes: list[TestOutcome]) -> float:
    total = sum(o.weight for o in outcomes)
    if total == 0:
        return 0.0
    return sum(o.weight for o in outcomes if o.passed) / total
