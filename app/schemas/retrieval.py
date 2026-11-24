from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class SearchRequest(BaseModel):
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


class RetrievalHitResponse(BaseModel):
    chunk_id: str
    document_id: UUID
    version_id: UUID
    chunk_index: int
    title: str
    content: str
    section_path: str | None = None
    department: str
    page_numbers: list[int] = Field(default_factory=list)
    sources_json: str | None = None
    score: float


class SearchResponse(BaseModel):
    query: str
    candidate_count: int
    results: list[RetrievalHitResponse]
    request_id: str
