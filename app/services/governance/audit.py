from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.database.models import AuditLog


logger = logging.getLogger("enterprise-ai.audit")


def record_audit_event(
    db: Session | None,
    *,
    request_id: str | None,
    user_id: UUID | None,
    action: str,
    resource_type: str,
    resource_id: str | None,
    outcome: str,
    details: dict[str, Any] | None = None,
) -> AuditLog | None:
    """Persist an audit log entry and emit a structured audit log."""
    details_json = json.dumps(details, sort_keys=True) if details else None
    logger.info(
        "audit_event",
        extra={
            "event": "audit_event",
            "request_id": request_id,
            "user_id": str(user_id) if user_id else None,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "outcome": outcome,
        },
    )
    if db is None:
        return None

    entry = AuditLog(
        request_id=request_id,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        details_json=details_json,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
