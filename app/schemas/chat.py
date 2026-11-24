from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2048)
    top_k: int = Field(default=5, ge=1, le=20)
    candidate_count: int = Field(default=30, ge=1, le=100)
    department: str | None = Field(default=None, min_length=1, max_length=100)
    document_id: UUID | None = None
    version_id: UUID | None = None

    @model_validator(mode="after")
    def candidate_count_covers_top_k(self):
        if self.candidate_count < self.top_k:
            raise ValueError("candidate_count must be at least top_k")
        return self


class CitationResponse(BaseModel):
    citation_key: str
    chunk_id: str
    document_id: UUID
    version_id: UUID
    title: str
    section_path: str | None = None
    page_numbers: list[int] = Field(default_factory=list)
    score: float


class TokenUsageResponse(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatResponse(BaseModel):
    query: str
    answer: str
    abstained: bool
    abstention_reason: str | None = None
    citations: list[CitationResponse] = Field(default_factory=list)
    model: str
    provider: str
    prompt_version: str
    used_fallback: bool = False
    usage: TokenUsageResponse = Field(default_factory=TokenUsageResponse)
    latency_ms: float = 0.0
    request_id: str
