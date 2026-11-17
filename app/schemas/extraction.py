
from typing import Literal

from pydantic import BaseModel, Field


BlockType = Literal[
    "heading",
    "paragraph",
    "table",
    "list_item",
    "other",
]


ExtractionMethod = Literal[
    "native_text",
    "ocr",
]



class ExtractedBlock(BaseModel):
    type: BlockType
    text: str = Field(min_length=1)
    section_path: str | None = None
    extraction_method: ExtractionMethod = "native_text"

    font_size: float | None = None
    is_bold: bool = False
    block_index: int | None = None



class ExtractedPage(BaseModel):
    page_number: int = Field(ge=1)
    blocks: list[ExtractedBlock] = Field(default_factory=list)
    extraction_status: Literal[
        "completed",
        "blank",
        "failed",
    ] = "completed"
    error_message: str | None = None


class ExtractionResult(BaseModel):
    filename: str
    file_type: Literal["pdf", "docx", "txt"]
    status: Literal[
        "completed",
        "partially_extracted",
        "failed",
    ]
    pages: list[ExtractedPage] = Field(default_factory=list)
    total_pages: int = Field(ge=0)
    successful_pages: int = Field(ge=0)
    failed_pages: int = Field(ge=0)
    extraction_errors: list[str] = Field(default_factory=list)
