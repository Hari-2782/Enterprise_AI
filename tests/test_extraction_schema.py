
from app.schemas.extraction import (
    ExtractedBlock,
    ExtractedPage,
    ExtractionResult,
)


def test_extraction_result_with_successful_page():
    result = ExtractionResult(
        filename="policy.pdf",
        file_type="pdf",
        status="completed",
        total_pages=1,
        successful_pages=1,
        failed_pages=0,
        pages=[
            ExtractedPage(
                page_number=1,
                blocks=[
                    ExtractedBlock(
                        type="heading",
                        text="Travel Policy",
                    ),
                    ExtractedBlock(
                        type="paragraph",
                        text="Employees can claim approved expenses.",
                    ),
                ],
            )
        ],
    )

    assert result.status == "completed"
    assert result.pages[0].page_number == 1
    assert len(result.pages[0].blocks) == 2


def test_partial_extraction_records_failed_page():
    result = ExtractionResult(
        filename="handbook.pdf",
        file_type="pdf",
        status="partially_extracted",
        total_pages=3,
        successful_pages=2,
        failed_pages=1,
        pages=[
            ExtractedPage(
                page_number=1,
                extraction_status="completed",
            ),
            ExtractedPage(
                page_number=2,
                extraction_status="failed",
                error_message="OCR failed",
            ),
            ExtractedPage(
                page_number=3,
                extraction_status="completed",
            ),
        ],
    )

    assert result.status == "partially_extracted"
    assert result.failed_pages == 1
    assert result.pages[1].error_message == "OCR failed"
