
from dataclasses import dataclass
from functools import lru_cache

from transformers import AutoTokenizer


MODEL_NAME = "intfloat/multilingual-e5-small"


@dataclass(frozen=True)
class TokenizedChunk:
    """Chunk content with original source positions."""

    content: str

    source_token_start: int
    source_token_end: int
    source_token_count: int

    passage_token_count: int

    source_char_start: int
    source_char_end: int

@lru_cache(maxsize=2)
def load_tokenizer(model_name: str = MODEL_NAME):
    """Load and cache the tokenizer."""
    return AutoTokenizer.from_pretrained(
        model_name,
        use_fast=True,
    )


class E5TokenizerService:
    def __init__(self, model_name: str = MODEL_NAME):
        self.tokenizer = load_tokenizer(model_name)
        self.model_limit = self.tokenizer.model_max_length

    def _encode_ids(
        self,
        text: str,
        add_special_tokens: bool = False,
    ) -> list[int]:
        """Encode text using the fast tokenizer backend."""
        encoding = self.tokenizer.backend_tokenizer.encode(
            text,
            add_special_tokens=False,
        )

        token_ids = encoding.ids

        if add_special_tokens:
            token_ids = self.tokenizer.build_inputs_with_special_tokens(
                token_ids
            )

        return token_ids

    def count_passage_tokens(
        self,
        content: str,
        context: str | None = None,
    ) -> int:
        """Count the full E5 passage input, including section context."""
        body = (
            f"{context.strip()}\n{content}"
            if context and context.strip()
            else content
        )
        return len(
            self._encode_ids(
                f"passage: {body}",
                add_special_tokens=True,
            )
        )

    def split_passage_with_metadata(
        self,
        content: str,
        target_tokens: int = 400,
        max_tokens: int = 450,
        overlap_tokens: int = 50,
        context: str | None = None,
    ) -> list[TokenizedChunk]:
        """
        Split text into token-bounded chunks while preserving
        original token and character positions.
        """

        if max_tokens <= 0 or max_tokens > self.model_limit:
            raise ValueError(
                f"max_tokens must be between 1 and {self.model_limit}"
            )

        if target_tokens <= 0 or target_tokens > max_tokens:
            raise ValueError(
                "target_tokens must be positive and cannot exceed max_tokens"
            )

        if overlap_tokens < 0:
            raise ValueError("overlap_tokens cannot be negative")

        if not content.strip():
            return []

        # Obtain token IDs and character offsets from the same
        # fast-tokenizer encoding operation.
        encoding = self.tokenizer.backend_tokenizer.encode(
            content,
            add_special_tokens=False,
        )

        content_ids = encoding.ids
        offsets = encoding.offsets

        if not content_ids:
            return []

        normalized_context = (
            context.strip()
            if context and context.strip()
            else None
        )
        prefix = (
            f"passage: {normalized_context}\n"
            if normalized_context
            else "passage: "
        )

        prefix_cost = len(
            self._encode_ids(
                prefix,
                add_special_tokens=True,
            )
        )

        content_budget = target_tokens - prefix_cost - 2

        if content_budget <= 0:
            raise ValueError(
                "Section context leaves insufficient token budget"
            )

        if overlap_tokens >= content_budget:
            raise ValueError(
                "Overlap must be smaller than the content token budget"
            )

        chunks: list[TokenizedChunk] = []
        start = 0

        while start < len(content_ids):
            end = min(
                start + content_budget,
                len(content_ids),
            )

            while end > start:
                # Map the original token window to character positions.
                char_start = offsets[start][0]
                char_end = offsets[end - 1][1]

                if char_end <= char_start:
                    end -= 1
                    continue

                # Use the exact original source substring instead
                # of decoding and reconstructing the token IDs.
                chunk_text = content[char_start:char_end]

                passage_token_count = self.count_passage_tokens(
                    chunk_text,
                    context=normalized_context,
                )

                if (
                    chunk_text.strip()
                    and passage_token_count <= target_tokens
                ):
                    break

                end -= 1

            if end <= start:
                raise ValueError(
                    "Unable to produce a chunk within the token limit"
                )

            chunks.append(
                TokenizedChunk(
                    content=chunk_text,
                    source_token_start=start,
                    source_token_end=end,
                    source_token_count=end - start,
                    passage_token_count=passage_token_count,
                    source_char_start=char_start,
                    source_char_end=char_end,
                )
            )

            if end == len(content_ids):
                break

            start = max(
                start + 1,
                end - overlap_tokens,
            )

        return chunks

    def split_passage(
        self,
        content: str,
        max_tokens: int = 450,
        overlap_tokens: int = 50,
    ) -> list[str]:
        """
        Backward-compatible method returning only chunk text.
        """
        chunks = self.split_passage_with_metadata(
            content=content,
            target_tokens=min(400, max_tokens),
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
        )

        return [chunk.content for chunk in chunks]

