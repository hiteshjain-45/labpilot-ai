"""Regression tests for the sandbox escapes found in the final security review.

Before the hardening, `().__class__.__base__.__subclasses__()` led to `os.system`, and as root `fork` worked too.
Two independent layers now stop this: a static check (readable errors for the classic tricks) and an audit hook
(refuses the operation itself, however it was reached). The second group of tests skips the static check and the
import guard on purpose, so the audit hook is what has to stop the operation.

These are best-effort defences, not a security boundary: see docs/SECURITY.md.
"""
import os
import subprocess
import sys

import pytest

from app.sandbox import get_sandbox

sandbox = get_sandbox()
posix_only = pytest.mark.skipif(os.name != "posix", reason="uses POSIX paths and the resource module")


def run(code, stdin=""):
    return sandbox.run(code, stdin)


def via_foreign_globals(expr):
    """Evaluate `expr` inside typing.ForwardRef with foreign globals: this skips the static check and the import
    guard, so only the audit hook stands between the program and the operation."""
    return f"import typing\ntyping.ForwardRef({expr!r})._evaluate({{}}, {{}}, recursive_guard=frozenset())\nprint('REACHED')\n"


def imp(name):
    return f"__import__({name!r}, {{}}, None, (), 0)"


# ------------------------------------------------------------------------------ static check
OBJECT_GRAPH_ESCAPES = {
    "subclasses to os.system": "W=[c for c in ().__class__.__base__.__subclasses__() if c.__name__=='_wrap_close'][0]\nprint(W.__init__.__globals__['system']('id'))",
    "getattr with a built string": "print(getattr((), '__cl'+'ass__'))",
    "eval": "print(eval('1+1'))",
    "exec": "exec('print(1)')",
    "builtin module through __self__": "print(print.__self__)",
    "generator frame": "g = (i for i in range(3))\nprint(g.gi_frame)",
    "traceback frame": "try:\n    1/0\nexcept Exception as e:\n    print(e.__traceback__.tb_frame.f_globals)",
}


@pytest.mark.parametrize("name", list(OBJECT_GRAPH_ESCAPES))
def test_object_graph_escapes_are_rejected_with_a_clear_message(name):
    out = run(OBJECT_GRAPH_ESCAPES[name])
    assert out.exit_code != 0 and out.stdout == "" and "SandboxRestriction" in out.stderr and "line" in out.stderr


def test_a_program_may_reuse_the_names_of_restricted_builtins_for_its_own_things():
    out = run("vars = [1, 2, 3]\ndef compile(x):\n    return x * 2\nlocals_ = compile(4)\nprint(len(vars), locals_)\n")
    assert out.exit_code == 0 and out.stdout.split() == ["3", "8"]


# ------------------------------------------------------------------------------ audit hook
HOOK_CASES = {
    "run a shell command": (imp("os") + ".system('echo PWNED')", "PermissionError"),
    "fork a process": (imp("os") + ".fork()", "PermissionError"),
    "read a system file": (imp("io") + ".open('/etc/passwd').read()", "PermissionError"),
    "list a directory": (imp("os") + ".listdir('/')", "PermissionError"),
    "delete a file": (imp("os") + ".remove('/tmp/labpilot_nothing')", "PermissionError"),
    "walk the heap": (imp("gc") + ".get_objects()", "PermissionError"),
    "open a socket": (imp("socket") + ".socket()", "ImportError"),
    "start a subprocess": (imp("subprocess") + ".run(['id'])", "ImportError"),
    "load ctypes": (imp("ctypes"), "ImportError"),
}


@posix_only
@pytest.mark.parametrize("name", list(HOOK_CASES))
def test_the_audit_hook_refuses_dangerous_operations_even_when_earlier_checks_are_bypassed(name):
    expr, error = HOOK_CASES[name]
    out = run(via_foreign_globals(expr))
    assert out.exit_code != 0 and "REACHED" not in out.stdout and "PWNED" not in out.stdout
    assert error in out.stderr and "disabled in the LabPilot sandbox" in out.stderr


@posix_only
def test_a_file_cannot_be_created_even_through_the_real_io_module(tmp_path):
    target = tmp_path / "escaped.txt"
    out = run(via_foreign_globals(imp("io") + f".open({str(target)!r}, 'w').write('x')"))
    assert out.exit_code != 0 and not target.exists()


@posix_only
def test_the_real_sys_module_reached_through_another_module_is_still_contained():
    out = run("import typing\nprint(typing.sys.modules['os'].system('id'))\n")
    assert out.exit_code != 0 and "uid=" not in out.stdout and "PermissionError" in out.stderr


# ------------------------------------------------------------------------------ nothing legitimate broke
PROGRAM = '''
import math, random, re, json, statistics, itertools, functools, heapq, bisect, textwrap, sys
from collections import Counter, deque, defaultdict, namedtuple
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from datetime import datetime, timedelta
from enum import Enum
from typing import NamedTuple

@dataclass
class Point:
    x: int
    y: int = 0
    def norm(self):
        return math.hypot(self.x, self.y)

class Emp(NamedTuple):
    name: str
    age: int

Pair = namedtuple("Pair", "a b")
Color = Enum("Color", "RED GREEN")

class Animal:
    def __init__(self, name):
        self.name = name
    def __repr__(self):
        return f"{self.__class__.__name__}({self.name})"

class Dog(Animal):
    def __init__(self, name):
        super().__init__(name)

@functools.lru_cache(maxsize=None)
def fib(n):
    return n if n < 2 else fib(n - 1) + fib(n - 2)

random.seed(4)
print(Point(3, 4).norm(), Pair(1, 2).b, Emp("Ana", 20).age, Color.GREEN.name, Dog("rex"), fib(30), random.randint(1, 100))
print(datetime.strptime("2024-03-05", "%Y-%m-%d").day, (datetime(2024, 1, 1) + timedelta(days=40)).month)
print(Counter("hello").most_common(1), sorted({"b": 1, "a": 2}.items()), statistics.mean([1, 2, 3, 4]))
print(Decimal("1.10") + Decimal("2.20"), Fraction(1, 3) + Fraction(1, 6), json.loads(json.dumps({"k": [1, 2]})), re.findall(r"\\d+", "a12b345"))
print(list(itertools.permutations([1, 2, 3]))[3], heapq.nsmallest(2, [5, 1, 4]), bisect.bisect([1, 3, 5], 4), textwrap.shorten("hello world foo", 11))
d = deque([1, 2, 3]); d.rotate(1); dd = defaultdict(list); dd["k"].append(1)
sys.setrecursionlimit(3000)
print(d, dict(dd), sys.stdin.readline().strip(), input())
'''


def test_ordinary_programs_behave_exactly_as_they_do_on_the_host_interpreter():
    stdin = "first\nsecond\n"
    expected = subprocess.run([sys.executable, "-c", PROGRAM], input=stdin, capture_output=True, text=True, check=True).stdout
    out = run(PROGRAM, stdin)
    assert out.exit_code == 0, out.stderr
    assert out.stdout == expected


def test_runtime_errors_are_still_reported_in_the_students_own_terms():
    out = run("data = [1, 2, 3]\nprint(data[5])\n")
    assert out.error_type == "IndexError" and 'File "<student>", line 2' in out.stderr
    assert "harness" not in out.stderr.lower() and "audit" not in out.stderr.lower()
