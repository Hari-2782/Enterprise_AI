from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.schemas.chunking import ChunkSource, DocumentChunkData
from app.services.search.index_schema import (
    VECTOR_DIMENSIONS,
    VECTOR_FIELD_NAME,
    build_search_index,
)
from app.services.search.vector_indexing_service import (
    SearchIndexingError,
    VectorIndexingService,
    deterministic_chunk_key,
)


def make_chunk(index=0):
    return DocumentChunkData(
        chunk_index=index,
        content=f"Receipts are required for travel expense {index}.",
        token_count=20,
        section_path="Travel Benefits",
        sources=[
            ChunkSource(
                page_number=2,
                block_index=4,
                char_start=0,
                char_end=42,
            )
        ],
        source_token_start=index * 10,
        source_token_end=index * 10 + 5,
        source_token_count=5,
    )


def make_vector(value=1.0):
    return [value] + [0.0] * (VECTOR_DIMENSIONS - 1)


class FakeSearchClient:
    def __init__(self, fail_once_keys=(), counts=None):
        self.fail_once_keys = set(fail_once_keys)
        self.failed_before = set()
        self.calls = []
        self.counts = list(counts or [])

    def merge_or_upload_documents(self, documents):
        self.calls.append([document.copy() for document in documents])
        results = []
        for document in documents:
            key = document["id"]
            should_fail = (
                key in self.fail_once_keys
                and key not in self.failed_before
            )
            if should_fail:
                self.failed_before.add(key)
            results.append({
                "key": key,
                "succeeded": not should_fail,
                "status_code": 503 if should_fail else 200,
                "error_message": "temporary failure" if should_fail else None,
            })
        return results

    def search(self, **kwargs):
        self.search_kwargs = kwargs
        count = self.counts.pop(0) if self.counts else 0
        return SimpleNamespace(get_count=lambda: count)


def test_schema_has_384_dimension_vector_profile():
    index = build_search_index("test-index")
    vector_field = next(field for field in index.fields if field.name == VECTOR_FIELD_NAME)

    assert index.name == "test-index"
    assert vector_field.vector_search_dimensions == 384
    assert vector_field.searchable is True
    assert index.vector_search.profiles[0].name == "e5-vector-profile"


def test_document_mapping_uses_deterministic_key_and_citations():
    document_id = uuid4()
    version_id = uuid4()
    chunk = make_chunk()
    vector = make_vector()

    first = VectorIndexingService.build_documents(
        document_id,
        version_id,
        "Travel Policy",
        "People Operations",
        [chunk],
        [vector],
    )[0]
    second_key = deterministic_chunk_key(version_id, chunk.chunk_index)

    assert first["id"] == second_key
    assert first["id"] == VectorIndexingService.build_documents(
        document_id,
        version_id,
        "Travel Policy",
        "People Operations",
        [chunk],
        [vector],
    )[0]["id"]
    assert first["embedding_text"] == chunk.embedding_text
    assert first["content_vector"] == vector
    assert first["page_numbers"] == [2]
    assert '"block_index":4' in first["sources_json"]


def test_upsert_retries_only_failed_docs_and_reports_complete_count():
    version_id = uuid4()
    chunks = [make_chunk(0), make_chunk(1), make_chunk(2)]
    failed_key = deterministic_chunk_key(version_id, 1)
    client = FakeSearchClient(fail_once_keys=[failed_key])
    service = VectorIndexingService(
        search_client=client,
        batch_size=3,
        retry_base_seconds=0,
        sleep=lambda _: None,
    )

    summary = service.upsert_chunks(
        document_id=uuid4(),
        version_id=version_id,
        title="Travel Policy",
        department="People Operations",
        chunks=chunks,
        embeddings=[make_vector() for _ in chunks],
    )

    assert summary.complete
    assert summary.expected_count == summary.indexed_count == 3
    assert [len(call) for call in client.calls] == [3, 1]
    assert client.calls[0][1]["id"] == client.calls[1][0]["id"]


def test_repeated_upsert_reuses_document_key():
    version_id = uuid4()
    client = FakeSearchClient()
    service = VectorIndexingService(
        search_client=client,
        retry_base_seconds=0,
        sleep=lambda _: None,
    )
    args = dict(
        document_id=uuid4(),
        version_id=version_id,
        title="Travel Policy",
        department="People Operations",
        chunks=[make_chunk()],
        embeddings=[make_vector()],
    )

    service.upsert_chunks(**args)
    service.upsert_chunks(**args)

    assert client.calls[0][0]["id"] == client.calls[1][0]["id"]


def test_persistent_failure_raises_incomplete_summary():
    version_id = uuid4()
    key = deterministic_chunk_key(version_id, 0)

    class AlwaysFail(FakeSearchClient):
        def merge_or_upload_documents(self, documents):
            return [{
                "key": item["id"],
                "succeeded": False,
                "error_message": "permanent failure",
            } for item in documents]

    service = VectorIndexingService(
        search_client=AlwaysFail(),
        max_attempts=2,
        retry_base_seconds=0,
        sleep=lambda _: None,
    )
    with pytest.raises(SearchIndexingError) as exc_info:
        service.upsert_chunks(
            document_id=uuid4(),
            version_id=version_id,
            title="Travel Policy",
            department="People Operations",
            chunks=[make_chunk()],
            embeddings=[make_vector()],
        )

    assert exc_info.value.summary.failed_keys == (key,)
    assert exc_info.value.summary.errors[key] == "permanent failure"


def test_count_verification_waits_for_expected_index_count():
    client = FakeSearchClient(counts=[1, 2])
    service = VectorIndexingService(
        search_client=client,
        sleep=lambda _: None,
    )

    assert service.verify_indexed_count(
        version_id="version-1",
        expected_count=2,
        timeout_seconds=1,
        poll_interval_seconds=0,
    ) == 2
    assert client.search_kwargs["filter"] == "version_id eq 'version-1'"


def test_index_and_verify_runs_count_validation_after_upsert():
    version_id = uuid4()
    client = FakeSearchClient(counts=[1])

    class FakeEmbeddingService:
        def embed_chunks(self, chunks):
            return [make_vector() for _ in chunks]

    service = VectorIndexingService(
        search_client=client,
        embedding_service=FakeEmbeddingService(),
        sleep=lambda _: None,
    )
    summary = service.index_and_verify_chunks(
        document_id=uuid4(),
        version_id=version_id,
        title="Travel Policy",
        department="People Operations",
        chunks=[make_chunk()],
        count_timeout_seconds=1,
    )

    assert summary.complete
    assert client.search_kwargs["filter"] == f"version_id eq '{version_id}'"


@pytest.mark.parametrize("vector", [[0.0], [float("nan")] + [0.0] * 383])
def test_invalid_embedding_vectors_rejected(vector):
    with pytest.raises(ValueError):
        VectorIndexingService.build_documents(
            uuid4(),
            uuid4(),
            "Travel Policy",
            "People Operations",
            [make_chunk()],
            [vector],
        )


def test_batch_size_respects_search_service_limit():
    with pytest.raises(ValueError):
        VectorIndexingService(batch_size=1001)
