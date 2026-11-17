from app.schemas.extraction import ExtractionResult


def can_publish_extraction(
    extraction: ExtractionResult,
    chunk_count: int,
) -> bool:
    """Allow publication only for complete extraction with usable chunks."""
    return (
        extraction.status == "completed"
        and extraction.failed_pages == 0
        and chunk_count > 0
    )
