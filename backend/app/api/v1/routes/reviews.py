from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.security import AuthenticatedUser, get_current_user, require_roles
from app.database.connection import get_db
from app.database.models import ReviewTask
from app.schemas.reviews import (
    CreateFeedbackRequest,
    CreateReviewRequest,
    FeedbackResponse,
    ResolveReviewRequest,
    ReviewTaskResponse,
)
from app.services.governance.reviews import (
    ReviewConflictError,
    create_feedback,
    create_review_task,
    resolve_review_task,
)


router = APIRouter(prefix="/api/v1", tags=["reviews"])


def _to_review_response(task: ReviewTask) -> ReviewTaskResponse:
    return ReviewTaskResponse(
        id=task.id,
        request_id=task.request_id,
        user_id=task.user_id,
        query=task.query,
        proposed_answer=task.proposed_answer,
        abstention_reason=task.abstention_reason,
        status=task.status,
        reviewer_id=task.reviewer_id,
        reviewer_notes=task.reviewer_notes,
        resolved_at=task.resolved_at,
        created_at=task.created_at,
    )


@router.post(
    "/reviews",
    response_model=ReviewTaskResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_review(
    payload: CreateReviewRequest,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = create_review_task(
        db,
        request_id=request.state.request_id,
        user_id=user.user_id,
        query=payload.query,
        proposed_answer=payload.proposed_answer,
        abstention_reason=payload.abstention_reason,
        escalate=payload.escalate,
    )
    return _to_review_response(task)


@router.get("/reviews", response_model=list[ReviewTaskResponse])
def list_reviews(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    _user: AuthenticatedUser = Depends(require_roles("admin", "auditor", "editor")),
    db: Session = Depends(get_db),
):
    stmt = select(ReviewTask).order_by(desc(ReviewTask.created_at)).limit(limit)
    if status_filter is not None:
        stmt = stmt.where(ReviewTask.status == status_filter)
    return [_to_review_response(row) for row in db.scalars(stmt).all()]


@router.post("/reviews/{review_id}/resolve", response_model=ReviewTaskResponse)
def resolve_review(
    review_id: UUID,
    payload: ResolveReviewRequest,
    request: Request,
    reviewer: AuthenticatedUser = Depends(require_roles("admin", "auditor")),
    db: Session = Depends(get_db),
):
    try:
        task = resolve_review_task(
            db,
            review_id=review_id,
            reviewer_id=reviewer.user_id,
            decision=payload.decision,
            notes=payload.notes,
            request_id=request.state.request_id,
        )
    except ReviewConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if task is None:
        raise HTTPException(status_code=404, detail="Review task not found")
    return _to_review_response(task)


@router.post(
    "/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_feedback(
    payload: CreateFeedbackRequest,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entry = create_feedback(
        db,
        request_id=request.state.request_id,
        user_id=user.user_id,
        query=payload.query,
        rating=payload.rating,
        comment=payload.comment,
    )
    return FeedbackResponse(
        id=entry.id,
        request_id=entry.request_id,
        user_id=entry.user_id,
        query=entry.query,
        rating=entry.rating,
        comment=entry.comment,
        created_at=entry.created_at,
    )
