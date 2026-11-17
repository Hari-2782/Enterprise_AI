
from pydantic import BaseModel, Field


class ChunkSource(BaseModel):
    page_number: int = Field(ge=1)
    block_index: int = Field(ge=0)


class DocumentChunkData(BaseModel):
    chunk_index: int = Field(ge=0)
    content: str = Field(min_length=1)
    token_count: int = Field(ge=1)

    section_path: str | None = None

    sources: list[ChunkSource] = Field(default_factory=list)
