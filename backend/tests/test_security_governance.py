from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.security import (
    AuthenticatedUser,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.database.connection import SessionLocal
from app.database.models import (
    Document,
    DocumentPermission,
    DocumentVersion,
)
from app.main import app
from app.providers.llm import MockLLMProvider
from app.services.generation.rag_service import GroundedRAGService
from app.services.governance.authorization import build_authorized_versions_statement
from app.services.governance.pii import mask_pii
from app.services.search.retrieval_service import RetrievalHit


def test_password_hashing_and_token_verification():
    hashed = hash_password("super-secret-password")
    assert verify_password("super-secret-password", hashed) is True
    assert verify_password("wrong-password", hashed) is False

    user = AuthenticatedUser(
        user_id=uuid4(),
        email="alice@example.com",
        department="Engineering",
        roles=frozenset({"viewer", "editor"}),
    )
    token = create_access_token(user, ttl_minutes=5)
    decoded = decode_access_token(token)
    assert decoded.user_id == user.user_id
    assert decoded.email == "alice@example.com"
    assert decoded.department == "Engineering"
    assert decoded.roles == frozenset({"viewer", "editor"})

    with pytest.raises(ValueError):
        decode_access_token(token + "tampered")


def test_protected_endpoints_require_authentication_and_rbac():
    client = TestClient(app)

    assert client.post("/api/v1/search", json={"query": "policy"}).status_code == 401
    assert client.post("/api/v1/chat", json={"query": "policy"}).status_code == 401
    assert client.get("/api/v1/audit-logs").status_code == 401
    assert (
        client.post(
            "/api/v1/documents",
            data={"title": "Rogue", "department": "HR"},
            files={"file": ("rogue.txt", b"hello", "text/plain")},
        ).status_code
        == 401
    )

    eng_editor = AuthenticatedUser(
        user_id=uuid4(),
        email="eng-editor@example.com",
        department="Engineering",
        roles=frozenset({"editor"}),
    )
    eng_editor_token = create_access_token(eng_editor)
    cross_dept_upload = client.post(
        "/api/v1/documents",
        data={"title": "Rogue HR", "department": "HR"},
        files={"file": ("rogue.txt", b"hello", "text/plain")},
        headers={"Authorization": f"Bearer {eng_editor_token}"},
    )
    assert cross_dept_upload.status_code == 403

    viewer = AuthenticatedUser(
        user_id=uuid4(),
        email="viewer@example.com",
        department="Engineering",
        roles=frozenset({"viewer"}),
    )
    viewer_token = create_access_token(viewer)
    res_forbidden = client.get(
        "/api/v1/audit-logs",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert res_forbidden.status_code == 403

    auditor = AuthenticatedUser(
        user_id=uuid4(),
        email="auditor@example.com",
        department="Compliance",
        roles=frozenset({"auditor"}),
    )
    auditor_token = create_access_token(auditor)
    res_allowed = client.get(
        "/api/v1/audit-logs",
        headers={"Authorization": f"Bearer {auditor_token}"},
    )
    assert res_allowed.status_code == 200
    assert isinstance(res_allowed.json(), list)


def test_pii_masking_redacts_sensitive_fields_before_llm_call():
    raw = "Contact jane.doe@example.com or +94 755318753 or 555-123-4567, SSN 123-45-6789."
    masked, kinds = mask_pii(raw)
    assert "jane.doe@example.com" not in masked
    assert "+94 755318753" not in masked
    assert "555-123-4567" not in masked
    assert "123-45-6789" not in masked
    assert set(kinds) == {"email", "phone", "ssn"}

    class _FakeRetrieval:
        def search(self, _query: str, **_kwargs):
            return [
                RetrievalHit(
                    chunk_id="c1",
                    document_id=str(uuid4()),
                    version_id=str(uuid4()),
                    chunk_index=0,
                    title="Directory",
                    content=raw,
                    section_path="Contacts",
                    department="HR",
                    page_numbers=[1],
                    sources_json=None,
                    score=0.9,
                )
            ]

    llm = MockLLMProvider(canned_response="See directory [C1].")
    rag = GroundedRAGService(
        retrieval_service=_FakeRetrieval(),  # type: ignore[arg-type]
        llm_provider=llm,
    )
    rag.answer("Who do I contact?")
    sent_prompt = llm.calls[0].messages[1].content
    assert "jane.doe@example.com" not in sent_prompt
    assert "123-45-6789" not in sent_prompt
    assert "[REDACTED_EMAIL]" in sent_prompt


def test_department_and_acl_authorization_against_postgres():
    db = SessionLocal()
    eng_doc = Document(title="Eng Runbook", department="Engineering")
    hr_doc = Document(title="HR Salaries", department="HR")
    db.add_all([eng_doc, hr_doc])
    db.flush()

    eng_ver = DocumentVersion(
        document_id=eng_doc.id,
        version_number=1,
        filename="eng.txt",
        content_hash=uuid4().hex + uuid4().hex,
        status="published",
    )
    hr_ver = DocumentVersion(
        document_id=hr_doc.id,
        version_number=1,
        filename="hr.txt",
        content_hash=uuid4().hex + uuid4().hex,
        status="published",
    )
    db.add_all([eng_ver, hr_ver])
    db.flush()

    eng_doc.current_version_id = eng_ver.id
    hr_doc.current_version_id = hr_ver.id
    db.commit()

    eng_user_id = uuid4()
    eng_user = AuthenticatedUser(
        user_id=eng_user_id,
        email="dev@example.com",
        department="Engineering",
        roles=frozenset({"viewer"}),
    )
    admin_user = AuthenticatedUser(
        user_id=uuid4(),
        email="admin@example.com",
        department="IT",
        roles=frozenset({"admin"}),
    )

    try:
        # 1. Engineering user sees Eng doc, NOT HR doc.
        eng_allowed = set(
            db.scalars(build_authorized_versions_statement(user=eng_user)).all()
        )
        assert eng_ver.id in eng_allowed
        assert hr_ver.id not in eng_allowed

        # 2. Admin sees both.
        admin_allowed = set(
            db.scalars(build_authorized_versions_statement(user=admin_user)).all()
        )
        assert {eng_ver.id, hr_ver.id}.issubset(admin_allowed)

        # 3. Grant explicit user ACL on HR doc -> Engineering user now sees HR doc.
        acl = DocumentPermission(
            document_id=hr_doc.id,
            principal_type="user",
            principal_id=str(eng_user_id),
            permission="read",
        )
        db.add(acl)
        db.commit()

        eng_allowed_after = set(
            db.scalars(build_authorized_versions_statement(user=eng_user)).all()
        )
        assert {eng_ver.id, hr_ver.id}.issubset(eng_allowed_after)
    finally:
        db.rollback()
        eng_doc.current_version_id = None
        hr_doc.current_version_id = None
        db.flush()
        db.query(DocumentPermission).filter(
            DocumentPermission.document_id.in_([eng_doc.id, hr_doc.id])
        ).delete(synchronize_session=False)
        db.delete(eng_ver)
        db.delete(hr_ver)
        db.flush()
        db.delete(eng_doc)
        db.delete(hr_doc)
        db.commit()
        db.close()
