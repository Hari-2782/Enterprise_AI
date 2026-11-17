
import pytest

from app.services.ingestion.extractors.txt_extractor import (
    extract_txt,
)


def test_extract_txt_successfully(tmp_path):
    file_path = tmp_path / "policy.txt"

    file_path.write_text(
        "Travel Policy\n\nEmployees can claim expenses.\n"
        "Claims require approval.",
        encoding="utf-8",
    )

    result = extract_txt(file_path)

    assert result.status == "completed"
    assert result.file_type == "txt"
    assert result.total_pages == 1

    extracted_text = [
        block.text
        for block in result.pages[0].blocks
    ]

    assert extracted_text == [
        "Travel Policy",
        "Employees can claim expenses.",
        "Claims require approval.",
    ]


def test_extract_empty_txt(tmp_path):
    file_path = tmp_path / "empty.txt"
    file_path.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="empty"):
        extract_txt(file_path)


def test_reject_unsupported_extension(tmp_path):
    file_path = tmp_path / "policy.pdf"
    file_path.write_text("Some content", encoding="utf-8")

    with pytest.raises(ValueError, match="Expected a .txt"):
        extract_txt(file_path)


def test_extract_missing_file(tmp_path):
    file_path = tmp_path / "missing.txt"

    with pytest.raises(FileNotFoundError):
        extract_txt(file_path)
