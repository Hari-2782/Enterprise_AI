from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.security import AuthenticatedUser, require_roles
from app.database.connection import get_db
from app.database.models import AuditLog


router = APIRouter(prefix="/api/v1", tags=["governance"])


class AuditLogResponse(BaseModel):
    id: UUID
    request_id: str | None = None
    user_id: UUID | None = None
    action: str
    resource_type: str
    resource_id: str | None = None
    outcome: str
    details_json: str | None = None
    created_at: datetime


@router.get("/audit-logs", response_model=list[AuditLogResponse])
def list_audit_logs(
    limit: int = Query(default=50, ge=1, le=200),
    _user: AuthenticatedUser = Depends(require_roles("admin", "auditor")),
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        select(AuditLog).order_by(desc(AuditLog.created_at)).limit(limit)
    ).all()
    return [
        AuditLogResponse(
            id=row.id,
            request_id=row.request_id,
            user_id=row.user_id,
            action=row.action,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            outcome=row.outcome,
            details_json=row.details_json,
            created_at=row.created_at,
        )
        for row in rows
    ]
