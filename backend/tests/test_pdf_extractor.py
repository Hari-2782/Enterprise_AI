
import pymupdf as fitz
import pytest

from app.services.ingestion.extractors.pdf_extractor import (
    extract_pdf,
)


def create_test_pdf(path):
    document = fitz.open()

    page = document.new_page()

    page.insert_text(
        (72, 72),
        "Employee Travel Policy",
        fontsize=20,
    )

    page.insert_text(
        (72, 110),
        "Employees can claim approved expenses.",
        fontsize=11,
    )

    document.new_page()

    document.save(path)
    document.close()


def test_extract_pdf_pages_and_blocks(tmp_path):
    file_path = tmp_path / "policy.pdf"
    create_test_pdf(file_path)

    result = extract_pdf(file_path)

    assert result.status == "completed"
    assert result.total_pages == 2
    assert result.successful_pages == 2
    assert result.failed_pages == 0

    first_page = result.pages[0]

    assert first_page.page_number == 1
    assert len(first_page.blocks) == 2

    extracted_text = "\n".join(
        block.text for block in first_page.blocks
    )

    assert "Employee Travel Policy" in extracted_text
    assert "Employees can claim approved expenses." in extracted_text

    assert first_page.blocks[0].font_size == 20

    assert result.pages[1].page_number == 2
    assert result.pages[1].blocks == []
    assert result.pages[1].extraction_status == "blank"


def test_reject_non_pdf_file(tmp_path):
    file_path = tmp_path / "policy.txt"
    file_path.write_text("Test content", encoding="utf-8")

    with pytest.raises(ValueError, match="Expected a .pdf"):
        extract_pdf(file_path)


def test_reject_missing_pdf(tmp_path):
    with pytest.raises(FileNotFoundError):
        extract_pdf(tmp_path / "missing.pdf")


def test_reject_invalid_pdf(tmp_path):
    file_path = tmp_path / "invalid.pdf"
    file_path.write_text("This is not a PDF", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="Invalid or unreadable",
    ):
        extract_pdf(file_path)
