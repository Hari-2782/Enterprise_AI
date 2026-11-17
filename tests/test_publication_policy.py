from app.schemas.extraction import (
    ExtractedPage,
    ExtractionResult,
)
from app.services.ingestion.publication_policy import (
    can_publish_extraction,
)


def make_result(status="completed", failed_pages=0):
    return ExtractionResult(
        filename="policy.txt",
        file_type="txt",
        status=status,
        pages=[ExtractedPage(page_number=1)],
        total_pages=1,
        successful_pages=1 if status != "failed" else 0,
        failed_pages=failed_pages,
    )


def test_completed_extraction_with_chunks_can_publish():
    assert can_publish_extraction(make_result(), chunk_count=1)


def test_partial_extraction_cannot_publish_even_with_chunks():
    partial = make_result("partially_extracted", failed_pages=1)
    assert not can_publish_extraction(partial, chunk_count=2)


def test_failed_extraction_cannot_publish():
    failed = make_result("failed", failed_pages=1)
    assert not can_publish_extraction(failed, chunk_count=1)


def test_completed_extraction_without_chunks_cannot_publish():
    assert not can_publish_extraction(make_result(), chunk_count=0)
