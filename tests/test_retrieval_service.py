from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.database.models import Document, DocumentVersion
from app.services.search.retrieval_service import HybridRetrievalService


class FakeEmbeddingService:
    def __init__(self):
        self.queries = []

    def embed_query(self, query):
        self.queries.append(query)
        return [0.25] * 384


class FakeSearchClient:
    def __init__(self, response=None):
        self.kwargs = None
        self.response = response or []

    def search(self, **kwargs):
        self.kwargs = kwargs
        return iter(self.response)


def make_database():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, autoflush=False)


def add_version(session_factory, *, department, status, current=True):
    document_id = uuid4()
    version_id = uuid4()
    with session_factory() as db:
        document = Document(
            id=document_id,
            title="Expense policy",
            department=department,
        )
        db.add(document)
        db.flush()
        version = DocumentVersion(
            id=version_id,
            document_id=document_id,
            version_number=1,
            filename="policy.txt",
            content_hash=uuid4().hex,
            status=status,
            expected_chunks=1,
            indexed_chunks=1 if status == "published" else 0,
        )
        db.add(version)
        db.flush()
        if current:
            document.current_version_id = version_id
        db.commit()
    return document_id, version_id


def make_search_item(version_id, document_id, index):
    return {
        "id": f"chunk-{index}",
        "document_id": str(document_id),
        "version_id": str(version_id),
        "chunk_index": index,
        "title": "Expense policy",
        "content": "Submit receipts for approved business travel.",
        "section_path": "Travel > Receipts",
        "department": "People's Operations",
        "page_numbers": [1, 2],
        "sources_json": "[]",
        "@search.score": 0.04 - index / 1000,
    }


def test_hybrid_search_uses_current_published_scope_and_rrf_query():
    engine, session_factory = make_database()
    active_document, active_version = add_version(
        session_factory,
        department="People's Operations",
        status="published",
    )
    _, old_version = add_version(
        session_factory,
        department="People's Operations",
        status="published",
        current=False,
    )
    _, processing_version = add_version(
        session_factory,
        department="People's Operations",
        status="processing",
    )
    embedding = FakeEmbeddingService()
    response = [
        make_search_item(active_version, active_document, index)
        for index in range(4)
    ]
    search_client = FakeSearchClient(response)
    service = HybridRetrievalService(
        search_client=search_client,
        embedding_service=embedding,
        session_factory=session_factory,
    )

    try:
        hits = service.search(
            "  receipt reimbursement  ",
            top_k=2,
            department="People's Operations",
        )

        assert len(hits) == 2
        assert hits[0].chunk_id == "chunk-0"
        assert embedding.queries == ["receipt reimbursement"]
        kwargs = search_client.kwargs
        assert kwargs["search_text"] == "receipt reimbursement"
        assert kwargs["search_fields"] == ["title", "content", "section_path"]
        assert kwargs["top"] == 30
        assert kwargs["vector_filter_mode"] == "preFilter"
        assert active_version.hex not in kwargs["filter"]
        assert str(active_version) in kwargs["filter"]
        assert str(old_version) not in kwargs["filter"]
        assert str(processing_version) not in kwargs["filter"]
        assert "department eq 'People''s Operations'" in kwargs["filter"]
        vector_query = kwargs["vector_queries"][0]
        assert vector_query.k_nearest_neighbors == 30
        assert vector_query.fields == "content_vector"
        assert len(vector_query.vector) == 384
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_hybrid_search_returns_no_results_for_unpublished_version():
    engine, session_factory = make_database()
    _, version_id = add_version(
        session_factory,
        department="Engineering",
        status="processing",
    )
    search_client = FakeSearchClient()
    service = HybridRetrievalService(
        search_client=search_client,
        embedding_service=FakeEmbeddingService(),
        session_factory=session_factory,
    )

    try:
        assert service.search("deployment", version_id=version_id) == []
        assert search_client.kwargs is None
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.mark.parametrize(
    ("query", "top_k", "candidate_count"),
    [
        ("   ", 5, 30),
        ("deployment", 0, 30),
        ("deployment", 5, 4),
        ("deployment", 5, 101),
    ],
)
def test_hybrid_search_rejects_invalid_query_parameters(
    query,
    top_k,
    candidate_count,
):
    service = HybridRetrievalService(
        search_client=FakeSearchClient(),
        embedding_service=FakeEmbeddingService(),
    )
    with pytest.raises(ValueError):
        service.search(
            query,
            top_k=top_k,
            candidate_count=candidate_count,
        )
