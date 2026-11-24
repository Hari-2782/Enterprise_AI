from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import AuthenticatedUser
from app.database.models import EvaluationRun, Experiment
from app.services.evaluation.metrics import (
    citation_correctness_score,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from app.services.generation.rag_service import GroundedRAGService


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    query: str
    expected_document_ids: list[str] = field(default_factory=list)
    should_abstain: bool = False


@dataclass(frozen=True)
class CaseEvaluationResult:
    case_id: str
    query: str
    precision_at_k: float
    recall_at_k: float
    reciprocal_rank: float
    ndcg_at_k: float
    citation_correctness: float
    abstention_correct: bool
    abstained: bool
    latency_ms: float
    total_tokens: int


@dataclass(frozen=True)
class EvaluationSummary:
    run_id: UUID | None
    experiment_name: str
    dataset_name: str
    total_cases: int
    precision_at_k: float
    recall_at_k: float
    mrr: float
    ndcg_at_k: float
    citation_correctness: float
    abstention_accuracy: float
    avg_latency_ms: float
    total_tokens: int
    case_results: list[CaseEvaluationResult]


class EvaluationRunner:
    """Execute labelled RAG evaluation datasets and optionally persist runs."""

    def __init__(self, rag_service: GroundedRAGService) -> None:
        self.rag_service = rag_service

    def run(
        self,
        *,
        experiment_name: str,
        dataset_name: str,
        cases: list[EvaluationCase],
        top_k: int = 5,
        config: dict[str, Any] | None = None,
        user: AuthenticatedUser | None = None,
        db: Session | None = None,
    ) -> EvaluationSummary:
        if not cases:
            raise ValueError("Evaluation dataset must contain at least one case")

        case_results: list[CaseEvaluationResult] = []
        retrieval_cases = 0
        sum_p = 0.0
        sum_r = 0.0
        sum_rr = 0.0
        sum_ndcg = 0.0
        sum_cit = 0.0
        abstention_hits = 0
        sum_latency = 0.0
        total_tokens = 0

        for case in cases:
            hits = self.rag_service.retrieval_service.search(
                case.query,
                user=user,
                top_k=top_k,
            )
            retrieved_doc_ids = [hit.document_id for hit in hits]

            answer = self.rag_service.answer(
                case.query,
                user=user,
                top_k=top_k,
            )
            cited_doc_ids = [hit.document_id for _key, hit in answer.citations]

            if case.expected_document_ids:
                p_k = precision_at_k(retrieved_doc_ids, case.expected_document_ids, top_k)
                r_k = recall_at_k(retrieved_doc_ids, case.expected_document_ids, top_k)
                rr = reciprocal_rank(retrieved_doc_ids, case.expected_document_ids)
                n_k = ndcg_at_k(retrieved_doc_ids, case.expected_document_ids, top_k)
                retrieval_cases += 1
                sum_p += p_k
                sum_r += r_k
                sum_rr += rr
                sum_ndcg += n_k
            else:
                p_k = r_k = rr = n_k = 0.0

            cit_score = citation_correctness_score(
                cited_doc_ids,
                case.expected_document_ids,
                should_abstain=case.should_abstain,
                abstained=answer.abstained,
            )
            abs_ok = answer.abstained == case.should_abstain
            sum_cit += cit_score
            if abs_ok:
                abstention_hits += 1
            sum_latency += answer.latency_ms
            total_tokens += answer.usage.total_tokens

            case_results.append(
                CaseEvaluationResult(
                    case_id=case.case_id,
                    query=case.query,
                    precision_at_k=round(p_k, 4),
                    recall_at_k=round(r_k, 4),
                    reciprocal_rank=round(rr, 4),
                    ndcg_at_k=round(n_k, 4),
                    citation_correctness=round(cit_score, 4),
                    abstention_correct=abs_ok,
                    abstained=answer.abstained,
                    latency_ms=answer.latency_ms,
                    total_tokens=answer.usage.total_tokens,
                )
            )

        n_cases = len(cases)
        denom_ret = retrieval_cases or 1
        avg_p = round(sum_p / denom_ret, 4) if retrieval_cases else 0.0
        avg_r = round(sum_r / denom_ret, 4) if retrieval_cases else 0.0
        mrr = round(sum_rr / denom_ret, 4) if retrieval_cases else 0.0
        avg_ndcg = round(sum_ndcg / denom_ret, 4) if retrieval_cases else 0.0
        avg_cit = round(sum_cit / n_cases, 4)
        abs_acc = round(abstention_hits / n_cases, 4)
        avg_lat = round(sum_latency / n_cases, 2)

        run_id: UUID | None = None
        if db is not None:
            experiment = db.scalar(
                select(Experiment).where(Experiment.name == experiment_name)
            )
            if experiment is None:
                experiment = Experiment(
                    name=experiment_name,
                    config_json=json.dumps(config or {}, sort_keys=True),
                )
                db.add(experiment)
                db.flush()

            db_run = EvaluationRun(
                experiment_id=experiment.id,
                dataset_name=dataset_name,
                status="completed",
                total_cases=n_cases,
                precision_at_k=avg_p,
                recall_at_k=avg_r,
                mrr=mrr,
                ndcg_at_k=avg_ndcg,
                citation_correctness=avg_cit,
                abstention_accuracy=abs_acc,
                avg_latency_ms=avg_lat,
                total_tokens=total_tokens,
                results_json=json.dumps(
                    [r.__dict__ for r in case_results],
                    sort_keys=True,
                ),
            )
            db.add(db_run)
            db.commit()
            db.refresh(db_run)
            run_id = db_run.id

        return EvaluationSummary(
            run_id=run_id,
            experiment_name=experiment_name,
            dataset_name=dataset_name,
            total_cases=n_cases,
            precision_at_k=avg_p,
            recall_at_k=avg_r,
            mrr=mrr,
            ndcg_at_k=avg_ndcg,
            citation_correctness=avg_cit,
            abstention_accuracy=abs_acc,
            avg_latency_ms=avg_lat,
            total_tokens=total_tokens,
            case_results=case_results,
        )
