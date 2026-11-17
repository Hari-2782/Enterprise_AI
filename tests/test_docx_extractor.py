
import pytest

from docx import Document

from app.services.ingestion.extractors.docx_extractor import (
    extract_docx,
)


def create_test_docx(path):
    document = Document()

    document.add_heading("Employee Benefits", level=1)

    document.add_paragraph(
        "Employees receive annual leave."
    )

    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Category"
    table.rows[0].cells[1].text = "Annual Leave"

    row = table.add_row()
    row.cells[0].text = "Full-time"
    row.cells[1].text = "21 days"

    document.add_heading("Medical Benefits", level=1)

    document.add_paragraph(
        "Employees receive medical coverage."
    )

    document.save(path)


def test_extract_docx_preserves_content_order(tmp_path):
    file_path = tmp_path / "benefits.docx"
    create_test_docx(file_path)

    result = extract_docx(file_path)

    assert result.status == "completed"
    assert result.file_type == "docx"

    blocks = result.pages[0].blocks

    assert [block.type for block in blocks] == [
        "heading",
        "paragraph",
        "table",
        "heading",
        "paragraph",
    ]

    assert blocks[0].text == "Employee Benefits"
    assert "21 days" in blocks[2].text
    assert blocks[3].text == "Medical Benefits"


def test_extract_docx_preserves_heading_hierarchy(tmp_path):
    file_path = tmp_path / "hierarchy.docx"

    document = Document()
    document.add_heading("Policies", level=1)
    document.add_heading("Leave", level=2)
    document.add_paragraph("Annual leave information.")
    document.save(file_path)

    result = extract_docx(file_path)

    paragraph = result.pages[0].blocks[2]

    assert paragraph.section_path == "Policies > Leave"


def test_reject_non_docx_file(tmp_path):
    file_path = tmp_path / "document.txt"
    file_path.write_text("Some content")

    with pytest.raises(ValueError, match="Expected a .docx"):
        extract_docx(file_path)


def test_reject_missing_docx(tmp_path):
    with pytest.raises(FileNotFoundError):
        extract_docx(tmp_path / "missing.docx")


def test_reject_empty_docx(tmp_path):
    file_path = tmp_path / "empty.docx"
    Document().save(file_path)

    with pytest.raises(ValueError, match="No extractable content"):
        extract_docx(file_path)
