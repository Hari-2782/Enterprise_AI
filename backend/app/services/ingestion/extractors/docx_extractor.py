
from pathlib import Path

from docx import Document as WordDocument
from docx.document import Document as DocumentObject
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.schemas.extraction import (
    ExtractedBlock,
    ExtractedPage,
    ExtractionResult,
)


def get_table_text(table: Table) -> str:
    """Convert a Word table into an ordered text representation."""
    rows = []

    for row_index, row in enumerate(table.rows, start=1):
        cells = [
            " ".join(cell.text.split())
            for cell in row.cells
        ]

        rows.append(
            f"Row {row_index}: " + " | ".join(cells)
        )

    return "\n".join(rows)


def extract_docx(file_path: str | Path) -> ExtractionResult:
    path = Path(file_path)

    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    if path.suffix.lower() != ".docx":
        raise ValueError("Expected a .docx file")

    try:
        document = WordDocument(path)
    except Exception as exc:
        raise ValueError("Invalid or unreadable DOCX file") from exc

    blocks: list[ExtractedBlock] = []
    heading_stack: list[tuple[int, str]] = []

    for element in document.iter_inner_content():

        if isinstance(element, Paragraph):
            text = element.text.strip()

            if not text:
                continue

            style_name = element.style.name if element.style else ""

            if style_name.startswith("Heading "):
                try:
                    level = int(style_name.split()[-1])
                except ValueError:
                    level = 1

                heading_stack = [
                    item
                    for item in heading_stack
                    if item[0] < level
                ]

                heading_stack.append((level, text))

                blocks.append(
                    ExtractedBlock(
                        type="heading",
                        text=text,
                        section_path=" > ".join(
                            heading for _, heading in heading_stack
                        ),
                    )
                )

            else:
                blocks.append(
                    ExtractedBlock(
                        type="paragraph",
                        text=text,
                        section_path=" > ".join(
                            heading for _, heading in heading_stack
                        ) or None,
                    )
                )

        elif isinstance(element, Table):
            table_text = get_table_text(element)

            if table_text.strip():
                blocks.append(
                    ExtractedBlock(
                        type="table",
                        text=table_text,
                        section_path=" > ".join(
                            heading for _, heading in heading_stack
                        ) or None,
                    )
                )

    if not blocks:
        raise ValueError("No extractable content found in DOCX")

    # DOCX has no reliable physical page mapping here.
    # This is one logical extraction unit, not a rendered page.
    logical_page = ExtractedPage(
        page_number=1,
        blocks=blocks,
        extraction_status="completed",
    )

    return ExtractionResult(
        filename=path.name,
        file_type="docx",
        status="completed",
        pages=[logical_page],
        total_pages=1,
        successful_pages=1,
        failed_pages=0,
    )
