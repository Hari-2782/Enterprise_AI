import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from typing import Sequence
from uuid import UUID

from app.schemas.chunking import DocumentChunkData
from app.services.search.index_schema import (
    VECTOR_DIMENSIONS,
    create_or_update_search_index,
)


@dataclass(frozen=True)
class IndexingSummary:
    expected_count: int
    indexed_count: int
    failed_keys: tuple[str, ...] = ()
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def complete(self) -> bool:
        return self.expected_count == self.indexed_count and not self.failed_keys


class SearchIndexingError(RuntimeError):
    def __init__(self, summary: IndexingSummary):
        self.summary = summary
        super().__init__(
            f"Indexed {summary.indexed_count} of {summary.expected_count} "
            f"chunks; {len(summary.failed_keys)} failed"
        )


def deterministic_chunk_key(version_id: UUID | str, chunk_index: int) -> str:
    """Return a stable Azure key for this version and chunk position."""
    if chunk_index < 0:
        raise ValueError("chunk_index cannot be negative")
    source = f"{version_id}:{chunk_index}".encode("utf-8")
    return hashlib.sha256(source).hexdigest()


class VectorIndexingService:
    """Create and verify deterministic, retryable Azure Search upserts."""

    def __init__(
        self,
        search_client=None,
        embedding_service=None,
        index_name: str | None = None,
        batch_size: int = 100,
        max_attempts: int = 3,
        retry_base_seconds: float = 0.25,
        sleep=time.sleep,
    ):
        if batch_size <= 0 or batch_size > 1000:
            raise ValueError("batch_size must be between 1 and 1000")
        if max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        self.search_client = search_client
        self.embedding_service = embedding_service
        self.index_name = index_name
        self.batch_size = batch_size
        self.max_attempts = max_attempts
        self.retry_base_seconds = retry_base_seconds
        self.sleep = sleep

    def _get_search_client(self):
        if self.search_client is None:
            from app.services.search.client import get_search_client

            self.search_client = get_search_client(self._index_name())
        return self.search_client

    def _index_name(self) -> str:
        if self.index_name:
            return self.index_name
        from app.core.config import settings

        return settings.azure_search_index_name

    def ensure_index(self, index_client=None):
        """Create or update the configured Azure vector index schema."""
        if index_client is None:
            from app.services.search.client import get_search_index_client

            index_client = get_search_index_client()
        return create_or_update_search_index(index_client, self._index_name())

    @staticmethod
    def _validate_vector(vector: Sequence[float]) -> list[float]:
        if len(vector) != VECTOR_DIMENSIONS:
            raise ValueError(
                f"Expected {VECTOR_DIMENSIONS}-dimensional vector, "
                f"received {len(vector)} dimensions"
            )
        normalized = [float(value) for value in vector]
        if not all(math.isfinite(value) for value in normalized):
            raise ValueError("Vector contains a non-finite value")
        return normalized

    @classmethod
    def build_documents(
        cls,
        document_id: UUID | str,
        version_id: UUID | str,
        title: str,
        department: str,
        chunks: Sequence[DocumentChunkData],
        embeddings: Sequence[Sequence[float]],
    ) -> list[dict]:
        if len(chunks) != len(embeddings):
            raise ValueError("Each chunk must have exactly one embedding")
        if not title.strip() or not department.strip():
            raise ValueError("title and department must be non-empty")

        documents = []
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            sources = [source.model_dump(mode="json") for source in chunk.sources]
            documents.append({
                "id": deterministic_chunk_key(version_id, chunk.chunk_index),
                "document_id": str(document_id),
                "version_id": str(version_id),
                "chunk_index": chunk.chunk_index,
                "title": title,
                "content": chunk.content,
                "embedding_text": chunk.embedding_text,
                "section_path": chunk.section_path,
                "department": department,
                "token_count": chunk.token_count,
                "source_token_start": chunk.source_token_start,
                "source_token_end": chunk.source_token_end,
                "source_token_count": chunk.source_token_count,
                "page_numbers": sorted({source.page_number for source in chunk.sources}),
                "sources_json": json.dumps(sources, separators=(",", ":")),
                "content_vector": cls._validate_vector(embedding),
            })
        return documents

    def index_chunks(
        self,
        document_id: UUID | str,
        version_id: UUID | str,
        title: str,
        department: str,
        chunks: Sequence[DocumentChunkData],
    ) -> IndexingSummary:
        """Embed chunks and upsert them with stable version-scoped keys."""
        if self.embedding_service is None:
            from app.services.ingestion.embedding_service import E5EmbeddingService

            self.embedding_service = E5EmbeddingService()
        embeddings = self.embedding_service.embed_chunks(chunks)
        return self.upsert_chunks(
            document_id=document_id,
            version_id=version_id,
            title=title,
            department=department,
            chunks=chunks,
            embeddings=embeddings,
        )

    def index_and_verify_chunks(
        self,
        document_id: UUID | str,
        version_id: UUID | str,
        title: str,
        department: str,
        chunks: Sequence[DocumentChunkData],
        count_timeout_seconds: float = 10.0,
        count_poll_interval_seconds: float = 0.5,
    ) -> IndexingSummary:
        """Embed, upsert, then verify all chunks are visible before publish."""
        summary = self.index_chunks(
            document_id=document_id,
            version_id=version_id,
            title=title,
            department=department,
            chunks=chunks,
        )
        self.verify_indexed_count(
            version_id=version_id,
            expected_count=summary.expected_count,
            timeout_seconds=count_timeout_seconds,
            poll_interval_seconds=count_poll_interval_seconds,
        )
        return summary

    def upsert_chunks(
        self,
        document_id: UUID | str,
        version_id: UUID | str,
        title: str,
        department: str,
        chunks: Sequence[DocumentChunkData],
        embeddings: Sequence[Sequence[float]],
    ) -> IndexingSummary:
        documents = self.build_documents(
            document_id=document_id,
            version_id=version_id,
            title=title,
            department=department,
            chunks=chunks,
            embeddings=embeddings,
        )
        if not documents:
            return IndexingSummary(expected_count=0, indexed_count=0)

        client = self._get_search_client()
        indexed_keys: set[str] = set()
        errors: dict[str, str] = {}

        for batch_start in range(0, len(documents), self.batch_size):
            pending = documents[batch_start:batch_start + self.batch_size]
            batch_errors: dict[str, str] = {}

            for attempt in range(1, self.max_attempts + 1):
                try:
                    results = client.merge_or_upload_documents(
                        documents=pending
                    )
                except Exception as exc:
                    batch_errors = {
                        item["id"]: f"{type(exc).__name__}: {exc}"
                        for item in pending
                    }
                    if attempt < self.max_attempts:
                        self.sleep(self.retry_base_seconds * (2 ** (attempt - 1)))
                        continue
                    break

                result_by_key = {
                    self._result_value(result, "key"): result
                    for result in results
                }
                retry_pending = []
                batch_errors = {}
                for item in pending:
                    result = result_by_key.get(item["id"])
                    succeeded = bool(
                        result is not None
                        and self._result_value(result, "succeeded", False)
                    )
                    if succeeded:
                        indexed_keys.add(item["id"])
                    else:
                        retry_pending.append(item)
                        batch_errors[item["id"]] = self._result_error(result)

                if not retry_pending:
                    break
                pending = retry_pending
                if attempt < self.max_attempts:
                    self.sleep(self.retry_base_seconds * (2 ** (attempt - 1)))

            errors.update(batch_errors)

        failed_keys = tuple(
            document["id"]
            for document in documents
            if document["id"] not in indexed_keys
        )
        summary = IndexingSummary(
            expected_count=len(documents),
            indexed_count=len(indexed_keys),
            failed_keys=failed_keys,
            errors={key: errors.get(key, "Index operation failed") for key in failed_keys},
        )
        if not summary.complete:
            raise SearchIndexingError(summary)
        return summary

    @staticmethod
    def _result_value(result, name: str, default=None):
        if result is None:
            return default
        if isinstance(result, dict):
            return result.get(name, default)
        return getattr(result, name, default)

    @classmethod
    def _result_error(cls, result) -> str:
        if result is None:
            return "No indexing result returned for document"
        message = cls._result_value(result, "error_message")
        status = cls._result_value(result, "status_code")
        return str(message or f"Indexing failed (status {status})")

    def verify_indexed_count(
        self,
        version_id: UUID | str,
        expected_count: int,
        timeout_seconds: float = 10.0,
        poll_interval_seconds: float = 0.5,
    ) -> int:
        """Poll the version filter until its indexed count is visible."""
        if expected_count < 0:
            raise ValueError("expected_count cannot be negative")
        version = str(version_id).replace("'", "''")
        filter_expression = f"version_id eq '{version}'"
        deadline = time.monotonic() + timeout_seconds

        while True:
            results = self._get_search_client().search(
                search_text="*",
                filter=filter_expression,
                include_total_count=True,
            )
            count = results.get_count()
            if count == expected_count:
                return count
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"Azure Search reports {count} indexed chunks for version "
                    f"{version_id}; expected {expected_count}"
                )
            self.sleep(min(poll_interval_seconds, max(0, deadline - time.monotonic())))
