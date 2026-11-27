from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class IngestionAccepted(BaseModel):
    document_id: UUID
    version_id: UUID
    status: str
    duplicate: bool = False
    request_id: str


class IngestionStatus(BaseModel):
    document_id: UUID
    version_id: UUID
    version_number: int
    filename: str
    status: str
    expected_chunks: int
    indexed_chunks: int
    error_message: str | None = None
    published_at: datetime | None = None
