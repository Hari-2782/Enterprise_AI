from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.database.models import Feedback, ReviewTask
from app.services.governance.audit import record_audit_event


_RESOLVABLE_STATUSES = frozenset({"pending", "escalated"})


class ReviewConflictError(Exception):
    """Raised when a review task is already resolved."""


def create_review_task(
    db: Session,
    *,
    request_id: str | None,
    user_id: UUID | None,
    query: str,
    proposed_answer: str,
    abstention_reason: str | None = None,
    escalate: bool = False,
) -> ReviewTask:
    status = "escalated" if escalate else "pending"
    task = ReviewTask(
        request_id=request_id,
        user_id=user_id,
        query=query.strip(),
        proposed_answer=proposed_answer.strip(),
        abstention_reason=abstention_reason,
        status=status,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    record_audit_event(
        db,
        request_id=request_id,
        user_id=user_id,
        action="review.create",
        resource_type="review_task",
        resource_id=str(task.id),
        outcome="allowed",
        details={"status": status},
    )
    return task


def resolve_review_task(
    db: Session,
    *,
    review_id: UUID,
    reviewer_id: UUID,
    decision: str,
    notes: str | None,
    request_id: str | None,
) -> ReviewTask | None:
    task = db.get(ReviewTask, review_id)
    if task is None:
        return None
    if task.status not in _RESOLVABLE_STATUSES:
        raise ReviewConflictError(
            f"Review task {review_id} is already {task.status}"
        )

    task.status = decision
    task.reviewer_id = reviewer_id
    task.reviewer_notes = notes
    task.resolved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(task)

    record_audit_event(
        db,
        request_id=request_id,
        user_id=reviewer_id,
        action="review.resolve",
        resource_type="review_task",
        resource_id=str(task.id),
        outcome="allowed",
        details={"decision": decision},
    )
    return task


def create_feedback(
    db: Session,
    *,
    request_id: str | None,
    user_id: UUID | None,
    query: str,
    rating: str,
    comment: str | None,
) -> Feedback:
    entry = Feedback(
        request_id=request_id,
        user_id=user_id,
        query=query.strip(),
        rating=rating,
        comment=comment,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
