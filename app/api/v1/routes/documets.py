import logging
import os
import uuid
from pathlib import Path
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.connection import get_db
from app.database.models import Document, DocumentVersion, IngestionJob
from app.schemas.ingestion import IngestionAccepted, IngestionStatus
from app.services.ingestion.file_validation import (
    SUPPORTED_EXTENSIONS,
    detect_file_type,
)


logger = logging.getLogger("enterprise-ai.ingestion")
router = APIRouter(prefix="/api/v1/documents", tags=["documents"])
CHUNK_SIZE = 1024 * 1024
RETRYABLE_STATUSES = {
    "failed",
    "extraction_failed",
    "chunking_failed",
    "partial_extraction",
    "no_usable_chunks",
    "indexing_failed",
    "worker_failed",
}


def _safe_filename(filename: str | None) -> str:
    cleaned = (filename or "").replace("\\", "/")
    basename = Path(cleaned).name
    if not basename or basename in {".", ".."} or len(basename) > 255:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return basename


async def _stage_upload(upload: UploadFile) -> tuple[Path, str, str]:
    filename = _safe_filename(upload.filename)
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file extension: {extension}",
        )
    storage_root = Path(settings.upload_dir)
    storage_root.mkdir(parents=True, exist_ok=True)
    temporary_path = storage_root / f".upload-{uuid.uuid4().hex}{extension}"
    import hashlib

    digest = hashlib.sha256()
    total_bytes = 0
    try:
        with temporary_path.open("wb") as destination:
            while data := await upload.read(CHUNK_SIZE):
                total_bytes += len(data)
                if total_bytes > settings.max_upload_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail="Uploaded file exceeds the size limit",
                    )
                digest.update(data)
                destination.write(data)

        content_hash = digest.hexdigest()
        detect_file_type(temporary_path)

        final_path = storage_root / f"{content_hash}{extension}"
        if final_path.exists():
            temporary_path.unlink(missing_ok=True)
        else:
            os.replace(temporary_path, final_path)
        return final_path, content_hash, filename
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()


@router.post(
    "",
    response_model=IngestionAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(..., min_length=1, max_length=255),
    department: str = Form(..., min_length=1, max_length=100),
    document_id: UUID | None = Header(default=None, alias="X-Document-ID"),
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        max_length=128,
    ),
    db: Session = Depends(get_db),
):
    title = title.strip()
    department = department.strip()
    if not title or not department:
        raise HTTPException(
            status_code=422,
            detail="title and department must not be blank",
        )
    if idempotency_key is not None:
        idempotency_key = idempotency_key.strip()
        if not idempotency_key:
            raise HTTPException(
                status_code=400,
                detail="Idempotency-Key must not be blank",
            )

    try:
        upload_path, content_hash, filename = await _stage_upload(file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        document_identifier = document_id
        generated_from_idempotency_key = (
            document_identifier is None and idempotency_key is not None
        )
        if generated_from_idempotency_key:
            document_identifier = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"enterprise-ai-ingestion:{idempotency_key}",
            )
        if document_identifier is None:
            document_identifier = uuid.uuid4()

        document = db.scalar(
            select(Document)
            .where(Document.id == document_identifier)
            .with_for_update()
        )
        document_already_existed = document is not None
        if document is None:
            document = Document(
                id=document_identifier,
                title=title,
                department=department,
            )
            db.add(document)
            db.flush()
        elif document.title != title or document.department != department:
            raise HTTPException(
                status_code=409,
                detail="Document ID or idempotency key is already tied to different metadata",
            )

        existing_version = db.scalar(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document.id,
                DocumentVersion.content_hash == content_hash,
            )
        )
        duplicate = existing_version is not None
        requeued_existing = False
        if existing_version is None:
            if generated_from_idempotency_key and document_already_existed:
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency-Key was already used for a different upload",
                )
            max_version = db.scalar(
                select(func.max(DocumentVersion.version_number)).where(
                    DocumentVersion.document_id == document.id
                )
            )
            version = DocumentVersion(
                document_id=document.id,
                version_number=(max_version or 0) + 1,
                filename=filename,
                content_hash=content_hash,
                status="queued",
                expected_chunks=0,
                indexed_chunks=0,
            )
            db.add(version)
            db.flush()
            job = IngestionJob(
                version_id=version.id,
                source_path=str(upload_path),
                request_id=request.state.request_id,
                status="pending",
            )
            db.add(job)
        else:
            version = existing_version
            if version.status in RETRYABLE_STATUSES:
                version.status = "queued"
                version.error_message = None
                requeued_existing = True
            job = db.scalar(
                select(IngestionJob)
                .where(IngestionJob.version_id == version.id)
                .with_for_update()
            )
            if job is None:
                job = IngestionJob(
                    version_id=version.id,
                    source_path=str(upload_path),
                    request_id=request.state.request_id,
                    status="pending",
                )
                db.add(job)
                requeued_existing = True
            elif requeued_existing or job.status == "dead_letter":
                job.source_path = str(upload_path)
                job.request_id = request.state.request_id
                job.status = "pending"
                job.attempt_count = 0
                job.available_at = func.now()
                job.locked_at = None
                job.locked_by = None
                job.lease_token = None
                job.last_error = None

        db.commit()
        db.refresh(version)
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raced_document = db.get(Document, document_identifier)
        raced_version = (
            db.scalar(
                select(DocumentVersion).where(
                    DocumentVersion.document_id == document_identifier,
                    DocumentVersion.content_hash == content_hash,
                )
            )
            if raced_document is not None
            else None
        )
        if raced_version is None:
            raise HTTPException(
                status_code=409,
                detail="A concurrent document version was created; retry the upload",
            ) from exc
        document = raced_document
        version = raced_version
        duplicate = True
        requeued_existing = False
    except Exception:
        db.rollback()
        logger.exception(
            "document_upload_persistence_failed",
            extra={
                "event": "document_upload_persistence_failed",
                "request_id": request.state.request_id,
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Unable to persist document upload",
        )

    logger.info(
        "document_upload_accepted",
        extra={
            "event": "document_upload_accepted",
            "document_id": str(document.id),
            "version_id": str(version.id),
            "duplicate": duplicate,
        },
    )
    return IngestionAccepted(
        document_id=document.id,
        version_id=version.id,
        status=version.status,
        duplicate=duplicate,
        request_id=request.state.request_id,
    )


@router.get("/{version_id}", response_model=IngestionStatus)
def get_ingestion_status(
    version_id: UUID,
    db: Session = Depends(get_db),
):
    version = db.get(DocumentVersion, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Document version not found")
    return IngestionStatus(
        document_id=version.document_id,
        version_id=version.id,
        version_number=version.version_number,
        filename=version.filename,
        status=version.status,
        expected_chunks=version.expected_chunks,
        indexed_chunks=version.indexed_chunks,
        error_message=version.error_message,
        published_at=version.published_at,
    )
