
from types import SimpleNamespace

from app.schemas.extraction import (
    ExtractionResult,
    ExtractedPage,
    ExtractedBlock,
)
from app.services.ingestion.chunking_service import (
    StructureAwareChunkingService,
)


def create_block(
    block_type,
    text,
    section_path=None,
    block_index=None,
):
    return ExtractedBlock(
        type=block_type,
        text=text,
        section_path=section_path,
        block_index=block_index,
    )


def create_extraction(blocks):
    return ExtractionResult(
        filename="employee_policy.docx",
        file_type="docx",
        status="completed",
        pages=[
            ExtractedPage(
                page_number=1,
                blocks=blocks,
                extraction_status="completed",
            )
        ],
        total_pages=1,
        successful_pages=1,
        failed_pages=0,
    )


def test_groups_parent_and_child_sections_separately():
    extraction = create_extraction([
        create_block("heading", "Employee Benefits", block_index=0),
        create_block("paragraph", "Paragraph A", block_index=1),
        create_block("paragraph", "Paragraph B", block_index=2),

        create_block(
            "heading",
            "Medical Benefits",
            section_path="Employee Benefits / Medical Benefits",
            block_index=3,
        ),
        create_block("paragraph", "Paragraph C", block_index=4),
        create_block("paragraph", "Paragraph D", block_index=5),

        create_block(
            "heading",
            "Travel Benefits",
            section_path="Employee Benefits / Travel Benefits",
            block_index=6,
        ),
        create_block("paragraph", "Paragraph E", block_index=7),
    ])

    service = StructureAwareChunkingService()
    groups = service.group_by_section(extraction)

    assert len(groups) == 3

    assert groups[0].section_path == "Employee Benefits"
    assert groups[0].content == "Paragraph A\n\nParagraph B"

    assert (
        groups[1].section_path
        == "Employee Benefits / Medical Benefits"
    )
    assert groups[1].content == "Paragraph C\n\nParagraph D"

    assert (
        groups[2].section_path
        == "Employee Benefits / Travel Benefits"
    )
    assert groups[2].content == "Paragraph E"


def test_preserves_source_locations():
    extraction = create_extraction([
        create_block("heading", "Travel Benefits", block_index=0),
        create_block("paragraph", "Travel expenses", block_index=1),
    ])

    service = StructureAwareChunkingService()
    groups = service.group_by_section(extraction)

    sources = groups[0].sources

    assert len(sources) == 2
    assert sources[0].page_number == 1
    assert sources[0].block_index == 0
    assert sources[1].block_index == 1


def test_handles_document_without_headings():
    extraction = create_extraction([
        create_block("paragraph", "First paragraph", block_index=0),
        create_block("paragraph", "Second paragraph", block_index=1),
    ])

    service = StructureAwareChunkingService()
    groups = service.group_by_section(extraction)

    assert len(groups) == 1
    assert groups[0].section_path is None
    assert "First paragraph" in groups[0].content
    assert "Second paragraph" in groups[0].content


def test_preserves_page_numbers():
    extraction = ExtractionResult(
        filename="employee_policy.pdf",
        file_type="pdf",
        status="completed",
        pages=[
            ExtractedPage(
                page_number=1,
                blocks=[
                    create_block("heading", "Company Policy", block_index=0),
                    create_block("paragraph", "Page one content", block_index=1),
                ],
                extraction_status="completed",
            ),
            ExtractedPage(
                page_number=2,
                blocks=[
                    create_block("paragraph", "Page two content", block_index=0),
                ],
                extraction_status="completed",
            ),
        ],
        total_pages=2,
        successful_pages=2,
        failed_pages=0,
    )

    service = StructureAwareChunkingService()
    groups = service.group_by_section(extraction)

    assert len(groups) == 1

    assert groups[0].sources[1].page_number == 1
    assert groups[0].sources[2].page_number == 2
def test_tracks_exact_block_character_ranges():
    extraction = create_extraction([
        create_block("heading", "Travel Benefits", block_index=0),
        create_block("paragraph", "First paragraph", block_index=1),
        create_block("paragraph", "Second paragraph", block_index=2),
    ])

    service = StructureAwareChunkingService()
    groups = service.group_by_section(extraction)

    content, spans = groups[0].build_content_with_spans()

    assert content == "First paragraph\n\nSecond paragraph"

    first = spans[0]
    second = spans[1]

    assert content[
        first.section_char_start:first.section_char_end
    ] == "First paragraph"

    assert content[
        second.section_char_start:second.section_char_end
    ] == "Second paragraph"


def test_returns_only_blocks_contributing_to_chunk():
    extraction = create_extraction([
        create_block("heading", "Travel Benefits", block_index=0),
        create_block("paragraph", "First paragraph", block_index=1),
        create_block("paragraph", "Second paragraph", block_index=2),
    ])

    service = StructureAwareChunkingService()
    groups = service.group_by_section(extraction)

    content = groups[0].content

    # Select only the second paragraph.
    start = content.index("Second paragraph")
    end = start + len("Second paragraph")

    sources = groups[0].sources_for_range(start, end)

    assert len(sources) == 1
    assert sources[0].page_number == 1
    assert sources[0].block_index == 2
    assert sources[0].char_start == 0
    assert sources[0].char_end == len("Second paragraph")


def test_tracks_partial_block_provenance():
    extraction = create_extraction([
        create_block("heading", "Travel Benefits", block_index=0),
        create_block(
            "paragraph",
            "Approved travel expenses require receipts.",
            block_index=1,
        ),
    ])

    service = StructureAwareChunkingService()
    groups = service.group_by_section(extraction)

    content = groups[0].content

    start = content.index("travel")
    end = start + len("travel expenses")

    sources = groups[0].sources_for_range(start, end)

    assert len(sources) == 1
    assert sources[0].block_index == 1
    assert sources[0].char_start == start
    assert sources[0].char_end == end


class FakeTokenizerService:
    """Deterministic tokenizer substitute for integration unit tests."""

    def __init__(self):
        self.calls = []

    def split_passage_with_metadata(
        self,
        content,
        target_tokens,
        max_tokens,
        overlap_tokens,
        context,
    ):
        self.calls.append({
            "content": content,
            "target_tokens": target_tokens,
            "max_tokens": max_tokens,
            "overlap_tokens": overlap_tokens,
            "context": context,
        })
        start = content.index("Approved")
        end = len(content)
        return [
            SimpleNamespace(
                content=content[start:end],
                source_token_start=0,
                source_token_end=5,
                source_token_count=5,
                passage_token_count=12,
                source_char_start=start,
                source_char_end=end,
            )
        ]


def test_chunks_extraction_with_context_and_precise_provenance():
    extraction = create_extraction([
        create_block("heading", "Travel Benefits", block_index=0),
        create_block(
            "paragraph",
            "Introductory text. Approved travel expenses require receipts.",
            block_index=1,
        ),
    ])
    tokenizer = FakeTokenizerService()

    chunks = StructureAwareChunkingService().chunk_extraction(
        extraction,
        tokenizer_service=tokenizer,
    )

    assert len(chunks) == 1
    chunk = chunks[0]
    assert tokenizer.calls == [{
        "content": "Introductory text. Approved travel expenses require receipts.",
        "target_tokens": 400,
        "max_tokens": 450,
        "overlap_tokens": 50,
        "context": "Travel Benefits",
    }]
    assert chunk.content == "Approved travel expenses require receipts."
    assert chunk.section_path == "Travel Benefits"
    assert chunk.embedding_text == (
        "passage: Travel Benefits\nApproved travel expenses require receipts."
    )
    assert chunk.token_count == 12
    assert chunk.sources[0].page_number == 1
    assert chunk.sources[0].block_index == 1
    assert chunk.sources[0].char_start == len("Introductory text. ")
    assert chunk.sources[0].char_end == len(
        "Introductory text. Approved travel expenses require receipts."
    )
    assert chunk.source_token_start == 0
    assert chunk.source_token_end == 5
    assert chunk.source_token_count == 5
