
from pydantic import BaseModel, Field, model_validator


class ChunkSource(BaseModel):
    """Reference to the original extracted document block."""

    page_number: int = Field(ge=1)
    block_index: int = Field(ge=0)

    # Character range within the original block.
    # End position is exclusive.
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_character_range(self):
        if (self.char_start is None) != (self.char_end is None):
            raise ValueError(
                "char_start and char_end must either both be set or both be None"
            )

        if (
            self.char_start is not None
            and self.char_end <= self.char_start
        ):
            raise ValueError(
                "char_end must be greater than char_start"
            )

        return self


class DocumentChunkData(BaseModel):
    chunk_index: int = Field(ge=0)

    content: str = Field(min_length=1)
    token_count: int = Field(ge=1)

    section_path: str | None = None
    sources: list[ChunkSource] = Field(default_factory=list)

    # Token positions within the section text.
    source_token_start: int = Field(ge=0)
    source_token_end: int = Field(ge=1)
    source_token_count: int = Field(ge=1)

    @property
    def embedding_text(self) -> str:
        """Return the exact passage text sent to the E5 embedding model."""
        body = (
            f"{self.section_path}\n{self.content}"
            if self.section_path
            else self.content
        )
        return f"passage: {body}"

    @model_validator(mode="after")
    def validate_source_token_boundaries(self):
        if self.source_token_end <= self.source_token_start:
            raise ValueError(
                "source_token_end must be greater than source_token_start"
            )

        actual_count = (
            self.source_token_end - self.source_token_start
        )

        if actual_count != self.source_token_count:
            raise ValueError(
                "source_token_count must equal "
                "source_token_end - source_token_start"
            )

        return self
