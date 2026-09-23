from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.timeutil import utcnow


class Experiment(Base):
    """A programming experiment. Programs read stdin and write stdout; test cases compare stdout."""

    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    objective: Mapped[str] = mapped_column(Text, default="")
    problem_statement: Mapped[str] = mapped_column(Text, default="")
    instructions: Mapped[str] = mapped_column(Text, default="")
    starter_code: Mapped[str] = mapped_column(Text, default="")
    reference_solution: Mapped[str] = mapped_column(Text, default="")  # teacher-only
    difficulty: Mapped[str] = mapped_column(String(20), default="beginner", index=True)

    skills: Mapped[list] = mapped_column(JSON, default=list)  # names from core.constants.SKILLS
    focus_categories: Mapped[list] = mapped_column(JSON, default=list)  # mistake categories practised
    concepts: Mapped[list] = mapped_column(JSON, default=list)  # concepts to review
    hints: Mapped[list] = mapped_column(JSON, default=list)  # teacher-authored progressive hints
    what_if_scenarios: Mapped[list] = mapped_column(JSON, default=list)

    max_score: Mapped[int] = mapped_column(Integer, default=100)
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=20)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    test_cases: Mapped[list["ExperimentTestCase"]] = relationship(
        back_populates="experiment",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ExperimentTestCase.position, ExperimentTestCase.id",
    )


class ExperimentTestCase(Base):
    __tablename__ = "experiment_test_cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    stdin: Mapped[str] = mapped_column(Text, default="")
    expected_output: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(20), default="normal")  # normal | edge | performance
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    weight: Mapped[int] = mapped_column(Integer, default=1)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    experiment: Mapped[Experiment] = relationship(back_populates="test_cases")
