from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.v1.routes.evaluations import get_evaluation_runner
from app.core.security import AuthenticatedUser, create_access_token
from app.database.connection import SessionLocal
from app.database.models import Experiment
from app.main import app
from app.providers.llm import MockLLMProvider
from app.services.evaluation.metrics import citation_correctness_score, ndcg_at_k
from app.services.evaluation.runner import EvaluationCase, EvaluationRunner
from app.services.generation.rag_service import GroundedRAGService
from app.services.search.retrieval_service import RetrievalHit


def test_ndcg_at_k_and_citation_correctness_metrics():
    assert ndcg_at_k(["d1", "d2", "d3"], {"d1", "d2"}, k=3) == pytest.approx(1.0)
    assert ndcg_at_k(["x1", "d1"], {"d1"}, k=2) == pytest.approx(0.6309, abs=1e-3)
    assert citation_correctness_score(
        ["d1"], ["d1", "d2"], should_abstain=False, abstained=False
    ) == 1.0
    assert citation_correctness_score(
        [], ["d1"], should_abstain=True, abstained=True
    ) == 1.0
    assert citation_correctness_score(
        ["d1"], [], should_abstain=True, abstained=False
    ) == 0.0


def test_ablation_runner_isolates_retrieval_vs_generation_quality():
    doc_id = str(uuid4())

    class _FakeRetrieval:
        def search(self, query: str, **_kwargs):
            if "unknown" in query:
                return []
            return [
                RetrievalHit(
                    chunk_id="c1",
                    document_id=doc_id,
                    version_id=str(uuid4()),
                    chunk_index=0,
                    title="Policy",
                    content="Retention is 7 years.",
                    section_path="HR",
                    department="HR",
                    page_numbers=[1],
                    sources_json=None,
                    score=0.95,
                )
            ]

    cases = [
        EvaluationCase(
            case_id="case-1",
            query="What is the retention period?",
            expected_document_ids=[doc_id],
            should_abstain=False,
        ),
        EvaluationCase(
            case_id="case-2",
            query="What is the unknown project?",
            expected_document_ids=[],
            should_abstain=True,
        ),
    ]

    # Variant A: Grounded model cites [C1]
    runner_a = EvaluationRunner(
        GroundedRAGService(
            retrieval_service=_FakeRetrieval(),  # type: ignore[arg-type]
            llm_provider=MockLLMProvider(canned_response="Retention is 7 years [C1]."),
        )
    )
    summary_a = runner_a.run(
        experiment_name="ablation-grounded",
        dataset_name="hr-smoke",
        cases=cases,
        top_k=5,
    )

    # Variant B: Same retriever, but LLM forgets citations -> retrieval stays high, generation drops
    runner_b = EvaluationRunner(
        GroundedRAGService(
            retrieval_service=_FakeRetrieval(),  # type: ignore[arg-type]
            llm_provider=MockLLMProvider(canned_response="Retention is 7 years."),
        )
    )
    summary_b = runner_b.run(
        experiment_name="ablation-uncited",
        dataset_name="hr-smoke",
        cases=cases,
        top_k=5,
    )

    assert summary_a.recall_at_k == 1.0
    assert summary_a.citation_correctness == 1.0
    assert summary_a.abstention_accuracy == 1.0

    assert summary_b.recall_at_k == 1.0
    assert summary_b.citation_correctness == 0.5
    assert summary_b.abstention_accuracy == 0.5


def test_evaluation_endpoints_persist_and_list_runs_in_postgres():
    doc_id = str(uuid4())
    exp_name = f"exp-{uuid4().hex[:8]}"

    class _FakeRetrieval:
        def search(self, _query: str, **_kwargs):
            return [
                RetrievalHit(
                    chunk_id="c1",
                    document_id=doc_id,
                    version_id=str(uuid4()),
                    chunk_index=0,
                    title="Policy",
                    content="Retention is 7 years.",
                    section_path="HR",
                    department="HR",
                    page_numbers=[1],
                    sources_json=None,
                    score=0.95,
                )
            ]

    runner = EvaluationRunner(
        GroundedRAGService(
            retrieval_service=_FakeRetrieval(),  # type: ignore[arg-type]
            llm_provider=MockLLMProvider(canned_response="7 years [C1]."),
        )
    )

    editor_token = create_access_token(
        AuthenticatedUser(
            user_id=uuid4(),
            email="editor@example.com",
            department="Engineering",
            roles=frozenset({"editor"}),
        )
    )

    app.dependency_overrides[get_evaluation_runner] = lambda: runner
    db = SessionLocal()
    try:
        client = TestClient(app)
        assert client.get("/api/v1/evaluations").status_code == 401

        res = client.post(
            "/api/v1/evaluations/run",
            json={
                "experiment_name": exp_name,
                "dataset_name": "smoke-v1",
                "top_k": 5,
                "config": {"model": "mock", "chunk_size": 600},
                "cases": [
                    {
                        "case_id": "c1",
                        "query": "Retention?",
                        "expected_document_ids": [doc_id],
                        "should_abstain": False,
                    }
                ],
            },
            headers={"Authorization": f"Bearer {editor_token}"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["run_id"] is not None
        assert body["ndcg_at_k"] == 1.0
        assert body["citation_correctness"] == 1.0

        list_res = client.get(
            "/api/v1/evaluations",
            headers={"Authorization": f"Bearer {editor_token}"},
        )
        assert list_res.status_code == 200
        assert any(item["experiment_name"] == exp_name for item in list_res.json())
    finally:
        app.dependency_overrides.clear()
        exp = db.query(Experiment).filter(Experiment.name == exp_name).first()
        if exp is not None:
            db.delete(exp)
            db.commit()
        db.close()
