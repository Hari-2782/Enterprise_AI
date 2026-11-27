from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, exists, or_, select

from app.core.security import AuthenticatedUser
from app.database.models import Document, DocumentPermission, DocumentVersion


def build_authorized_versions_statement(
    user: AuthenticatedUser | None = None,
    *,
    department: str | None = None,
    document_id: UUID | None = None,
    version_id: UUID | None = None,
) -> Select[tuple[UUID]]:
    """Build a SQLAlchemy query for published versions the user is authorized to read."""
    statement = (
        select(DocumentVersion.id)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(
            Document.current_version_id == DocumentVersion.id,
            DocumentVersion.status == "published",
        )
        .order_by(DocumentVersion.id)
    )

    if department is not None:
        statement = statement.where(Document.department == department)
    if document_id is not None:
        statement = statement.where(Document.id == document_id)
    if version_id is not None:
        statement = statement.where(DocumentVersion.id == version_id)

    if user is not None and "admin" not in user.roles:
        acl_conditions = [
            (DocumentPermission.principal_type == "user")
            & (DocumentPermission.principal_id == str(user.user_id)),
            (DocumentPermission.principal_type == "department")
            & (DocumentPermission.principal_id == user.department),
        ]
        if user.roles:
            acl_conditions.append(
                (DocumentPermission.principal_type == "role")
                & (DocumentPermission.principal_id.in_(sorted(user.roles)))
            )

        acl_exists = exists(
            select(DocumentPermission.id).where(
                DocumentPermission.document_id == Document.id,
                or_(*acl_conditions),
            )
        )
        statement = statement.where(
            or_(
                Document.department == user.department,
                acl_exists,
            )
        )

    return statement
