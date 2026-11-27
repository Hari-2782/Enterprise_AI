from pathlib import Path
from types import SimpleNamespace

import pymupdf
from docx import Document

from app.services.ingestion.chunking_service import (
    StructureAwareChunkingService,
)
from app.services.ingestion.extraction_service import extract_document
from app.services.ingestion.publication_policy import (
    can_publish_extraction,
)


class FakeTokenizerService:
    """Keep pipeline tests independent of native model dependencies."""

    def split_passage_with_metadata(
        self,
        content,
        target_tokens,
        max_tokens,
        overlap_tokens,
        context,
    ):
        if not content.strip():
            return []
        return [
            SimpleNamespace(
                content=content,
                source_token_start=0,
                source_token_end=8,
                source_token_count=8,
                passage_token_count=min(target_tokens, 24),
                source_char_start=0,
                source_char_end=len(content),
            )
        ]


def write_fixtures(tmp_path: Path):
    txt_path = tmp_path / "policy.txt"
    txt_path.write_text(
        "Travel reimbursement policy.\nSubmit receipts for approval.",
        encoding="utf-8",
    )

    docx_path = tmp_path / "policy.docx"
    document = Document()
    document.add_heading("Employee Benefits", level=1)
    document.add_heading("Travel Benefits", level=2)
    document.add_paragraph("Approved travel expenses require receipts.")
    document.save(docx_path)

    pdf_path = tmp_path / "policy.pdf"
    with pymupdf.open() as pdf:
        first = pdf.new_page()
        first.insert_text((72, 72), "Page one travel policy.")
        second = pdf.new_page()
        second.insert_text((72, 72), "Page two receipt requirements.")
        pdf.save(pdf_path)

    return txt_path, docx_path, pdf_path


def test_real_txt_docx_pdf_ingestion_pipeline(tmp_path):
    tokenizer = FakeTokenizerService()
    chunker = StructureAwareChunkingService()
    txt_path, docx_path, pdf_path = write_fixtures(tmp_path)

    txt_result = extract_document(txt_path)
    txt_chunks = chunker.chunk_extraction(
        txt_result,
        tokenizer_service=tokenizer,
    )
    assert txt_result.status == "completed"
    assert txt_chunks[0].section_path is None
    assert txt_chunks[0].sources
    assert all(source.page_number == 1 for source in txt_chunks[0].sources)
    assert txt_chunks[0].token_count <= 450
    assert can_publish_extraction(txt_result, len(txt_chunks))

    docx_result = extract_document(docx_path)
    docx_chunks = chunker.chunk_extraction(
        docx_result,
        tokenizer_service=tokenizer,
    )
    assert docx_result.status == "completed"
    assert len(docx_chunks) == 1
    assert docx_chunks[0].section_path == (
        "Employee Benefits > Travel Benefits"
    )
    assert docx_chunks[0].sources
    assert docx_chunks[0].sources[0].page_number == 1
    assert docx_chunks[0].token_count <= 450
    assert "passage: Employee Benefits > Travel Benefits\n" in (
        docx_chunks[0].embedding_text
    )

    pdf_result = extract_document(pdf_path)
    pdf_chunks = chunker.chunk_extraction(
        pdf_result,
        tokenizer_service=tokenizer,
    )
    assert pdf_result.status == "completed"
    assert pdf_result.total_pages == 2
    assert {source.page_number for chunk in pdf_chunks for source in chunk.sources} == {1, 2}
    assert all(chunk.token_count <= 450 for chunk in pdf_chunks)
    assert can_publish_extraction(pdf_result, len(pdf_chunks))

    partial_result = docx_result.model_copy(
        update={
            "status": "partially_extracted",
            "failed_pages": 1,
        }
    )
    assert not can_publish_extraction(partial_result, len(docx_chunks))
