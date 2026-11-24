from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.v1.routes.search import get_retrieval_service
from app.core.security import AuthenticatedUser, get_current_user
from app.main import app
from app.services.search.retrieval_service import RetrievalHit


class FakeRetrievalService:
    def __init__(self):
        self.kwargs = None

    def search(self, query, **kwargs):
        self.kwargs = {"query": query, **kwargs}
        return [
            RetrievalHit(
                chunk_id="chunk-a",
                document_id=str(uuid4()),
                version_id=str(uuid4()),
                chunk_index=0,
                title="Travel policy",
                content="Receipts are required.",
                section_path="Travel > Reimbursement",
                department="People Operations",
                page_numbers=[2],
                sources_json="[]",
                score=0.031,
            )
        ]


def test_hybrid_search_endpoint_returns_results_and_request_id():
    service = FakeRetrievalService()
    test_user = AuthenticatedUser(
        user_id=uuid4(),
        email="eng@example.com",
        department="People Operations",
        roles=frozenset({"viewer"}),
    )
    app.dependency_overrides[get_retrieval_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/search",
                json={
                    "query": " receipts ",
                    "top_k": 3,
                    "candidate_count": 30,
                    "department": "People Operations",
                },
                headers={"X-Request-ID": "retrieval-test-123"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["query"] == "receipts"
        assert body["request_id"] == "retrieval-test-123"
        assert body["candidate_count"] == 30
        assert body["results"][0]["chunk_id"] == "chunk-a"
        assert body["results"][0]["page_numbers"] == [2]
        assert service.kwargs == {
            "query": " receipts ",
            "user": test_user,
            "top_k": 3,
            "candidate_count": 30,
            "department": "People Operations",
            "document_id": None,
            "version_id": None,
        }
    finally:
        app.dependency_overrides.pop(get_retrieval_service, None)
        app.dependency_overrides.pop(get_current_user, None)


def test_hybrid_search_endpoint_rejects_invalid_candidate_window():
    test_user = AuthenticatedUser(
        user_id=uuid4(),
        email="eng@example.com",
        department="People Operations",
        roles=frozenset({"viewer"}),
    )
    app.dependency_overrides[get_retrieval_service] = FakeRetrievalService
    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/search",
                json={"query": "receipts", "top_k": 10, "candidate_count": 5},
            )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_retrieval_service, None)
        app.dependency_overrides.pop(get_current_user, None)
