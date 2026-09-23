"""Request models for experiment and test-case management (teacher side)."""
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.constants import CATEGORIES, DIFFICULTIES, SKILLS, TEST_KINDS


class TestCaseIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    stdin: str = Field(default="", max_length=50_000)
    expected_output: str = Field(default="", max_length=50_000)
    kind: str = "normal"
    is_hidden: bool = False
    weight: int = Field(default=1, ge=1, le=10)

    @field_validator("kind")
    @classmethod
    def _kind(cls, v: str) -> str:
        if v not in TEST_KINDS:
            raise ValueError(f"kind must be one of {', '.join(TEST_KINDS)}")
        return v


class WhatIfScenarioIn(BaseModel):
    id: str = Field(min_length=1, max_length=60, pattern=r"^[a-z0-9_-]+$")
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=600)
    modified_code: str = Field(min_length=1, max_length=10_000)
    stdin: str = Field(default="", max_length=2000)
    explanation: str = Field(default="", max_length=1200)


class ExperimentBase(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    objective: str = Field(default="", max_length=1500)
    problem_statement: str = Field(default="", max_length=6000)
    instructions: str = Field(default="", max_length=6000)
    starter_code: str = Field(default="", max_length=10_000)
    reference_solution: str = Field(default="", max_length=10_000)
    difficulty: str = "beginner"
    skills: list[str] = Field(default_factory=list)
    focus_categories: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list, max_length=10)
    hints: list[str] = Field(default_factory=list, max_length=5)
    what_if_scenarios: list[WhatIfScenarioIn] = Field(default_factory=list, max_length=5)
    max_score: int = Field(default=100, ge=1, le=1000)
    estimated_minutes: int = Field(default=20, ge=1, le=600)
    is_published: bool = True
    position: int = Field(default=0, ge=0, le=10_000)

    @field_validator("difficulty")
    @classmethod
    def _difficulty(cls, v: str) -> str:
        if v not in DIFFICULTIES:
            raise ValueError(f"difficulty must be one of {', '.join(DIFFICULTIES)}")
        return v

    @field_validator("skills")
    @classmethod
    def _skills(cls, v: list[str]) -> list[str]:
        unknown = [s for s in v if s not in SKILLS]
        if unknown:
            raise ValueError(f"Unknown skill(s): {', '.join(unknown)}")
        return list(dict.fromkeys(v))

    @field_validator("focus_categories")
    @classmethod
    def _categories(cls, v: list[str]) -> list[str]:
        unknown = [c for c in v if c not in CATEGORIES]
        if unknown:
            raise ValueError(f"Unknown mistake categories: {', '.join(unknown)}")
        return list(dict.fromkeys(v))

    @field_validator("concepts", "hints")
    @classmethod
    def _strip(cls, v: list[str]) -> list[str]:
        return [x.strip()[:400] for x in v if x and x.strip()]

    @model_validator(mode="after")
    def _unique_scenarios(self):
        ids = [s.id for s in self.what_if_scenarios]
        if len(ids) != len(set(ids)):
            raise ValueError("What-if scenario ids must be unique")
        return self


class ExperimentCreate(ExperimentBase):
    test_cases: list[TestCaseIn] = Field(default_factory=list, max_length=30)


class ExperimentUpdate(BaseModel):
    """Partial update: only supplied fields change."""

    title: Optional[str] = Field(default=None, min_length=3, max_length=200)
    objective: Optional[str] = Field(default=None, max_length=1500)
    problem_statement: Optional[str] = Field(default=None, max_length=6000)
    instructions: Optional[str] = Field(default=None, max_length=6000)
    starter_code: Optional[str] = Field(default=None, max_length=10_000)
    reference_solution: Optional[str] = Field(default=None, max_length=10_000)
    difficulty: Optional[str] = None
    skills: Optional[list[str]] = None
    focus_categories: Optional[list[str]] = None
    concepts: Optional[list[str]] = None
    hints: Optional[list[str]] = None
    what_if_scenarios: Optional[list[WhatIfScenarioIn]] = None
    max_score: Optional[int] = Field(default=None, ge=1, le=1000)
    estimated_minutes: Optional[int] = Field(default=None, ge=1, le=600)
    is_published: Optional[bool] = None
    position: Optional[int] = Field(default=None, ge=0, le=10_000)

    # Reuse the validation rules of the create model.
    _difficulty = field_validator("difficulty")(ExperimentBase._difficulty.__func__)  # type: ignore[attr-defined]
    _skills = field_validator("skills")(ExperimentBase._skills.__func__)  # type: ignore[attr-defined]
    _categories = field_validator("focus_categories")(ExperimentBase._categories.__func__)  # type: ignore[attr-defined]
    _strip = field_validator("concepts", "hints")(ExperimentBase._strip.__func__)  # type: ignore[attr-defined]


class TestCaseUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    stdin: Optional[str] = Field(default=None, max_length=50_000)
    expected_output: Optional[str] = Field(default=None, max_length=50_000)
    kind: Optional[str] = None
    is_hidden: Optional[bool] = None
    weight: Optional[int] = Field(default=None, ge=1, le=10)

    _kind = field_validator("kind")(TestCaseIn._kind.__func__)  # type: ignore[attr-defined]
