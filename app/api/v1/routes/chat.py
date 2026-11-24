import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.security import AuthenticatedUser, get_current_user
from app.database.connection import get_db
from app.database.models import ChatMessageRecord, ChatSession, User
from app.providers.llm import LLMProviderError, get_llm_provider
from app.schemas.chat import (
    ChatHistoryMessage,
    ChatRequest,
    ChatResponse,
    ChatSessionSummary,
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


def _persist_chat_turn(
    db: Session,
    *,
    user_id: UUID,
    requested_session_id: UUID | None,
    query: str,
    answer: str,
    abstained: bool,
    abstention_reason: str | None,
    citations: list[CitationResponse],
    model: str,
    provider: str,
    prompt_version: str,
    total_tokens: int,
    latency_ms: float,
) -> UUID | None:
    if db.get(User, user_id) is None:
        return None

    session: ChatSession | None = None
    if requested_session_id is not None:
        session = db.get(ChatSession, requested_session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Chat session not found")
        if session.user_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized for this chat session")
    else:
        clean_title = query.strip()[:80] or "New Chat"
        session = ChatSession(user_id=user_id, title=clean_title)
        db.add(session)
        db.flush()

    record = ChatMessageRecord(
        session_id=session.id,
        query=query,
        answer=answer,
        abstained=abstained,
        abstention_reason=abstention_reason,
        citations_json=json.dumps([c.model_dump(mode="json") for c in citations]),
        model=model,
        provider=provider,
        prompt_version=prompt_version,
        total_tokens=total_tokens,
        latency_ms=latency_ms,
    )
    db.add(record)
    db.commit()
    return session.id


@router.post("", response_model=ChatResponse)
def grounded_chat(
    payload: ChatRequest,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
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

    citations = [
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
    ]

    session_id = _persist_chat_turn(
        db,
        user_id=user.user_id,
        requested_session_id=payload.session_id,
        query=result.query,
        answer=result.answer,
        abstained=result.abstained,
        abstention_reason=result.abstention_reason,
        citations=citations,
        model=result.model,
        provider=result.provider,
        prompt_version=result.prompt_version,
        total_tokens=result.usage.total_tokens,
        latency_ms=result.latency_ms,
    )

    return ChatResponse(
        query=result.query,
        answer=result.answer,
        abstained=result.abstained,
        abstention_reason=result.abstention_reason,
        citations=citations,
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
        session_id=session_id,
    )


@router.get("/sessions", response_model=list[ChatSessionSummary])
def list_chat_sessions(
    limit: int = Query(default=30, ge=1, le=100),
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        select(ChatSession)
        .where(ChatSession.user_id == user.user_id)
        .order_by(desc(ChatSession.updated_at))
        .limit(limit)
    ).all()
    return [
        ChatSessionSummary(
            id=row.id,
            title=row.title,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.get("/sessions/{session_id}", response_model=list[ChatHistoryMessage])
def get_chat_session_messages(
    session_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = db.get(ChatSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    if session.user_id != user.user_id:
        raise HTTPException(status_code=403, detail="Not authorized for this chat session")

    rows = db.scalars(
        select(ChatMessageRecord)
        .where(ChatMessageRecord.session_id == session_id)
        .order_by(ChatMessageRecord.created_at)
    ).all()
    return [
        ChatHistoryMessage(
            id=row.id,
            query=row.query,
            answer=row.answer,
            abstained=row.abstained,
            abstention_reason=row.abstention_reason,
            citations=[
                CitationResponse(**item)
                for item in json.loads(row.citations_json or "[]")
            ],
            model=row.model,
            provider=row.provider,
            prompt_version=row.prompt_version,
            total_tokens=row.total_tokens,
            latency_ms=row.latency_ms,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_chat_session(
    session_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = db.get(ChatSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    if session.user_id != user.user_id:
        raise HTTPException(status_code=403, detail="Not authorized for this chat session")
    db.delete(session)
    db.commit()
