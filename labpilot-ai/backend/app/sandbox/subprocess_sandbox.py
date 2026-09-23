"""Default sandbox: every run happens in a fresh interpreter *process* with OS resource limits.

See docs/SECURITY.md. This is defence-in-depth for a teaching prototype, not a hardened
boundary against a determined attacker: use SANDBOX_MODE=docker (or gVisor/Firecracker in
production) when untrusted users are involved.
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from app.config import Settings
from app.sandbox.types import (
    SIGNAL_ERRORS,
    ExecutionOutcome,
    SandboxBusyError,
    SandboxError,
    parse_error_type,
)

HARNESS_PATH = Path(__file__).with_name("harness.py")
IS_POSIX = os.name == "posix"


def resource_limits_supported() -> bool:
    if not IS_POSIX:
        return False
    try:
        import resource  # noqa: F401

        return True
    except ImportError:
        return False


def _interpreter() -> str:
    """The interpreter that runs student code.

    In a Windows virtual environment `python.exe` is only a launcher that starts the real interpreter as a child
    process. Killing the launcher on a timeout would leave the child running (and still holding the run's files), so
    on Windows the real interpreter is started directly. The harness needs only the standard library, so this is safe.
    """
    if not IS_POSIX:
        base = getattr(sys, "_base_executable", None)
        if base and os.path.isfile(base):
            return base
    return sys.executable


def _remove_tree(path: str, attempts: int = 10, delay: float = 0.1) -> None:
    """Delete a run's temp folder. Windows can hold a file for a moment after its process exits (antivirus scans,
    the search indexer), so retry, and never let a cleanup problem fail the student's run."""
    for _ in range(attempts):
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except OSError:
            time.sleep(delay)
    shutil.rmtree(path, ignore_errors=True)  # a leftover folder in the OS temp directory is harmless


class _TempDir:
    def __init__(self, prefix: str):
        self.path = tempfile.mkdtemp(prefix=prefix)

    def __enter__(self) -> str:
        return self.path

    def __exit__(self, *_exc) -> None:
        _remove_tree(self.path)


def _write_text(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as handle:  # no CRLF translation on Windows
        handle.write(text)


def _read_capped(path: Path, limit: int) -> tuple[str, bool]:
    with open(path, "rb") as handle:
        data = handle.read(limit * 4 + 1)
    text = data.decode("utf-8", errors="replace")
    return (text[:limit], True) if len(text) > limit else (text, False)


class SubprocessSandbox:
    name = "subprocess"

    def __init__(self, settings: Settings):
        self.settings = settings
        self._slots = threading.BoundedSemaphore(max(1, settings.sandbox_max_concurrent))

    def describe(self) -> dict:
        return {
            "mode": self.name,
            "resource_limits": resource_limits_supported(),
            "network_isolation": "audit-hook and import blocking inside the interpreter; no OS-level isolation (use docker mode)",
            "timeout_seconds": self.settings.sandbox_timeout_seconds,
            "memory_mb": self.settings.sandbox_memory_mb,
        }

    def run(self, code: str, stdin: str = "", timeout: float | None = None) -> ExecutionOutcome:
        timeout = timeout or self.settings.sandbox_timeout_seconds
        if not self._slots.acquire(timeout=30):
            raise SandboxBusyError("The execution service is busy, please retry shortly")
        try:
            return self._run(code, stdin, timeout)
        finally:
            self._slots.release()

    def _run(self, code: str, stdin: str, timeout: float) -> ExecutionOutcome:
        limit = self.settings.sandbox_max_output_chars
        cfg = {
            "memory_mb": self.settings.sandbox_memory_mb,
            "cpu_seconds": int(timeout) + 1,
            "max_output_chars": limit,
        }
        with _TempDir(prefix="labpilot_") as tmp:
            tmp_path = Path(tmp)
            code_file, in_file = tmp_path / "student.py", tmp_path / "stdin.txt"
            out_file, err_file = tmp_path / "stdout.txt", tmp_path / "stderr.txt"
            _write_text(code_file, code)
            _write_text(in_file, stdin)

            env = {"PYTHONIOENCODING": "utf-8", "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1"}
            if not IS_POSIX and os.environ.get("SYSTEMROOT"):
                env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]  # required for Python to start on Windows

            cmd = [_interpreter(), "-I", "-S", str(HARNESS_PATH), str(code_file), json.dumps(cfg)]
            kwargs: dict = {"cwd": tmp, "env": env, "close_fds": True}
            if IS_POSIX:
                kwargs["start_new_session"] = True
            else:  # pragma: no cover
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

            timed_out = False
            started = time.perf_counter()
            try:
                with open(in_file, "rb") as fin, open(out_file, "wb") as fout, open(err_file, "wb") as ferr:
                    proc = subprocess.Popen(cmd, stdin=fin, stdout=fout, stderr=ferr, **kwargs)
                    try:
                        proc.wait(timeout=timeout)
                    except subprocess.TimeoutExpired:
                        timed_out = True
                        self._kill(proc)
            except OSError as exc:
                raise SandboxError(f"Could not start the sandbox process: {exc}") from exc
            runtime_ms = int((time.perf_counter() - started) * 1000)

            stdout, truncated = _read_capped(out_file, limit)
            stderr, _ = _read_capped(err_file, 8000)
            exit_code = proc.returncode if proc.returncode is not None else -1

        error_type = parse_error_type(stderr)
        if exit_code < 0 and not error_type:
            error_type = SIGNAL_ERRORS.get(-exit_code, f"Signal{-exit_code}")
        if exit_code == -signal.SIGXCPU if IS_POSIX else False:
            timed_out = True
        if timed_out:
            error_type = "TimeLimitExceeded"
        return ExecutionOutcome(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            timed_out=timed_out,
            runtime_ms=runtime_ms,
            error_type=error_type,
            output_truncated=truncated,
        )

    @staticmethod
    def _kill(proc: subprocess.Popen) -> None:
        try:
            if IS_POSIX:
                os.killpg(proc.pid, signal.SIGKILL)
            else:  # pragma: no cover - Windows: end the whole process tree, not just the direct child
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, timeout=10, check=False)
                proc.kill()
        except (ProcessLookupError, PermissionError, OSError, subprocess.SubprocessError):
            pass
        proc.wait()
