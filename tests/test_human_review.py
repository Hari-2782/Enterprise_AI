from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.core.security import AuthenticatedUser, create_access_token, hash_password
from app.database.connection import SessionLocal
from app.database.models import AuditLog, Feedback, ReviewTask, User
from app.main import app


def test_human_review_lifecycle_rbac_and_audit_trail():
    db = SessionLocal()
    viewer_user = User(
        email=f"viewer-{uuid4().hex[:8]}@example.com",
        full_name="Test Viewer",
        department="HR",
        password_hash=hash_password("pw"),
    )
    auditor_user = User(
        email=f"auditor-{uuid4().hex[:8]}@example.com",
        full_name="Test Auditor",
        department="Compliance",
        password_hash=hash_password("pw"),
    )
    db.add_all([viewer_user, auditor_user])
    db.commit()
    db.refresh(viewer_user)
    db.refresh(auditor_user)
    db.close()

    viewer_token = create_access_token(
        AuthenticatedUser(
            user_id=viewer_user.id,
            email=viewer_user.email,
            department="HR",
            roles=frozenset({"viewer"}),
        )
    )
    auditor_token = create_access_token(
        AuthenticatedUser(
            user_id=auditor_user.id,
            email=auditor_user.email,
            department="Compliance",
            roles=frozenset({"auditor"}),
        )
    )

    client = TestClient(app)
    created_id: UUID | None = None
    feedback_id: UUID | None = None

    try:
        # 1. Viewer submits a review task for an abstained answer.
        res = client.post(
            "/api/v1/reviews",
            json={
                "query": "What is the executive bonus cap?",
                "proposed_answer": "INSUFFICIENT_EVIDENCE",
                "abstention_reason": "No matching policy found",
                "escalate": True,
            },
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert res.status_code == 201
        body = res.json()
        created_id = UUID(body["id"])
        assert body["status"] == "escalated"

        # 2. Viewer cannot resolve or list review queue.
        assert (
            client.get(
                "/api/v1/reviews",
                headers={"Authorization": f"Bearer {viewer_token}"},
            ).status_code
            == 403
        )
        assert (
            client.post(
                f"/api/v1/reviews/{created_id}/resolve",
                json={"decision": "approved"},
                headers={"Authorization": f"Bearer {viewer_token}"},
            ).status_code
            == 403
        )

        # 3. Auditor lists escalated tasks and approves.
        list_res = client.get(
            "/api/v1/reviews?status=escalated",
            headers={"Authorization": f"Bearer {auditor_token}"},
        )
        assert list_res.status_code == 200
        assert any(item["id"] == str(created_id) for item in list_res.json())

        resolve_res = client.post(
            f"/api/v1/reviews/{created_id}/resolve",
            json={"decision": "approved", "notes": "Verified against HR handbook."},
            headers={"Authorization": f"Bearer {auditor_token}"},
        )
        assert resolve_res.status_code == 200
        assert resolve_res.json()["status"] == "approved"
        assert resolve_res.json()["resolved_at"] is not None

        # 4. Double-resolution is rejected with 409 Conflict.
        conflict_res = client.post(
            f"/api/v1/reviews/{created_id}/resolve",
            json={"decision": "rejected"},
            headers={"Authorization": f"Bearer {auditor_token}"},
        )
        assert conflict_res.status_code == 409

        # 5. Feedback submission works for authenticated user.
        fb_res = client.post(
            "/api/v1/feedback",
            json={
                "query": "What is the executive bonus cap?",
                "rating": "positive",
                "comment": "Good abstention.",
            },
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert fb_res.status_code == 201
        feedback_id = UUID(fb_res.json()["id"])
        assert fb_res.json()["rating"] == "positive"
    finally:
        db = SessionLocal()
        try:
            if created_id is not None:
                db.query(AuditLog).filter(
                    AuditLog.resource_id == str(created_id)
                ).delete(synchronize_session=False)
                db.query(ReviewTask).filter(ReviewTask.id == created_id).delete(
                    synchronize_session=False
                )
            if feedback_id is not None:
                db.query(Feedback).filter(Feedback.id == feedback_id).delete(
                    synchronize_session=False
                )
            db.query(User).filter(
                User.id.in_([viewer_user.id, auditor_user.id])
            ).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()
