from functools import lru_cache

from app.config import get_settings
from app.sandbox.types import ExecutionOutcome, SandboxBusyError, SandboxError


@lru_cache
def get_sandbox():
    """Return the configured sandbox (SANDBOX_MODE=subprocess|docker)."""
    settings = get_settings()
    if settings.sandbox_mode == "docker":
        from app.sandbox.docker_sandbox import DockerSandbox

        return DockerSandbox(settings)
    from app.sandbox.subprocess_sandbox import SubprocessSandbox

    return SubprocessSandbox(settings)


__all__ = ["ExecutionOutcome", "SandboxBusyError", "SandboxError", "get_sandbox"]
