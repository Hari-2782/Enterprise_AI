from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class EvaluationCaseInput(BaseModel):
    case_id: str = Field(min_length=1, max_length=100)
    query: str = Field(min_length=1, max_length=2048)
    expected_document_ids: list[str] = Field(default_factory=list)
    should_abstain: bool = False


class RunEvaluationRequest(BaseModel):
    experiment_name: str = Field(min_length=1, max_length=150)
    dataset_name: str = Field(min_length=1, max_length=150)
    top_k: int = Field(default=5, ge=1, le=20)
    config: dict[str, Any] = Field(default_factory=dict)
    cases: list[EvaluationCaseInput] = Field(min_length=1, max_length=200)


class EvaluationRunResponse(BaseModel):
    run_id: UUID | None = None
    experiment_name: str
    dataset_name: str
    status: str = "completed"
    total_cases: int
    precision_at_k: float
    recall_at_k: float
    mrr: float
    ndcg_at_k: float
    citation_correctness: float
    abstention_accuracy: float
    avg_latency_ms: float
    total_tokens: int
    created_at: datetime | None = None
