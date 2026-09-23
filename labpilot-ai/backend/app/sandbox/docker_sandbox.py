"""Optional stronger isolation: run each execution in a throw-away Docker container.

Enabled with SANDBOX_MODE=docker. Container flags: no network, read-only root filesystem,
all capabilities dropped, memory/CPU/pids limits, unprivileged user, code mounted read-only.

NOTE: this backend was written for the prototype but has not been exercised in the
development environment used to build it (no Docker daemon available). Treat it as
experimental until you have run the sandbox tests with Docker on your machine.
"""
import json
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

from app.config import Settings
from app.sandbox.subprocess_sandbox import HARNESS_PATH, _read_capped
from app.sandbox.types import (
    SIGNAL_ERRORS,
    ExecutionOutcome,
    SandboxBusyError,
    SandboxError,
    parse_error_type,
)


class DockerSandbox:
    name = "docker"

    def __init__(self, settings: Settings):
        self.settings = settings
        self._slots = threading.BoundedSemaphore(max(1, settings.sandbox_max_concurrent))

    def describe(self) -> dict:
        return {
            "mode": self.name,
            "resource_limits": True,
            "network_isolation": "docker --network none",
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
        s = self.settings
        name = f"labpilot-{uuid.uuid4().hex[:12]}"
        cfg = {"memory_mb": s.sandbox_memory_mb, "cpu_seconds": int(timeout) + 1, "max_output_chars": s.sandbox_max_output_chars}
        with tempfile.TemporaryDirectory(prefix="labpilot_") as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "student.py").write_text(code, encoding="utf-8")
            (tmp_path / "harness.py").write_text(HARNESS_PATH.read_text(encoding="utf-8"), encoding="utf-8")
            in_file, out_file, err_file = tmp_path / "stdin.txt", tmp_path / "stdout.txt", tmp_path / "stderr.txt"
            in_file.write_text(stdin, encoding="utf-8")
            cmd = [
                "docker", "run", "--rm", "-i", "--name", name,
                "--network", "none",
                "--memory", f"{s.sandbox_memory_mb + 64}m", "--memory-swap", f"{s.sandbox_memory_mb + 64}m",
                "--cpus", "0.5", "--pids-limit", "32",
                "--read-only", "--tmpfs", "/tmp:size=8m,noexec",
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                "--user", "65534:65534",
                "-v", f"{tmp}:/sandbox:ro",
                s.sandbox_docker_image,
                "python", "-I", "-S", "/sandbox/harness.py", "/sandbox/student.py", json.dumps(cfg),
            ]
            timed_out = False
            started = time.perf_counter()
            try:
                with open(in_file, "rb") as fin, open(out_file, "wb") as fout, open(err_file, "wb") as ferr:
                    proc = subprocess.Popen(cmd, stdin=fin, stdout=fout, stderr=ferr)
                    try:
                        # Container start-up is slower than a bare interpreter: allow a grace period.
                        proc.wait(timeout=timeout + 5)
                    except subprocess.TimeoutExpired:
                        timed_out = True
                        subprocess.run(["docker", "kill", name], capture_output=True, timeout=10)
                        proc.wait()
            except FileNotFoundError as exc:
                raise SandboxError("Docker is not installed or not on PATH") from exc
            runtime_ms = int((time.perf_counter() - started) * 1000)
            stdout, truncated = _read_capped(out_file, s.sandbox_max_output_chars)
            stderr, _ = _read_capped(err_file, 8000)
            exit_code = proc.returncode if proc.returncode is not None else -1

        if exit_code == 125:  # docker itself failed (image missing, daemon down, ...)
            raise SandboxError(f"Docker could not start the container: {stderr.strip()[:300]}")
        error_type = parse_error_type(stderr)
        if exit_code == 137 and not timed_out:
            error_type = error_type or "MemoryLimitExceeded"
        elif exit_code < 0 and not error_type:
            error_type = SIGNAL_ERRORS.get(-exit_code, f"Signal{-exit_code}")
        if timed_out or exit_code == 152:  # 128 + SIGXCPU
            timed_out, error_type = True, "TimeLimitExceeded"
        return ExecutionOutcome(stdout, stderr, exit_code, timed_out, runtime_ms, error_type, truncated)
