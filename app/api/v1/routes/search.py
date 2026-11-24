import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.security import AuthenticatedUser, get_current_user
from app.schemas.retrieval import (
    RetrievalHitResponse,
    SearchRequest,
    SearchResponse,
)
from app.services.search.retrieval_service import HybridRetrievalService


logger = logging.getLogger("enterprise-ai.retrieval")
router = APIRouter(prefix="/api/v1/search", tags=["search"])


def get_retrieval_service() -> HybridRetrievalService:
    return HybridRetrievalService()


@router.post("", response_model=SearchResponse)
def hybrid_search(
    payload: SearchRequest,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
    service: HybridRetrievalService = Depends(get_retrieval_service),
):
    try:
        hits = service.search(
            payload.query,
            user=user,
            top_k=payload.top_k,
            candidate_count=payload.candidate_count,
            department=payload.department,
            document_id=payload.document_id,
            version_id=payload.version_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception(
            "hybrid_search_failed",
            extra={
                "event": "hybrid_search_failed",
                "request_id": request.state.request_id,
            },
        )
        raise HTTPException(
            status_code=503,
            detail="Search is temporarily unavailable",
        ) from exc

    return SearchResponse(
        query=payload.query.strip(),
        candidate_count=payload.candidate_count,
        results=[
            RetrievalHitResponse(
                chunk_id=hit.chunk_id,
                document_id=hit.document_id,
                version_id=hit.version_id,
                chunk_index=hit.chunk_index,
                title=hit.title,
                content=hit.content,
                section_path=hit.section_path,
                department=hit.department,
                page_numbers=hit.page_numbers,
                sources_json=hit.sources_json,
                score=hit.score,
            )
            for hit in hits
        ],
        request_id=request.state.request_id,
    )
