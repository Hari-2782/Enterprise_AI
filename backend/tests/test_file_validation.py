
import pytest
from zipfile import ZipFile

from app.services.ingestion.file_validation import detect_file_type


def test_detect_pdf(tmp_path):
    path = tmp_path / "policy.pdf"
    path.write_bytes(b"%PDF-1.7\nsample")

    assert detect_file_type(path) == "pdf"


def test_detect_docx(tmp_path):
    path = tmp_path / "policy.docx"

    with ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("_rels/.rels", "<Relationships/>")
        archive.writestr("word/document.xml", "<document/>")

    assert detect_file_type(path) == "docx"


def test_reject_ordinary_zip_as_docx(tmp_path):
    path = tmp_path / "fake.docx"

    with ZipFile(path, "w") as archive:
        archive.writestr("notes.txt", "Not a DOCX")

    with pytest.raises(ValueError, match="Invalid DOCX"):
        detect_file_type(path)


def test_reject_pdf_with_wrong_extension(tmp_path):
    path = tmp_path / "policy.pdf"
    path.write_text("This is not a PDF")

    with pytest.raises(ValueError, match="does not match"):
        detect_file_type(path)


def test_detect_txt(tmp_path):
    path = tmp_path / "policy.txt"
    path.write_text("Employee policy", encoding="utf-8")

    assert detect_file_type(path) == "txt"


def test_reject_empty_file(tmp_path):
    path = tmp_path / "empty.txt"
    path.write_bytes(b"")

    with pytest.raises(ValueError, match="empty"):
        detect_file_type(path)


def test_reject_unsupported_extension(tmp_path):
    path = tmp_path / "policy.exe"
    path.write_bytes(b"sample")

    with pytest.raises(ValueError, match="Unsupported"):
        detect_file_type(path)


def test_reject_missing_file(tmp_path):
    path = tmp_path / "missing.pdf"

    with pytest.raises(FileNotFoundError):
        detect_file_type(path)
