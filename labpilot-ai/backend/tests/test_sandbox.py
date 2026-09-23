"""The sandbox is the riskiest component, so its defences are tested directly."""
import pytest

from app.sandbox import get_sandbox

sandbox = get_sandbox()


def run(code, stdin=""):
    return sandbox.run(code, stdin)


def test_runs_code_with_stdin():
    out = run("a = int(input())\nb = int(input())\nprint(a + b)\n", "2\n5\n")
    assert out.exit_code == 0 and out.stdout.strip() == "7" and not out.timed_out


def test_reports_the_error_type_for_runtime_errors():
    out = run("print(1 // 0)\n")
    assert out.exit_code != 0 and out.error_type == "ZeroDivisionError"
    assert "harness" not in out.stderr.lower() and "/home/" not in out.stderr  # no host paths or internals leak


def test_reports_syntax_errors():
    out = run("for i in range(3)\n    print(i)\n")
    assert out.exit_code != 0 and out.error_type == "SyntaxError"


def test_infinite_loops_are_stopped():
    out = run("while True:\n    pass\n")
    assert out.timed_out or out.error_type == "TimeLimitExceeded"


@pytest.mark.parametrize("module", ["os", "subprocess", "socket", "shutil", "ctypes", "importlib", "pathlib", "builtins", "gc", "inspect"])
def test_dangerous_imports_are_blocked(module):
    out = run(f"import {module}\nprint('imported')\n")
    assert out.exit_code != 0 and "imported" not in out.stdout


def test_dunder_import_is_blocked():
    out = run("m = __import__('os')\nprint(m.getcwd())\n")
    assert out.exit_code != 0 and "/" not in out.stdout


def test_files_cannot_be_opened():
    out = run("print(open('/etc/passwd').read())\n")
    assert out.exit_code != 0 and "root:" not in out.stdout


def test_safe_standard_library_modules_work():
    out = run("import math, heapq\nprint(math.isqrt(49), heapq.nsmallest(2, [5, 1, 3]))\n")
    assert out.exit_code == 0 and out.stdout.strip() == "7 [1, 3]"


def test_output_floods_are_capped():
    out = run("while True:\n    print('x' * 1000)\n")
    assert out.error_type == "OutputLimitExceeded" or out.timed_out
    assert len(out.stdout) <= 70_000


def test_memory_exhaustion_is_contained():
    out = run("data = 'x' * (2 * 1024 ** 3)\nprint(len(data))\n")
    assert out.exit_code != 0 and out.error_type in ("MemoryError", "ProcessKilled")


def test_runs_do_not_share_state():
    run("import collections\ncollections.leak = 'secret'\n")
    out = run("import collections\nprint(hasattr(collections, 'leak'))\n")
    assert out.stdout.strip() == "False"


def test_unicode_output_round_trips():
    out = run("print('naïve café ✓')\n")
    assert out.stdout.strip() == "naïve café ✓"


# ---------------------------------------------------------------------------- Windows behaviour (checked on the code paths that run everywhere)
def test_temp_folder_cleanup_retries_and_never_fails_a_run(monkeypatch, tmp_path):
    import shutil

    from app.sandbox import subprocess_sandbox as sb

    folder = tmp_path / "labpilot_x"
    folder.mkdir()
    (folder / "stderr.txt").write_text("x")
    real, calls = shutil.rmtree, {"n": 0}

    def locked_twice(path, *a, **k):  # what Windows does while a process or a scanner still holds a file
        calls["n"] += 1
        if calls["n"] <= 2 and not k.get("ignore_errors"):
            raise PermissionError(32, "The process cannot access the file because it is being used by another process")
        return real(path, *a, **k)

    monkeypatch.setattr(sb.shutil, "rmtree", locked_twice)
    sb._remove_tree(str(folder), delay=0)
    assert calls["n"] == 3 and not folder.exists()

    (tmp_path / "stuck").mkdir()
    monkeypatch.setattr(sb.shutil, "rmtree", lambda p, *a, **k: None if k.get("ignore_errors") else (_ for _ in ()).throw(PermissionError(32, "locked")))
    sb._remove_tree(str(tmp_path / "stuck"), attempts=3, delay=0)  # gives up quietly instead of raising


def test_on_windows_the_real_interpreter_is_used_not_the_venv_launcher(monkeypatch):
    import sys

    from app.sandbox import subprocess_sandbox as sb

    assert sb._interpreter() == sys.executable
    monkeypatch.setattr(sb, "IS_POSIX", False)
    monkeypatch.setattr(sys, "_base_executable", sys.executable, raising=False)
    assert sb._interpreter() == sys.executable
    monkeypatch.setattr(sys, "_base_executable", "/no/such/python", raising=False)
    assert sb._interpreter() == sys.executable  # falls back when the base interpreter cannot be found


def test_program_and_input_are_written_without_newline_translation(tmp_path):
    from app.sandbox import subprocess_sandbox as sb

    target = tmp_path / "student.py"
    sb._write_text(target, "print(1)\nprint(2)\n")
    assert target.read_bytes() == b"print(1)\nprint(2)\n"
