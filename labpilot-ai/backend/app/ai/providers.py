"""Concrete providers. Real providers use plain HTTPS via httpx (no vendor SDK dependency)."""
import json

import httpx

from app.ai.base import AIProvider, AIProviderError, AIRequest


class AnthropicProvider(AIProvider):
    name = "anthropic"
    is_real = True

    def __init__(self, api_key: str, model: str, base_url: str = "https://api.anthropic.com",
                 timeout: float = 20.0, transport: httpx.BaseTransport | None = None):
        self.api_key, self.model, self.base_url, self.timeout = api_key, model, base_url.rstrip("/"), timeout
        self.label = f"Anthropic ({model})"
        self._transport = transport

    def generate(self, request: AIRequest) -> str:
        payload = {
            "model": self.model,
            "max_tokens": request.max_tokens,
            "system": request.system_prompt,
            "messages": [{"role": "user", "content": request.user_prompt}],
        }
        headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        try:
            with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
                resp = client.post(f"{self.base_url}/v1/messages", headers=headers, json=payload)
            resp.raise_for_status()
            blocks = resp.json().get("content", [])
            text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        except (httpx.HTTPError, ValueError, KeyError, AttributeError) as exc:
            raise AIProviderError(f"Anthropic request failed: {exc.__class__.__name__}") from exc
        if not text.strip():
            raise AIProviderError("Anthropic returned an empty response")
        return text


class OpenAICompatibleProvider(AIProvider):
    """Works with OpenAI and any server exposing /chat/completions (Ollama, vLLM, LM Studio...)."""

    name = "openai"
    is_real = True

    def __init__(self, api_key: str, model: str, base_url: str = "https://api.openai.com/v1",
                 timeout: float = 20.0, transport: httpx.BaseTransport | None = None):
        self.api_key, self.model, self.base_url, self.timeout = api_key, model, base_url.rstrip("/"), timeout
        self.label = f"OpenAI-compatible ({model})"
        self._transport = transport

    def generate(self, request: AIRequest) -> str:
        payload = {
            "model": self.model,
            "max_tokens": request.max_tokens,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
        }
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        try:
            with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
                resp = client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"] or ""
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise AIProviderError(f"OpenAI-compatible request failed: {exc.__class__.__name__}") from exc
        if not text.strip():
            raise AIProviderError("The provider returned an empty response")
        return text


class MockProvider(AIProvider):
    """Rule-based development fallback. It is NOT an LLM and is always labelled as such in the UI.

    It turns the structured context (deterministic error category, failing tests, the teacher's
    hint ladder) into templated guidance, so the Copilot remains useful with no API key.
    """

    name = "mock"
    label = "Rule-based mode (no AI provider configured)"
    is_real = False
    model = "rules-v1"

    def generate(self, request: AIRequest) -> str:
        if request.task == "copilot_hint":
            from app.ai.rules import build_rule_based_guidance

            return json.dumps(build_rule_based_guidance(request.context))
        raise AIProviderError(f"The rule-based provider cannot handle task '{request.task}'")
