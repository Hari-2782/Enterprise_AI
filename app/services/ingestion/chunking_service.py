
from dataclasses import dataclass, field

from app.schemas.extraction import ExtractionResult, ExtractedBlock
from app.schemas.chunking import ChunkSource, DocumentChunkData


@dataclass
class BlockReference:
    """An extracted block and its original document location."""

    page_number: int
    block_index: int
    block: ExtractedBlock


@dataclass
class BlockSpan:
    """A block's character range within its combined section text."""

    reference: BlockReference
    section_char_start: int
    section_char_end: int


@dataclass
class SectionGroup:
    """Consecutive content belonging to one section."""

    section_path: str | None
    blocks: list[BlockReference] = field(default_factory=list)
    heading_sources: list[ChunkSource] = field(default_factory=list)

    @property
    def sources(self) -> list[ChunkSource]:
        """Return heading and content block locations in document order."""
        content_sources = [
            ChunkSource(
                page_number=reference.page_number,
                block_index=reference.block_index,
            )
            for reference in self.blocks
        ]
        return sorted(
            [*self.heading_sources, *content_sources],
            key=lambda source: (source.page_number, source.block_index),
        )

    def build_content_with_spans(
        self,
    ) -> tuple[str, list[BlockSpan]]:
        """
        Combine section blocks and record their exact character ranges.

        Blocks are separated by two newline characters.
        Character positions use zero-based indexing and exclusive ends.
        """
        parts: list[str] = []
        spans: list[BlockSpan] = []

        cursor = 0

        for reference in self.blocks:
            if parts:
                separator = "\n\n"
                parts.append(separator)
                cursor += len(separator)

            block_text = reference.block.text

            start = cursor
            end = start + len(block_text)

            parts.append(block_text)

            spans.append(
                BlockSpan(
                    reference=reference,
                    section_char_start=start,
                    section_char_end=end,
                )
            )

            cursor = end

        return "".join(parts), spans

    @property
    def content(self) -> str:
        """Return combined section content."""
        content, _ = self.build_content_with_spans()
        return content

    def sources_for_range(
        self,
        char_start: int,
        char_end: int,
    ) -> list[ChunkSource]:
        """
        Return only original blocks that contribute characters
        to the requested section-text range.
        """
        if char_start < 0 or char_end <= char_start:
            raise ValueError("Invalid character range")

        _, spans = self.build_content_with_spans()

        sources: list[ChunkSource] = []

        for span in spans:
            intersection_start = max(
                char_start,
                span.section_char_start,
            )

            intersection_end = min(
                char_end,
                span.section_char_end,
            )

            # No content from this block contributes to the range.
            if intersection_start >= intersection_end:
                continue

            # Convert section-relative positions into
            # block-relative positions.
            block_char_start = (
                intersection_start - span.section_char_start
            )

            block_char_end = (
                intersection_end - span.section_char_start
            )

            reference = span.reference

            sources.append(
                ChunkSource(
                    page_number=reference.page_number,
                    block_index=reference.block_index,
                    char_start=block_char_start,
                    char_end=block_char_end,
                )
            )

        return sources


class StructureAwareChunkingService:
    """
    Groups extracted document blocks by their section hierarchy.

    Content from different section paths is never combined.
    """

    def chunk_extraction(
        self,
        extraction: ExtractionResult,
        tokenizer_service=None,
        target_tokens: int = 400,
        max_tokens: int = 450,
        overlap_tokens: int = 50,
    ) -> list[DocumentChunkData]:
        """Convert extracted pages into provenance-aware document chunks."""
        if tokenizer_service is None:
            # Keep tokenizer and native dependency imports out of ordinary
            # section-grouping paths used by lightweight unit tests.
            from app.services.ingestion.tokenizer_service import (
                E5TokenizerService,
            )

            tokenizer_service = E5TokenizerService()

        document_chunks: list[DocumentChunkData] = []

        for group in self.group_by_section(extraction):
            section_content, _ = group.build_content_with_spans()
            tokenized_chunks = tokenizer_service.split_passage_with_metadata(
                content=section_content,
                target_tokens=target_tokens,
                max_tokens=max_tokens,
                overlap_tokens=overlap_tokens,
                context=group.section_path,
            )

            for tokenized_chunk in tokenized_chunks:
                sources = group.sources_for_range(
                    char_start=tokenized_chunk.source_char_start,
                    char_end=tokenized_chunk.source_char_end,
                )
                if not sources:
                    raise ValueError(
                        "Generated chunk has no original source references"
                    )

                document_chunks.append(
                    DocumentChunkData(
                        chunk_index=len(document_chunks),
                        content=tokenized_chunk.content,
                        token_count=tokenized_chunk.passage_token_count,
                        section_path=group.section_path,
                        sources=sources,
                        source_token_start=tokenized_chunk.source_token_start,
                        source_token_end=tokenized_chunk.source_token_end,
                        source_token_count=tokenized_chunk.source_token_count,
                    )
                )

        return document_chunks

    def group_by_section(
        self,
        extraction: ExtractionResult,
    ) -> list[SectionGroup]:

        groups: list[SectionGroup] = []

        current_section_path: str | None = None
        current_group: SectionGroup | None = None

        pending_heading_sources: list[ChunkSource] = []

        for page in extraction.pages:
            for position, block in enumerate(page.blocks):

                block_index = (
                    block.block_index
                    if block.block_index is not None
                    else position
                )

                if block.type == "heading":
                    current_section_path = (
                        block.section_path or block.text
                    ).strip()

                    pending_heading_sources.append(
                        ChunkSource(
                            page_number=page.page_number,
                            block_index=block_index,
                        )
                    )

                    current_group = None
                    continue

                section_path = (
                    block.section_path or current_section_path
                )

                if (
                    current_group is None
                    or current_group.section_path != section_path
                ):
                    current_group = SectionGroup(
                        section_path=section_path,
                        heading_sources=pending_heading_sources,
                    )

                    groups.append(current_group)
                    pending_heading_sources = []

                current_group.blocks.append(
                    BlockReference(
                        page_number=page.page_number,
                        block_index=block_index,
                        block=block,
                    )
                )

        return [
            group
            for group in groups
            if group.blocks
        ]
