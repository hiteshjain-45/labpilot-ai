"""Request models for code execution, the Copilot and What-If."""
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class CodeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=40_000)


class HintRequest(BaseModel):
    code: str = Field(min_length=1, max_length=40_000)
    question: Optional[str] = Field(default=None, max_length=500)
    console_output: Optional[str] = Field(default=None, max_length=4000)


class ChatRequest(BaseModel):
    """A message to the AI Copilot chat: a quick action, a typed question, or both."""

    experiment_id: int
    action: Optional[Literal["explain_error", "hint", "explain_concept", "similar_problem", "check_attempt"]] = None
    message: Optional[str] = Field(default=None, max_length=500)
    code: Optional[str] = Field(default=None, max_length=40_000)
    console_output: Optional[str] = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def _needs_something_to_answer(self):
        if not self.action and not (self.message and self.message.strip()):
            raise ValueError("Choose a quick action or type a question")
        return self


class WhatIfExploreRequest(BaseModel):
    """Explore a hypothetical condition: no prediction, nothing stored."""

    condition_id: str = Field(min_length=1, max_length=40)
    option: str = Field(min_length=1, max_length=40)
    code: Optional[str] = Field(default=None, max_length=40_000)


class WhatIfRequest(BaseModel):
    scenario_id: str = Field(min_length=1, max_length=60)
    prediction: str = Field(min_length=1, max_length=2000)
    stdin: Optional[str] = Field(default=None, max_length=2000)
