"""SQLAlchemy ORM models: Problem -> Attempt -> Evaluation."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Problem(Base):
    __tablename__ = "problems"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # Stored as newline-separated bullet text so a future "rich" format
    # (e.g. JSON list) only needs a serializer change, not a schema change.
    requirements: Mapped[str] = mapped_column(Text, nullable=False)
    constraints: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    attempts: Mapped[list["Attempt"]] = relationship(back_populates="problem")


class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id"), nullable=False, index=True)
    submission_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Lifecycle: submitted -> evaluating -> completed | failed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="submitted")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    problem: Mapped["Problem"] = relationship(back_populates="attempts")
    evaluation: Mapped["Evaluation | None"] = relationship(
        back_populates="attempt", uselist=False, cascade="all, delete-orphan"
    )


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("attempts.id"), unique=True, nullable=False)
    overall_score: Mapped[int] = mapped_column(Integer, nullable=False)

    requirement_understanding_score: Mapped[int] = mapped_column(Integer, nullable=False)
    requirement_understanding_evidence: Mapped[str] = mapped_column(Text, default="")
    requirement_understanding_concern: Mapped[str] = mapped_column(Text, default="")
    requirement_understanding_suggestion: Mapped[str] = mapped_column(Text, default="")

    class_responsibilities_score: Mapped[int] = mapped_column(Integer, nullable=False)
    class_responsibilities_evidence: Mapped[str] = mapped_column(Text, default="")
    class_responsibilities_concern: Mapped[str] = mapped_column(Text, default="")
    class_responsibilities_suggestion: Mapped[str] = mapped_column(Text, default="")

    coupling_cohesion_score: Mapped[int] = mapped_column(Integer, nullable=False)
    coupling_cohesion_evidence: Mapped[str] = mapped_column(Text, default="")
    coupling_cohesion_concern: Mapped[str] = mapped_column(Text, default="")
    coupling_cohesion_suggestion: Mapped[str] = mapped_column(Text, default="")

    abstraction_score: Mapped[int] = mapped_column(Integer, nullable=False)
    abstraction_evidence: Mapped[str] = mapped_column(Text, default="")
    abstraction_concern: Mapped[str] = mapped_column(Text, default="")
    abstraction_suggestion: Mapped[str] = mapped_column(Text, default="")

    extensibility_score: Mapped[int] = mapped_column(Integer, nullable=False)
    extensibility_evidence: Mapped[str] = mapped_column(Text, default="")
    extensibility_concern: Mapped[str] = mapped_column(Text, default="")
    extensibility_suggestion: Mapped[str] = mapped_column(Text, default="")

    edge_cases_score: Mapped[int] = mapped_column(Integer, nullable=False)
    edge_cases_evidence: Mapped[str] = mapped_column(Text, default="")
    edge_cases_concern: Mapped[str] = mapped_column(Text, default="")
    edge_cases_suggestion: Mapped[str] = mapped_column(Text, default="")

    explanation_quality_score: Mapped[int] = mapped_column(Integer, nullable=False)
    explanation_quality_evidence: Mapped[str] = mapped_column(Text, default="")
    explanation_quality_concern: Mapped[str] = mapped_column(Text, default="")
    explanation_quality_suggestion: Mapped[str] = mapped_column(Text, default="")

    # JSON arrays stored as strings: SQLite has no native array type and the
    # lists are only ever read back whole, never queried by element.
    top_strengths: Mapped[str] = mapped_column(Text, default="[]")
    top_improvements: Mapped[str] = mapped_column(Text, default="[]")
    summary: Mapped[str] = mapped_column(Text, default="")
    # Kept verbatim so we can re-parse if the rubric/parser changes later.
    raw_ai_response: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    attempt: Mapped["Attempt"] = relationship(back_populates="evaluation")
