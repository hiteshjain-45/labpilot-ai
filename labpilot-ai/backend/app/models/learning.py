from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.utils.timeutil import utcnow


class MistakeRecord(Base):
    """One detected mistake category for one submission (Mistake DNA raw data)."""

    __tablename__ = "mistake_records"
    __table_args__ = (Index("ix_mistake_student_category", "student_id", "category"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"))
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"))
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(String(40))
    detail: Mapped[str] = mapped_column(String(300), default="")
    source: Mapped[str] = mapped_column(String(10), default="submit")  # run | submit
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SkillRecord(Base):
    """Current mastery (0-100) of one practical skill for one student."""

    __tablename__ = "skill_records"
    __table_args__ = (UniqueConstraint("student_id", "skill", name="uq_student_skill"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    skill: Mapped[str] = mapped_column(String(60))
    mastery: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    last_evidence_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class SkillEvidence(Base):
    """One event that moved a skill: which experiment, why, and by how much (the Skill Passport audit trail)."""

    __tablename__ = "skill_evidence"
    __table_args__ = (Index("ix_skill_evidence_student_skill", "student_id", "skill"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"))
    skill: Mapped[str] = mapped_column(String(60))
    experiment_id: Mapped[Optional[int]] = mapped_column(ForeignKey("experiments.id", ondelete="SET NULL"), nullable=True)
    source: Mapped[str] = mapped_column(String(12), default="submission")  # submission | debugging | whatif
    ratio: Mapped[float] = mapped_column(Float, default=0.0)
    before: Mapped[float] = mapped_column(Float, default=0.0)
    after: Mapped[float] = mapped_column(Float, default=0.0)
    delta: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ExperimentRecommendation(Base):
    __tablename__ = "experiment_recommendations"
    __table_args__ = (Index("ix_reco_student_created", "student_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"))
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"))
    difficulty: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text)
    signals: Mapped[dict] = mapped_column(JSON, default=dict)
    followed: Mapped[bool] = mapped_column(Boolean, default=False)
    followed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
