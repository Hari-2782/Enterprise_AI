
from app.services.ingestion.tokenizer_service import E5TokenizerService


def measure_overlap(previous: str, current: str, service) -> int:
    """
    Estimate matching token IDs at the boundary of two decoded chunks.

    Note: This measures re-tokenized text, not the original source
    token windows. Re-tokenization can change token boundaries.
    """
    previous_ids = service._encode_ids(previous)
    current_ids = service._encode_ids(current)

    max_overlap = min(
        50,
        len(previous_ids),
        len(current_ids),
    )

    for size in range(max_overlap, 0, -1):
        if previous_ids[-size:] == current_ids[:size]:
            return size

    return 0


def main():
    service = E5TokenizerService()

    sample = "Employee accommodation reimbursement policy"

    print("Model limit:", service.model_limit)

    # 1. Verify token count against the standard tokenizer.
    reference = service.tokenizer(
        f"passage: {sample}",
        add_special_tokens=True,
    )["input_ids"]

    actual_count = service.count_passage_tokens(sample)

    assert actual_count == len(reference)

    print("Sample tokens:", actual_count)
    print("Token-count equivalence: passed")

    # 2. Generate less repetitive test content.
    long_text = " ".join(
        f"employee{i:05d} department{i:05d} "
        f"reimbursement{i:05d} policy{i:05d} "
        f"approval{i:05d} expense{i:05d}"
        for i in range(1000)
    )

    # 3. Split long text into chunks.
    chunks = service.split_passage(
        long_text,
        max_tokens=450,
        overlap_tokens=50,
    )

    print("\nGenerated chunks:", len(chunks))

    for index, chunk in enumerate(chunks):
        token_count = service.count_passage_tokens(chunk)

        assert token_count <= 450
        assert chunk.strip()

        print(f"Chunk {index}: {token_count} tokens")

    print("Chunk-size validation: passed")

    # 4. Verify exact overlap using original source token positions.
    metadata_chunks = service.split_passage_with_metadata(
        long_text,
        max_tokens=450,
        overlap_tokens=50,
    )

    print("\nCharacter provenance validation:")

    for index, chunk in enumerate(metadata_chunks):
        original_text = long_text[
            chunk.source_char_start:chunk.source_char_end
        ]

        assert original_text == chunk.content
        assert (
            chunk.source_token_end - chunk.source_token_start
            == chunk.source_token_count
        )
        assert chunk.passage_token_count <= 450

        print(f"Chunk {index}: provenance passed")

    print("Token and character provenance: passed")

    print("\nSource token-window validation:")

    for index in range(1, len(metadata_chunks)):
        previous = metadata_chunks[index - 1]
        current = metadata_chunks[index]

        actual_overlap = (
            previous.source_token_end - current.source_token_start
        )

        expected_overlap = min(
            50,
            previous.source_token_count,
        )

        assert actual_overlap == expected_overlap

        print(
            f"Chunks {index - 1} -> {index}: "
            f"{actual_overlap} source tokens"
        )

    print("Exact source-window overlap: passed")

    # 5. Test empty input.
    assert service.split_passage("   ") == []

    print("Empty-input test: passed")

    # 5. Measure decoded chunk overlap.
    print("\nActual overlap measurements:")

    overlaps = []

    for index in range(len(chunks) - 1):
        overlap = measure_overlap(
            chunks[index],
            chunks[index + 1],
            service,
        )

        overlaps.append(overlap)

        print(
            f"Chunks {index} -> {index + 1}: "
            f"{overlap} matching tokens"
        )

    if overlaps:
        print("\nOverlap summary:")
        print("Minimum:", min(overlaps))
        print("Maximum:", max(overlaps))
        print("Average:", round(sum(overlaps) / len(overlaps), 2))

    print("\nAll tokenizer smoke tests passed.")


if __name__ == "__main__":
    main()
