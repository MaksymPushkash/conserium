"""Document processing Celery task chain.

Pipeline:
    process_document (document_processing queue)
      ├─ _step_extract   — extract raw text from file bytes or URL
      ├─ _step_chunk     — split text into chunks using SimpleTextChunker
      ├─ _step_embed     — [placeholder] embed chunks (embeddings queue in Month 2)
      └─ _step_finalize  — persist chunks to DB, mark document READY

Status is written to Redis at every step so callers can poll
GET /documents/{id}/status.

IMPORTANT: Celery tasks are synchronous. They use a separate sync
SQLAlchemy engine — NOT the async engine owned by the Dishka DI container.
This avoids mixing async event loops between the FastAPI and Celery processes.

Progress milestones:
  0%   → QUEUED  (set by the API before dispatching)
  10%  → PROCESSING, extracting content
  40%  → PROCESSING, chunking text
  60%  → PROCESSING, embedding chunks (placeholder)
  90%  → PROCESSING, persisting to database
  100% → READY / FAILED
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import structlog
from celery import Task
from celery.exceptions import MaxRetriesExceededError
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session, sessionmaker

from src.core.config import settings
from src.domain.value_objects.document_status import DocumentStatus
from src.domain.value_objects.document_type import DocumentType
from src.infrastructure.celery.app import celery_app
from src.infrastructure.database.models.chunk import ChunkModel
from src.infrastructure.database.models.document import DocumentModel
from src.infrastructure.text_processing.simple_text_chunker import SimpleTextChunker

logger = structlog.get_logger(__name__)


# Sync database session factory for Celery workers
# Workers run in separate processes — they must NOT share the async engine
# from the FastAPI DI container. We create a dedicated sync engine here.
# This engine is module-level so it is created once per worker process.

_sync_engine = create_engine(
    # asyncpg DSN → psycopg2-compatible DSN
    settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://"),
    pool_size=5,
    max_overflow=2,
    pool_pre_ping=True,
    pool_recycle=300,
)
_SyncSession = sessionmaker(bind=_sync_engine, autoflush=True, expire_on_commit=False)

# Chunker singleton (stateless, safe to share across task invocations)
_chunker = SimpleTextChunker()




def _set_status_sync(document_id: str, status: str, progress: int, message: str) -> None:
    """Write document processing status to Redis synchronously.

    Uses raw redis-py (sync client) to avoid spinning up an event loop
    inside a Celery task.
    """
    import redis as redis_sync

    client = redis_sync.from_url(settings.REDIS_URL, decode_responses=True)
    payload = json.dumps({
        "document_id": document_id,
        "status": status,
        "progress": max(0, min(100, progress)),
        "message": message,
    })
    client.set(f"doc:status:{document_id}", payload, ex=settings.REDIS_DOC_STATUS_TTL)
    client.close()





def _mark_document_status(session: Session, document_id: str, status: DocumentStatus) -> None:
    from datetime import UTC, datetime
    session.execute(
        update(DocumentModel)
        .where(DocumentModel.id == uuid.UUID(document_id))
        .values(status=status, updated_at=datetime.now(UTC))
    )
    session.commit()


def _get_document_row(session: Session, document_id: str) -> DocumentModel | None:
    result = session.execute(
        select(DocumentModel).where(DocumentModel.id == uuid.UUID(document_id))
    )
    return result.scalar_one_or_none()



@celery_app.task(
    name="src.infrastructure.celery.tasks.document_processing.process_document",
    queue="document_processing",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def process_document(self: Task, document_id: str) -> dict[str, Any]:
    """Entry point for the document processing pipeline.

    Args:
        document_id: string UUID of the document row already persisted
                     in PostgreSQL with status=QUEUED.

    Returns:
        dict with {"document_id": ..., "status": "READY"|"FAILED"}
    """
    log = logger.bind(document_id=document_id, task_id=self.request.id)
    log.info("Document processing started")

    try:
        with _SyncSession() as session:
            doc = _get_document_row(session, document_id)
            if doc is None:
                log.error("Document not found — skipping")
                return {"document_id": document_id, "status": "NOT_FOUND"}

            # mark PROCESSING, extract content
            _set_status_sync(document_id, "PROCESSING", 10, "Extracting content…")
            _mark_document_status(session, document_id, DocumentStatus.PROCESSING)

            raw_text = _step_extract(doc, log)

            # chunk text
            _set_status_sync(document_id, "PROCESSING", 40, "Splitting into chunks…")
            chunks_data = _step_chunk(raw_text, log)

            # embed (placeholder — real embeddings in Month 2)
            _set_status_sync(document_id, "PROCESSING", 60, "Generating embeddings…")
            embedded_chunks = _step_embed_placeholder(chunks_data, log)

            # persist chunks + mark READY
            _set_status_sync(document_id, "PROCESSING", 90, "Saving to database…")
            _step_finalize(session, document_id, doc, raw_text, embedded_chunks, log)

        _set_status_sync(document_id, "READY", 100, "Processing complete.")
        log.info("Document processing completed")
        return {"document_id": document_id, "status": "READY"}

    except MaxRetriesExceededError:
        _handle_failure(document_id, "Max retries exceeded", log)
        raise
    except Exception as exc:
        log.exception("Document processing failed", error=str(exc))
        try:
            self.retry(exc=exc)
        except MaxRetriesExceededError:
            _handle_failure(document_id, str(exc), log)
            return {"document_id": document_id, "status": "FAILED"}
        return {"document_id": document_id, "status": "RETRYING"}




def _step_extract(doc: DocumentModel, log: Any) -> str:
    """Extract raw text from the document.

    Currently handles:
    - TEXT/MARKDOWN: raw_content is already stored in the DB (ingested via
      /ingest-text endpoint).
    - URL: synchronously fetches and extracts via trafilatura.
    - PDF: reads from local file path and extracts via pdfplumber.

    Returns the extracted plain text.
    """
    doc_type = doc.type

    # Plain text already stored
    if doc_type in (DocumentType.TEXT, DocumentType.MARKDOWN):
        if doc.raw_content:
            log.debug("Using stored raw_content", type=doc_type.value)
            return doc.raw_content
        raise ValueError(f"Document {doc.id} has type {doc_type.value} but no raw_content stored")

    # URL extraction
    if doc_type == DocumentType.URL:
        if not doc.source_url:
            raise ValueError(f"Document {doc.id} is type URL but has no source_url")
        log.info("Fetching URL content", url=doc.source_url)
        from src.infrastructure.ai.extractors.url_extractor import UrlExtractor
        extractor = UrlExtractor()
        import asyncio
        result = asyncio.run(extractor.extract_from_url(doc.source_url))
        return result.text

    # PDF extraction
    if doc_type == DocumentType.PDF:
        if not doc.file_path:
            raise ValueError(f"Document {doc.id} is type PDF but has no file_path")
        log.info("Extracting PDF", file_path=doc.file_path)
        with open(doc.file_path, "rb") as f:
            pdf_bytes = f.read()
        from src.infrastructure.ai.extractors.pdf_extractor import PdfExtractor
        extractor = PdfExtractor()
        import asyncio
        result = asyncio.run(extractor.extract_from_bytes(pdf_bytes, filename=doc.file_path))
        return result.text

    raise NotImplementedError(
        f"Extraction not yet implemented for document type: {doc_type.value}. "
        "Audio (Whisper) and Image (OCR) are planned for Month 2."
    )


def _step_chunk(raw_text: str, log: Any) -> list[dict[str, Any]]:
    """Split raw text into chunks using SimpleTextChunker.

    Returns a list of dicts (JSON-serialisable) with chunk fields.
    This keeps the step boundary clean for future distribution.
    """
    text_chunks = _chunker.chunk_text(raw_text)
    if not text_chunks:
        raise ValueError("Text produced no chunks after splitting")

    log.info("Text chunked", num_chunks=len(text_chunks))
    return [
        {
            "content": tc.content,
            "chunk_index": tc.chunk_index,
            "start_char": tc.start_char,
            "end_char": tc.end_char,
            "token_count": tc.token_count,
        }
        for tc in text_chunks
    ]


def _step_embed_placeholder(
    chunks_data: list[dict[str, Any]],
    log: Any,
) -> list[dict[str, Any]]:
    """Placeholder embedding step — inserts zero vectors.

    Real OpenAI embeddings are implemented in Month 2 when the
    embeddings queue worker is wired up. Zero vectors still satisfy
    the NOT NULL constraint and pgvector schema so the document
    reaches READY status and chunks are queryable by exact match.
    """
    from src.domain.entities.chunk_entity import ChunkEntity

    dim = ChunkEntity.EMBEDDING_DIMENSIONS
    log.debug("Embedding step (placeholder)", num_chunks=len(chunks_data), dimensions=dim)
    for chunk in chunks_data:
        chunk["embedding"] = [0.0] * dim
    return chunks_data


def _step_finalize(
    session: Session,
    document_id: str,
    doc: DocumentModel,
    raw_text: str,
    chunks_data: list[dict[str, Any]],
    log: Any,
) -> None:
    """Persist chunks and mark the document as READY."""
    from datetime import UTC, datetime

    doc_uuid = uuid.UUID(document_id)

    
    from sqlalchemy import delete
    session.execute(delete(ChunkModel).where(ChunkModel.document_id == doc_uuid))
    session.flush()
    
    chunk_models = [
        ChunkModel(
            id=uuid.uuid4(),
            document_id=doc_uuid,
            content=c["content"],
            embedding=c["embedding"],
            chunk_index=c["chunk_index"],
            start_char=c["start_char"],
            end_char=c["end_char"],
            page_number=None,
            token_count=c["token_count"],
            created_at=datetime.now(UTC),
        )
        for c in chunks_data
    ]
    session.add_all(chunk_models)

    
    now = datetime.now(UTC)
    session.execute(
        update(DocumentModel)
        .where(DocumentModel.id == doc_uuid)
        .values(
            status=DocumentStatus.READY,
            word_count=len(raw_text.split()),
            raw_content=raw_text if not doc.raw_content else doc.raw_content,
            updated_at=now,
        )
    )
    session.commit()
    log.info("Document finalized", chunks_saved=len(chunk_models))


def _handle_failure(document_id: str, reason: str, log: Any) -> None:
    """Mark document as FAILED in DB and Redis."""
    try:
        with _SyncSession() as session:
            _mark_document_status(session, document_id, DocumentStatus.FAILED)
    except Exception:
        log.exception("Failed to mark document as FAILED in DB")
    _set_status_sync(document_id, "FAILED", 0, f"Processing failed: {reason}")
    log.error("Document processing permanently failed", reason=reason)
