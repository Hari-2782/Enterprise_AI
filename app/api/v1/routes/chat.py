import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.security import AuthenticatedUser, get_current_user
from app.providers.llm import LLMProviderError, get_llm_provider
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    CitationResponse,
    TokenUsageResponse,
)
from app.services.generation.rag_service import GroundedRAGService
from app.services.search.retrieval_service import HybridRetrievalService


logger = logging.getLogger("enterprise-ai.chat")
router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


def get_rag_service() -> GroundedRAGService:
    return GroundedRAGService(
        retrieval_service=HybridRetrievalService(),
        llm_provider=get_llm_provider(),
    )


@router.post("", response_model=ChatResponse)
def grounded_chat(
    payload: ChatRequest,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
    service: GroundedRAGService = Depends(get_rag_service),
):
    try:
        result = service.answer(
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
    except LLMProviderError as exc:
        logger.exception(
            "chat_llm_provider_failed",
            extra={
                "event": "chat_llm_provider_failed",
                "request_id": request.state.request_id,
            },
        )
        raise HTTPException(
            status_code=503,
            detail="LLM provider is temporarily unavailable",
        ) from exc
    except Exception as exc:
        logger.exception(
            "chat_generation_failed",
            extra={
                "event": "chat_generation_failed",
                "request_id": request.state.request_id,
            },
        )
        raise HTTPException(
            status_code=503,
            detail="Chat service is temporarily unavailable",
        ) from exc

    return ChatResponse(
        query=result.query,
        answer=result.answer,
        abstained=result.abstained,
        abstention_reason=result.abstention_reason,
        citations=[
            CitationResponse(
                citation_key=key,
                chunk_id=hit.chunk_id,
                document_id=hit.document_id,
                version_id=hit.version_id,
                title=hit.title,
                section_path=hit.section_path,
                page_numbers=hit.page_numbers,
                score=hit.score,
            )
            for key, hit in result.citations
        ],
        model=result.model,
        provider=result.provider,
        prompt_version=result.prompt_version,
        used_fallback=result.used_fallback,
        usage=TokenUsageResponse(
            prompt_tokens=result.usage.prompt_tokens,
            completion_tokens=result.usage.completion_tokens,
            total_tokens=result.usage.total_tokens,
        ),
        latency_ms=result.latency_ms,
        request_id=request.state.request_id,
    )
