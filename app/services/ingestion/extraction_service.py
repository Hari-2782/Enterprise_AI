
from pathlib import Path

from app.schemas.extraction import ExtractionResult
from app.services.ingestion.file_validation import detect_file_type
from app.services.ingestion.extractors.pdf_extractor import extract_pdf
from app.services.ingestion.extractors.docx_extractor import extract_docx
from app.services.ingestion.extractors.txt_extractor import extract_txt


def extract_document(file_path: str | Path) -> ExtractionResult:
    """
    Validate and extract a supported document.

    Supported formats: PDF, DOCX and TXT.
    """
    file_type = detect_file_type(file_path)

    extractors = {
        "pdf": extract_pdf,
        "docx": extract_docx,
        "txt": extract_txt,
    }

    extractor = extractors.get(file_type)

    if extractor is None:
        raise ValueError(f"No extractor registered for: {file_type}")

    return extractor(file_path)
