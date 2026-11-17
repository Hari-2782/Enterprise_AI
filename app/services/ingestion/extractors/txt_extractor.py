
from pathlib import Path

from app.schemas.extraction import (
    ExtractedBlock,
    ExtractedPage,
    ExtractionResult,
)


def extract_txt(file_path: str | Path) -> ExtractionResult:
    path = Path(file_path)

    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    if path.suffix.lower() != ".txt":
        raise ValueError("Expected a .txt file")

    raw_bytes = path.read_bytes()

    if not raw_bytes:
        raise ValueError("The TXT file is empty")

    text = None

    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = raw_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue

    if text is None:
        raise ValueError(
            "Unable to decode TXT file using supported encodings"
        )

    blocks = [
        ExtractedBlock(
            type="paragraph",
            text=line.strip(),
        )
        for line in text.splitlines()
        if line.strip()
    ]

    if not blocks:
        raise ValueError("No extractable text found")

    page = ExtractedPage(
        page_number=1,
        blocks=blocks,
        extraction_status="completed",
    )

    return ExtractionResult(
        filename=path.name,
        file_type="txt",
        status="completed",
        total_pages=1,
        successful_pages=1,
        failed_pages=0,
        pages=[page],
    )
