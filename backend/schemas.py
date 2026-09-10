"""Pydantic request/response schemas."""

import json
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProblemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    requirements: str
    constraints: str


class AttemptCreate(BaseModel):
    problem_id: int
    submission_text: str = Field(..., min_length=1)

    @field_validator("submission_text")
    @classmethod
    def not_blank(cls, value: str) -> str:
        # min_length catches "", this catches whitespace-only submissions.
        if not value.strip():
            raise ValueError("submission_text must not be empty")
        return value


class AttemptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    problem_id: int
    submission_text: str
    status: str
    created_at: datetime


class DimensionFeedback(BaseModel):
    """One rubric dimension, re-nested from the flat DB columns for the UI."""

    score: int
    max_score: int
    evidence: str
    concern: str
    suggestion: str


class EvaluationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    attempt_id: int
    overall_score: int

    requirement_understanding_score: int
    requirement_understanding_evidence: str
    requirement_understanding_concern: str
    requirement_understanding_suggestion: str

    class_responsibilities_score: int
    class_responsibilities_evidence: str
    class_responsibilities_concern: str
    class_responsibilities_suggestion: str

    coupling_cohesion_score: int
    coupling_cohesion_evidence: str
    coupling_cohesion_concern: str
    coupling_cohesion_suggestion: str

    abstraction_score: int
    abstraction_evidence: str
    abstraction_concern: str
    abstraction_suggestion: str

    extensibility_score: int
    extensibility_evidence: str
    extensibility_concern: str
    extensibility_suggestion: str

    edge_cases_score: int
    edge_cases_evidence: str
    edge_cases_concern: str
    edge_cases_suggestion: str

    explanation_quality_score: int
    explanation_quality_evidence: str
    explanation_quality_concern: str
    explanation_quality_suggestion: str

    top_strengths: list[str]
    top_improvements: list[str]
    summary: str
    created_at: datetime

    @field_validator("top_strengths", "top_improvements", mode="before")
    @classmethod
    def parse_json_list(cls, value):
        # DB stores these as JSON strings; the API returns real arrays.
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                return []
        return value or []


class AttemptWithEvaluation(AttemptResponse):
    evaluation: Optional[EvaluationResponse] = None


class SubmitResponse(BaseModel):
    attempt_id: int
    status: str
    message: str
