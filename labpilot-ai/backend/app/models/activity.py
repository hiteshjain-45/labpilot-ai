from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:  # relationship targets referenced as strings
    from app.models.user import Teacher
from app.utils.timeutil import utcnow


class Attempt(Base):
    """One sitting on an experiment: any number of runs, closed by a graded submission."""

    __tablename__ = "attempts"
    __table_args__ = (
        UniqueConstraint("student_id", "experiment_id", "attempt_number", name="uq_attempt_number"),
        Index("ix_attempt_student_experiment", "student_id", "experiment_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"))
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"))
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="in_progress")  # in_progress | submitted
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_score: Mapped[int] = mapped_column(Integer, default=100)
    run_count: Mapped[int] = mapped_column(Integer, default=0)
    hints_used: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Submission(Base):
    """A code execution stored for history: kind 'run' (visible tests) or 'submit' (graded)."""

    __tablename__ = "submissions"
    __table_args__ = (Index("ix_submission_student_created", "student_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("attempts.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"))
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10), default="run")
    code: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="failed")  # passed | partial | failed
    passed_count: Mapped[int] = mapped_column(Integer, default=0)
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    max_score: Mapped[int] = mapped_column(Integer, default=100)
    runtime_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    review: Mapped[Optional["SubmissionReview"]] = relationship(back_populates="submission", cascade="all, delete-orphan", uselist=False, lazy="joined")
    results: Mapped[list["ExecutionResult"]] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ExecutionResult.id",
    )
    attempt: Mapped[Attempt] = relationship()


class SubmissionReview(Base):
    """A teacher's remark and sign-off on one graded submission, the way a lab record is signed.

    Automatic grading is untouched: a review never changes the score. One review per submission; a teacher
    editing their remark updates the same row.
    """

    __tablename__ = "submission_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), unique=True, index=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16))          # approved | needs_rework
    remark: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    submission: Mapped["Submission"] = relationship(back_populates="review")
    teacher: Mapped["Teacher"] = relationship(lazy="joined")


class ExecutionResult(Base):
    """Outcome of one test case for one submission (values are snapshots)."""

    __tablename__ = "execution_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), index=True)
    test_case_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("experiment_test_cases.id", ondelete="SET NULL"), nullable=True
    )
    test_name: Mapped[str] = mapped_column(String(120))
    test_kind: Mapped[str] = mapped_column(String(20), default="normal")
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20))  # passed|wrong_answer|runtime_error|syntax_error|timeout|output_limit
    stdin: Mapped[str] = mapped_column(Text, default="")
    expected_output: Mapped[str] = mapped_column(Text, default="")
    actual_output: Mapped[str] = mapped_column(Text, default="")
    stderr: Mapped[str] = mapped_column(Text, default="")
    error_type: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    runtime_ms: Mapped[int] = mapped_column(Integer, default=0)
    timed_out: Mapped[bool] = mapped_column(Boolean, default=False)

    submission: Mapped[Submission] = relationship(back_populates="results")
