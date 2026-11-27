
from pathlib import Path

import pymupdf as fitz

from app.schemas.extraction import (
    ExtractedBlock,
    ExtractedPage,
    ExtractionResult,
)


def extract_pdf(file_path: str | Path) -> ExtractionResult:
    path = Path(file_path)

    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    if path.suffix.lower() != ".pdf":
        raise ValueError("Expected a .pdf file")

    pages: list[ExtractedPage] = []
    extraction_errors: list[str] = []
    successful_pages = 0
    failed_pages = 0

    try:
        with fitz.open(path) as document:
            if document.is_encrypted:
                raise ValueError("Encrypted PDFs are not supported")

            total_pages = len(document)

            if total_pages == 0:
                raise ValueError("PDF contains no pages")

            for page_index, page in enumerate(document):
                page_number = page_index + 1

                try:
                    raw_blocks = page.get_text("dict")["blocks"]

                    blocks = []

                    for block_index, raw_block in enumerate(raw_blocks):
                        if raw_block.get("type") != 0:
                            continue

                        lines = raw_block.get("lines", [])
                        spans = [
                            span
                            for line in lines
                            for span in line.get("spans", [])
                        ]

                        text = "\n".join(
                            span["text"]
                            for span in spans
                        ).strip()

                        if not text:
                            continue

                        font_sizes = [
                            span["size"]
                            for span in spans
                            if span.get("text", "").strip()
                        ]

                        font_flags = [
                            span.get("flags", 0)
                            for span in spans
                        ]

                        font_size = (
                            max(font_sizes)
                            if font_sizes
                            else None
                        )

                        is_bold = any(
                            flags & 16
                            for flags in font_flags
                        )

                        blocks.append(
                            ExtractedBlock(
                                type="paragraph",
                                text=text,
                                font_size=font_size,
                                is_bold=is_bold,
                                block_index=block_index,
                            )
                        )
                    pages.append(
                        ExtractedPage(
                            page_number=page_number,
                            blocks=blocks,
                            extraction_status="completed"
                            if blocks
                            else "blank",
                        )
                    )

                    successful_pages += 1

                
                except Exception as exc:
                    failed_pages += 1

                    error = (
                        f"Page {page_number}: "
                        f"{type(exc).__name__}: {exc}"
                    )

                    extraction_errors.append(error)

                    pages.append(
                        ExtractedPage(
                            page_number=page_number,
                            extraction_status="failed",
                            error_message=error,
                        )
                    )

            status = (
                "failed"
                if successful_pages == 0
                else (
                    "partially_extracted"
                    if failed_pages > 0
                    else "completed"
                )
            )

            return ExtractionResult(
                filename=path.name,
                file_type="pdf",
                status=status,
                pages=pages,
                total_pages=total_pages,
                successful_pages=successful_pages,
                failed_pages=failed_pages,
                extraction_errors=extraction_errors,
            )

    except (fitz.FileDataError, fitz.EmptyFileError) as exc:
        raise ValueError("Invalid or unreadable PDF file") from exc
