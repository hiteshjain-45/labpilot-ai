"""Provider-neutral AI interface.

The application never talks to a vendor SDK directly: services build an `AIRequest` and call
`provider.generate()`. To add a provider, subclass `AIProvider` and register it in
`app/ai/factory.py`.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class AIRequest:
    task: str  # "copilot_hint" | "whatif_explanation"
    system_prompt: str
    user_prompt: str
    context: dict = field(default_factory=dict)  # structured form of the prompt (used by the rule-based provider)
    max_tokens: int = 700


class AIProviderError(RuntimeError):
    """Raised when a provider call fails (network, auth, malformed response...)."""


class AIProvider(ABC):
    name = "base"
    label = "Base provider"
    is_real = True  # False for the rule-based development fallback
    model = ""

    @abstractmethod
    def generate(self, request: AIRequest) -> str:
        """Return the raw model text (the callers ask for a JSON object)."""

    def describe(self) -> dict:
        return {"provider": self.name, "label": self.label, "is_real": self.is_real, "model": self.model}
