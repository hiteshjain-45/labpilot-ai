import logging

from app.ai.base import AIProvider
from app.ai.providers import AnthropicProvider, MockProvider, OpenAICompatibleProvider
from app.config import Settings, get_settings

log = logging.getLogger("labpilot.ai")


def get_provider(settings: Settings | None = None) -> AIProvider:
    """AI_PROVIDER=auto picks Anthropic, then OpenAI-compatible, then the rule-based fallback."""
    s = settings or get_settings()
    choice = s.ai_provider
    if choice == "auto":
        choice = "anthropic" if s.anthropic_api_key else "openai" if s.openai_api_key else "mock"
    if choice == "anthropic":
        if s.anthropic_api_key:
            return AnthropicProvider(s.anthropic_api_key, s.anthropic_model, s.anthropic_base_url, s.ai_timeout_seconds)
        log.warning("AI_PROVIDER=anthropic but ANTHROPIC_API_KEY is empty; using the rule-based fallback")
    elif choice == "openai":
        # A key is optional for local OpenAI-compatible servers, but a custom base URL is then required.
        if s.openai_api_key or "api.openai.com" not in s.openai_base_url:
            return OpenAICompatibleProvider(s.openai_api_key, s.openai_model, s.openai_base_url, s.ai_timeout_seconds)
        log.warning("AI_PROVIDER=openai but OPENAI_API_KEY is empty; using the rule-based fallback")
    return MockProvider()
