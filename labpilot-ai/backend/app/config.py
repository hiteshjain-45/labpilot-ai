"""Application settings, read from environment variables (and an optional .env file)."""
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent

# Values already present in the real environment always win over .env files.
load_dotenv(PROJECT_DIR / ".env")
load_dotenv(BACKEND_DIR / ".env")

DEFAULT_SECRET = "dev-insecure-secret-change-me-before-deploying"


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    environment: str = "development"
    database_url: str = f"sqlite:///{BACKEND_DIR / 'labpilot.db'}"
    secret_key: str = DEFAULT_SECRET
    access_token_minutes: int = 480
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"])

    # AI
    ai_provider: str = "auto"  # auto | mock | anthropic | openai
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"
    anthropic_base_url: str = "https://api.anthropic.com"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    ai_timeout_seconds: float = 20.0

    # Sandbox
    sandbox_mode: str = "subprocess"  # subprocess | docker
    sandbox_timeout_seconds: float = 3.0
    sandbox_memory_mb: int = 256
    sandbox_max_output_chars: int = 64_000
    sandbox_max_concurrent: int = 4
    sandbox_docker_image: str = "python:3.12-slim"
    max_code_chars: int = 20_000

    # Rate limits
    login_max_failures: int = 5
    login_window_seconds: int = 300
    exec_max_per_minute: int = 60


def validate_settings(settings: Settings) -> None:
    """Refuse to start a production deployment with a guessable signing key."""
    if settings.environment.lower() in ("production", "prod") and (settings.secret_key == DEFAULT_SECRET or len(settings.secret_key) < 32):
        raise RuntimeError(
            "SECRET_KEY must be a random string of at least 32 characters when APP_ENV=production. "
            'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(48))"'
        )


@lru_cache
def get_settings() -> Settings:
    origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
    defaults = Settings()
    return Settings(
        environment=os.getenv("APP_ENV", defaults.environment),
        database_url=os.getenv("DATABASE_URL", defaults.database_url),
        secret_key=os.getenv("SECRET_KEY", defaults.secret_key),
        access_token_minutes=_int("ACCESS_TOKEN_MINUTES", defaults.access_token_minutes),
        cors_origins=origins or defaults.cors_origins,
        ai_provider=os.getenv("AI_PROVIDER", defaults.ai_provider).lower(),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        anthropic_model=os.getenv("ANTHROPIC_MODEL", defaults.anthropic_model),
        anthropic_base_url=os.getenv("ANTHROPIC_BASE_URL", defaults.anthropic_base_url).rstrip("/"),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_model=os.getenv("OPENAI_MODEL", defaults.openai_model),
        openai_base_url=os.getenv("OPENAI_BASE_URL", defaults.openai_base_url).rstrip("/"),
        ai_timeout_seconds=_float("AI_TIMEOUT_SECONDS", defaults.ai_timeout_seconds),
        sandbox_mode=os.getenv("SANDBOX_MODE", defaults.sandbox_mode).lower(),
        sandbox_timeout_seconds=_float("SANDBOX_TIMEOUT_SECONDS", defaults.sandbox_timeout_seconds),
        sandbox_memory_mb=_int("SANDBOX_MEMORY_MB", defaults.sandbox_memory_mb),
        sandbox_max_output_chars=_int("SANDBOX_MAX_OUTPUT_CHARS", defaults.sandbox_max_output_chars),
        sandbox_max_concurrent=_int("SANDBOX_MAX_CONCURRENT", defaults.sandbox_max_concurrent),
        sandbox_docker_image=os.getenv("SANDBOX_DOCKER_IMAGE", defaults.sandbox_docker_image),
        max_code_chars=_int("MAX_CODE_CHARS", defaults.max_code_chars),
        login_max_failures=_int("LOGIN_MAX_FAILURES", defaults.login_max_failures),
        login_window_seconds=_int("LOGIN_WINDOW_SECONDS", defaults.login_window_seconds),
        exec_max_per_minute=_int("EXEC_MAX_PER_MINUTE", defaults.exec_max_per_minute),
    )
