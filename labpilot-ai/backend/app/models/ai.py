from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.utils.timeutil import utcnow


class AIInteraction(Base):
    """Audit log of every AI call: what context was sent and what came back."""

    __tablename__ = "ai_interactions"
    __table_args__ = (Index("ix_ai_student_experiment", "student_id", "experiment_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"))
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"))
    submission_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("submissions.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(30), default="hint")  # hint | whatif_explanation | chat
    hint_level: Mapped[int] = mapped_column(Integer, default=1)
    request_context: Mapped[dict] = mapped_column(JSON, default=dict)
    response: Mapped[dict] = mapped_column(JSON, default=dict)
    provider: Mapped[str] = mapped_column(String(40), default="mock")
    is_fallback: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class WhatIfPrediction(Base):
    __tablename__ = "what_if_predictions"
    __table_args__ = (Index("ix_whatif_student_experiment", "student_id", "experiment_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"))
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"))
    scenario_id: Mapped[str] = mapped_column(String(60))
    scenario_title: Mapped[str] = mapped_column(String(200))
    modified_code: Mapped[str] = mapped_column(Text)
    stdin: Mapped[str] = mapped_column(Text, default="")
    prediction: Mapped[str] = mapped_column(Text)
    actual_output: Mapped[str] = mapped_column(Text, default="")
    matched: Mapped[bool] = mapped_column(Boolean, default=False)
    explanation: Mapped[str] = mapped_column(Text, default="")
    ai_provider: Mapped[str] = mapped_column(String(40), default="rule-based")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
