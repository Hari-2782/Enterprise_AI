from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class CreateReviewRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2048)
    proposed_answer: str = Field(min_length=1, max_length=16000)
    abstention_reason: str | None = Field(default=None, max_length=1000)
    escalate: bool = False


class ResolveReviewRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    notes: str | None = Field(default=None, max_length=2000)


class ReviewTaskResponse(BaseModel):
    id: UUID
    request_id: str | None = None
    user_id: UUID | None = None
    query: str
    proposed_answer: str
    abstention_reason: str | None = None
    status: str
    reviewer_id: UUID | None = None
    reviewer_notes: str | None = None
    resolved_at: datetime | None = None
    created_at: datetime


class CreateFeedbackRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2048)
    rating: Literal["positive", "negative"]
    comment: str | None = Field(default=None, max_length=2000)


class FeedbackResponse(BaseModel):
    id: UUID
    request_id: str | None = None
    user_id: UUID | None = None
    query: str
    rating: str
    comment: str | None = None
    created_at: datetime
