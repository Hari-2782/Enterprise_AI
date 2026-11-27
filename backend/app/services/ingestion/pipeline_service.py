import hashlib
import json
import logging
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import select

from sqlalchemy.orm import Session

from app.core.request_context import reset_request_id, set_request_id
from app.database.connection import SessionLocal
from app.database.models import (
    Document,
    DocumentChunk,
    DocumentVersion,
    IngestionJob,
)
from app.services.ingestion.chunking_service import StructureAwareChunkingService
from app.services.ingestion.extraction_service import extract_document
from app.services.ingestion.publication_policy import can_publish_extraction
from app.services.search.vector_indexing_service import (
    SearchIndexingError,
    VectorIndexingService,
    deterministic_chunk_key,
)


logger = logging.getLogger("enterprise-ai.ingestion")


def _has_active_lease(
    db: Session,
    job_id: UUID | None,
    lease_token: UUID | None,
) -> bool:
    if job_id is None:
        return True
    job = db.scalar(
        select(IngestionJob)
        .where(IngestionJob.id == job_id)
        .with_for_update()
    )
    return bool(
        job is not None
        and job.status == "processing"
        and job.lease_token == lease_token
    )


def process_ingestion_version(
    version_id: UUID,
    upload_path: str,
    request_id: str,
    session_factory=SessionLocal,
    extractor=extract_document,
    chunker_factory=StructureAwareChunkingService,
    indexer_factory=VectorIndexingService,
    job_id: UUID | None = None,
    lease_token: UUID | None = None,
) -> str:
    """Run extraction through verified indexing for a claimed outbox job."""
    request_token = set_request_id(request_id)
    db: Session | None = None
    phase = "extraction"
    try:
        db = session_factory()
        if not _has_active_lease(db, job_id, lease_token):
            db.rollback()
            return "stale"
        version = db.get(DocumentVersion, version_id)
        if version is None:
            return "unpublishable"
        if version.status == "published":
            return "published"

        document = db.get(Document, version.document_id)
        if document is None:
            raise RuntimeError("Document record for version was not found")

        version.status = "processing"
        version.error_message = None
        db.commit()

        extraction = extractor(upload_path)
        if not _has_active_lease(db, job_id, lease_token):
            db.rollback()
            return "stale"
        phase = "chunking"
        version.status = "chunking"
        db.commit()

        chunks = chunker_factory().chunk_extraction(extraction)
        if not _has_active_lease(db, job_id, lease_token):
            db.rollback()
            return "stale"
        db.query(DocumentChunk).filter(
            DocumentChunk.version_id == version.id
        ).delete(synchronize_session=False)

        database_chunks = []
        for chunk in chunks:
            key = deterministic_chunk_key(version.id, chunk.chunk_index)
            sources = chunk.sources
            database_chunks.append(
                DocumentChunk(
                    version_id=version.id,
                    chunk_index=chunk.chunk_index,
                    search_document_key=key,
                    content=chunk.content,
                    chunk_hash=hashlib.sha256(
                        chunk.content.encode("utf-8")
                    ).hexdigest(),
                    section_path=chunk.section_path,
                    page_number=sources[0].page_number if sources else None,
                    token_count=chunk.token_count,
                    source_token_start=chunk.source_token_start,
                    source_token_end=chunk.source_token_end,
                    source_token_count=chunk.source_token_count,
                    sources_json=json.dumps(
                        [
                            source.model_dump(mode="json")
                            for source in sources
                        ],
                        separators=(",", ":"),
                    ),
                    index_status="pending",
                )
            )

        db.add_all(database_chunks)
        version.expected_chunks = len(chunks)
        version.indexed_chunks = 0
        version.status = "indexing"
        db.commit()

        if not can_publish_extraction(extraction, len(chunks)):
            if not _has_active_lease(db, job_id, lease_token):
                db.rollback()
                return "stale"
            version.status = (
                "partial_extraction"
                if extraction.status != "completed" or extraction.failed_pages
                else "no_usable_chunks"
            )
            version.error_message = (
                "; ".join(extraction.extraction_errors)
                or "Extraction produced no publishable chunks"
            )
            db.commit()
            return "unpublishable"

        phase = "indexing"
        indexer = indexer_factory()
        indexer.ensure_index()
        summary = indexer.index_and_verify_chunks(
            document_id=document.id,
            version_id=version.id,
            title=document.title,
            department=document.department,
            chunks=chunks,
        )

        if not _has_active_lease(db, job_id, lease_token):
            db.rollback()
            return "stale"
        version.indexed_chunks = summary.indexed_count
        version.status = "published"
        version.published_at = datetime.now(timezone.utc)
        version.error_message = None
        document.current_version_id = version.id
        for chunk in database_chunks:
            chunk.index_status = "indexed"
        db.commit()

        logger.info(
            "document_version_published",
            extra={
                "event": "document_version_published",
                "document_id": str(document.id),
                "version_id": str(version.id),
                "expected_chunks": version.expected_chunks,
                "indexed_chunks": version.indexed_chunks,
            },
        )
        return "published"
    except Exception as exc:
        if db is not None:
            db.rollback()
            if not _has_active_lease(db, job_id, lease_token):
                db.rollback()
                return "stale"
            version = db.get(DocumentVersion, version_id)
            if version is not None and version.status != "published":
                version.status = f"{phase}_failed"
                if isinstance(exc, SearchIndexingError):
                    version.indexed_chunks = exc.summary.indexed_count
                    failed_keys = set(exc.summary.failed_keys)
                    for chunk in db.query(DocumentChunk).filter(
                        DocumentChunk.version_id == version.id
                    ):
                        chunk.index_status = (
                            "failed"
                            if chunk.search_document_key in failed_keys
                            else "indexed"
                        )
                version.error_message = f"{type(exc).__name__}: {exc}"[:4000]
                db.commit()
        logger.exception(
            "document_ingestion_failed",
            extra={
                "event": "document_ingestion_failed",
                "version_id": str(version_id),
            },
        )
        return f"{phase}_failed"
    finally:
        if db is not None:
            db.close()
        reset_request_id(request_token)
