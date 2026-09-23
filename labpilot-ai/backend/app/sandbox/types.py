import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ExecutionOutcome:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    timed_out: bool = False
    runtime_ms: int = 0
    error_type: Optional[str] = None
    output_truncated: bool = False


class SandboxError(RuntimeError):
    """The sandbox itself failed (not the student's program)."""


class SandboxBusyError(SandboxError):
    """Too many concurrent executions."""


_ERROR_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_.]*)(?::|$)")
_ERROR_SUFFIXES = ("Error", "Exception", "Exit", "Interrupt", "Exceeded", "Warning")

# Signals reported as negative exit codes by subprocess on POSIX.
SIGNAL_ERRORS = {
    9: "ProcessKilled",  # SIGKILL - usually the kernel or the memory limit
    11: "SegmentationFault",
    24: "TimeLimitExceeded",  # SIGXCPU - CPU limit reached
    25: "OutputLimitExceeded",  # SIGXFSZ - file size limit reached
}


def parse_error_type(stderr: str) -> Optional[str]:
    """Extract the exception class name from the tail of a Python traceback."""
    for line in reversed([ln.strip() for ln in stderr.strip().splitlines()][-6:]):
        match = _ERROR_LINE.match(line)
        if match and match.group(1).split(".")[-1].endswith(_ERROR_SUFFIXES):
            return match.group(1).split(".")[-1]
    return None
