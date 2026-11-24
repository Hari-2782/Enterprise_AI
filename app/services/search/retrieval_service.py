from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any
from uuid import UUID

from azure.search.documents.models import VectorizedQuery

from app.core.security import AuthenticatedUser
from app.database.connection import SessionLocal
from app.services.governance.authorization import build_authorized_versions_statement
from app.services.ingestion.embedding_service import E5EmbeddingService
from app.services.search.index_schema import VECTOR_FIELD_NAME


DEFAULT_CANDIDATE_COUNT = 30
MAX_CANDIDATE_COUNT = 100
MAX_QUERY_LENGTH = 2048
SEARCH_FIELDS = ["title", "content", "section_path"]
RESULT_FIELDS = [
    "id",
    "document_id",
    "version_id",
    "chunk_index",
    "title",
    "content",
    "section_path",
    "department",
    "page_numbers",
    "sources_json",
]


@dataclass(frozen=True)
class RetrievalHit:
    chunk_id: str
    document_id: str
    version_id: str
    chunk_index: int
    title: str
    content: str
    section_path: str | None
    department: str
    page_numbers: list[int]
    sources_json: str | None
    score: float


class HybridRetrievalService:
    """Retrieve only currently published chunks with Azure hybrid search.

    Azure AI Search evaluates full-text BM25 and vector similarity in parallel,
    then combines their rankings with Reciprocal Rank Fusion (RRF).
    PostgreSQL remains the authority for which document versions are active.
    """

    def __init__(
        self,
        search_client: Any | None = None,
        embedding_service: E5EmbeddingService | None = None,
        session_factory=SessionLocal,
    ):
        self.search_client = search_client
        self.embedding_service = embedding_service or E5EmbeddingService()
        self.session_factory = session_factory

    def _get_search_client(self):
        if self.search_client is None:
            from app.services.search.client import get_search_client

            self.search_client = get_search_client()
        return self.search_client

    @staticmethod
    def _escape_odata_string(value: str) -> str:
        return value.replace("'", "''")

    def _active_version_ids(
        self,
        *,
        user: AuthenticatedUser | None = None,
        department: str | None,
        document_id: UUID | None,
        version_id: UUID | None,
    ) -> list[str]:
        statement = build_authorized_versions_statement(
            user=user,
            department=department,
            document_id=document_id,
            version_id=version_id,
        )

        db = self.session_factory()
        try:
            return [str(value) for value in db.scalars(statement).all()]
        finally:
            db.close()

    @staticmethod
    def _build_filter(version_ids: list[str], department: str | None) -> str:
        # search.in keeps the active-version allow-list to one OData clause.
        joined_ids = ",".join(version_ids).replace("'", "''")
        clauses = [f"search.in(version_id, '{joined_ids}', ',')"]
        if department is not None:
            escaped_department = HybridRetrievalService._escape_odata_string(
                department
            )
            clauses.append(f"department eq '{escaped_department}'")
        return " and ".join(clauses)

    @staticmethod
    def _to_hit(item: dict[str, Any]) -> RetrievalHit:
        score = float(item.get("@search.score", 0.0))
        if not isfinite(score):
            raise ValueError("Azure Search returned a non-finite score")
        return RetrievalHit(
            chunk_id=str(item["id"]),
            document_id=str(item["document_id"]),
            version_id=str(item["version_id"]),
            chunk_index=int(item["chunk_index"]),
            title=str(item.get("title") or ""),
            content=str(item.get("content") or ""),
            section_path=item.get("section_path"),
            department=str(item.get("department") or ""),
            page_numbers=[int(page) for page in item.get("page_numbers", [])],
            sources_json=item.get("sources_json"),
            score=score,
        )

    def search(
        self,
        query: str,
        *,
        user: AuthenticatedUser | None = None,
        top_k: int = 5,
        candidate_count: int = DEFAULT_CANDIDATE_COUNT,
        department: str | None = None,
        document_id: UUID | None = None,
        version_id: UUID | None = None,
    ) -> list[RetrievalHit]:
        normalized_query = query.strip() if isinstance(query, str) else ""
        if not normalized_query:
            raise ValueError("Query must be a non-empty string")
        if len(normalized_query) > MAX_QUERY_LENGTH:
            raise ValueError(
                f"Query must be at most {MAX_QUERY_LENGTH} characters"
            )
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        if candidate_count < top_k:
            raise ValueError("candidate_count must be at least top_k")
        if candidate_count > MAX_CANDIDATE_COUNT:
            raise ValueError(
                f"candidate_count cannot exceed {MAX_CANDIDATE_COUNT}"
            )

        normalized_department = department.strip() if department else None
        if department is not None and not normalized_department:
            raise ValueError("department must not be blank")

        active_versions = self._active_version_ids(
            user=user,
            department=normalized_department,
            document_id=document_id,
            version_id=version_id,
        )
        if not active_versions:
            return []

        query_vector = self.embedding_service.embed_query(normalized_query)
        if not query_vector or not all(isfinite(float(value)) for value in query_vector):
            raise ValueError("Query embedding must contain finite values")

        vector_query = VectorizedQuery(
            vector=query_vector,
            k_nearest_neighbors=candidate_count,
            fields=VECTOR_FIELD_NAME,
        )
        response = self._get_search_client().search(
            search_text=normalized_query,
            search_fields=SEARCH_FIELDS,
            vector_queries=[vector_query],
            vector_filter_mode="preFilter",
            filter=self._build_filter(active_versions, normalized_department),
            select=RESULT_FIELDS,
            top=candidate_count,
            include_total_count=False,
        )
        hits = [self._to_hit(item) for item in response]
        return hits[:top_k]
