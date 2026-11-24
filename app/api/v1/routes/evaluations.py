from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.core.security import AuthenticatedUser, get_current_user, require_roles
from app.database.connection import get_db
from app.database.models import EvaluationRun
from app.providers.llm import get_llm_provider
from app.schemas.evaluation import EvaluationRunResponse, RunEvaluationRequest
from app.services.evaluation.runner import EvaluationCase, EvaluationRunner
from app.services.generation.rag_service import GroundedRAGService
from app.services.search.retrieval_service import HybridRetrievalService


router = APIRouter(prefix="/api/v1/evaluations", tags=["evaluations"])


def get_evaluation_runner() -> EvaluationRunner:
    return EvaluationRunner(
        GroundedRAGService(
            retrieval_service=HybridRetrievalService(),
            llm_provider=get_llm_provider(),
        )
    )


@router.post("/run", response_model=EvaluationRunResponse)
def run_evaluation(
    payload: RunEvaluationRequest,
    user: AuthenticatedUser = Depends(require_roles("admin", "editor")),
    db: Session = Depends(get_db),
    runner: EvaluationRunner = Depends(get_evaluation_runner),
):
    cases = [
        EvaluationCase(
            case_id=c.case_id,
            query=c.query,
            expected_document_ids=c.expected_document_ids,
            should_abstain=c.should_abstain,
        )
        for c in payload.cases
    ]
    summary = runner.run(
        experiment_name=payload.experiment_name,
        dataset_name=payload.dataset_name,
        cases=cases,
        top_k=payload.top_k,
        config=payload.config,
        user=user,
        db=db,
    )
    return EvaluationRunResponse(
        run_id=summary.run_id,
        experiment_name=summary.experiment_name,
        dataset_name=summary.dataset_name,
        total_cases=summary.total_cases,
        precision_at_k=summary.precision_at_k,
        recall_at_k=summary.recall_at_k,
        mrr=summary.mrr,
        ndcg_at_k=summary.ndcg_at_k,
        citation_correctness=summary.citation_correctness,
        abstention_accuracy=summary.abstention_accuracy,
        avg_latency_ms=summary.avg_latency_ms,
        total_tokens=summary.total_tokens,
    )


@router.get("", response_model=list[EvaluationRunResponse])
def list_evaluations(
    limit: int = Query(default=20, ge=1, le=100),
    _user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    runs = db.scalars(
        select(EvaluationRun)
        .options(selectinload(EvaluationRun.experiment))
        .order_by(desc(EvaluationRun.created_at))
        .limit(limit)
    ).all()
    return [
        EvaluationRunResponse(
            run_id=run.id,
            experiment_name=run.experiment.name,
            dataset_name=run.dataset_name,
            status=run.status,
            total_cases=run.total_cases,
            precision_at_k=run.precision_at_k,
            recall_at_k=run.recall_at_k,
            mrr=run.mrr,
            ndcg_at_k=run.ndcg_at_k,
            citation_correctness=run.citation_correctness,
            abstention_accuracy=run.abstention_accuracy,
            avg_latency_ms=run.avg_latency_ms,
            total_tokens=run.total_tokens,
            created_at=run.created_at,
        )
        for run in runs
    ]
