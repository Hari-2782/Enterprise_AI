
from zipfile import ZipFile

import pymupdf
from docx import Document

from app.services.ingestion.extraction_service import extract_document


def test_extract_pdf_through_service(tmp_path):
    path = tmp_path / "policy.pdf"

    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "PDF policy content")
    pdf.save(path)
    pdf.close()

    result = extract_document(path)

    assert result.file_type == "pdf"
    assert result.status == "completed"
    assert len(result.pages) == 1


def test_extract_docx_through_service(tmp_path):
    path = tmp_path / "policy.docx"

    document = Document()
    document.add_paragraph("DOCX policy content")
    document.save(path)

    result = extract_document(path)

    assert result.file_type == "docx"
    assert result.status == "completed"


def test_extract_txt_through_service(tmp_path):
    path = tmp_path / "policy.txt"
    path.write_text("TXT policy content", encoding="utf-8")

    result = extract_document(path)

    assert result.file_type == "txt"
    assert result.status == "completed"


def test_reject_mismatched_file_through_service(tmp_path):
    path = tmp_path / "fake.pdf"
    path.write_text("This is not a PDF")

    try:
        extract_document(path)
        assert False, "Expected validation to reject the file"
    except ValueError as exc:
        assert "does not match" in str(exc)
