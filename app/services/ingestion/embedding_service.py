from functools import lru_cache
from typing import Sequence

from app.schemas.chunking import DocumentChunkData


MODEL_NAME = "intfloat/multilingual-e5-small"
EMBEDDING_DIMENSION = 384
DEFAULT_BATCH_SIZE = 16
MAX_INPUT_TOKENS = 512


@lru_cache(maxsize=1)
def _load_model_and_tokenizer(model_name: str = MODEL_NAME):
    """Load the CPU model once per process."""
    import torch
    from transformers import AutoModel, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)
    model.eval()
    model.to("cpu")
    return torch, tokenizer, model


class E5EmbeddingService:
    """Create normalized multilingual E5 passage embeddings in batches."""

    def __init__(
        self,
        model_name: str = MODEL_NAME,
        batch_size: int = DEFAULT_BATCH_SIZE,
        model_bundle=None,
    ):
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        self.model_name = model_name
        self.batch_size = batch_size
        self._model_bundle = model_bundle

    @staticmethod
    def _validate_text(text: str, prefix: str = "passage:") -> None:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Embedding input must be a non-empty string")
        if not text.startswith(prefix):
            raise ValueError(f"Embedding input must start with '{prefix}'")

    @property
    def dimension(self) -> int:
        return EMBEDDING_DIMENSION

    def _embed_texts(
        self,
        texts: Sequence[str],
        expected_prefix: str,
    ) -> list[list[float]]:
        """Encode prefixed inputs using mean pooling and L2 normalization."""
        if not texts:
            return []
        for text in texts:
            self._validate_text(text, expected_prefix)

        torch, tokenizer, model = (
            self._model_bundle
            if self._model_bundle is not None
            else _load_model_and_tokenizer(self.model_name)
        )

        embeddings: list[list[float]] = []
        for batch_start in range(0, len(texts), self.batch_size):
            batch = list(texts[batch_start:batch_start + self.batch_size])
            inputs = tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=MAX_INPUT_TOKENS,
                return_tensors="pt",
            )
            with torch.inference_mode():
                output = model(**inputs)

            token_embeddings = output.last_hidden_state
            attention_mask = inputs["attention_mask"].unsqueeze(-1)
            masked_embeddings = token_embeddings * attention_mask
            summed = masked_embeddings.sum(dim=1)
            counts = attention_mask.sum(dim=1).clamp(min=1)
            pooled = summed / counts
            normalized = torch.nn.functional.normalize(pooled, p=2, dim=1)

            for vector in normalized.cpu().tolist():
                if len(vector) != EMBEDDING_DIMENSION:
                    raise ValueError(
                        f"Expected {EMBEDDING_DIMENSION}-dimensional embedding, "
                        f"received {len(vector)} dimensions"
                    )
                if not all(float("-inf") < value < float("inf") for value in vector):
                    raise ValueError("Embedding contains a non-finite value")
                embeddings.append([float(value) for value in vector])

        return embeddings

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """Encode passage inputs using masked mean pooling and L2 normalization."""
        return self._embed_texts(texts, expected_prefix="passage:")

    def embed_chunks(
        self,
        chunks: Sequence[DocumentChunkData],
    ) -> list[list[float]]:
        """Embed chunks using their canonical E5 passage input."""
        return self.embed_texts([chunk.embedding_text for chunk in chunks])

    def embed_query(self, query: str) -> list[float]:
        """Embed a retrieval query with E5's distinct query prefix."""
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Query must be a non-empty string")
        vectors = self._embed_texts(
            [f"query: {query.strip()}"],
            expected_prefix="query:",
        )
        return vectors[0]
