from __future__ import annotations

import json
import uuid
from typing import Any

import structlog
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session, sessionmaker

from src.application.use_cases.documents.process_document_ingestion_use_case import (
    ProcessDocumentIngestionUseCase,
)
from src.core.config import settings
from src.domain.value_objects.document_status import DocumentStatus
from src.infrastructure.ai.extractors.pdf_extractor import PdfExtractor
from src.infrastructure.ai.extractors.url_extractor import UrlExtractor
from src.infrastructure.ai.extractors.youtube_extractor import YoutubeExtractor
from src.infrastructure.cache.document_status_cache import RedisDocumentStatusCache
from src.infrastructure.celery.app import celery_app
from src.infrastructure.celery.dependencies import get_worker_redis, get_worker_session_factory
from src.infrastructure.celery.dispatcher import CeleryTaskDispatcher
from src.infrastructure.celery.error_handling import classify_error
from src.infrastructure.database.models.document import DocumentModel
from src.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from src.infrastructure.storage.factory import build_file_storage
from src.infrastructure.text_processing.simple_text_chunker import SimpleTextChunker

logger = structlog.get_logger(__name__)


# Sync database session factory for Celery workers
# Workers run in separate processes — they must NOT share the async engine
# from the FastAPI DI container. We create a dedicated sync engine here.
# This engine is module-level so it is created once per worker process.

_sync_engine = create_engine(
    settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://"),
    pool_size=5,
    max_overflow=2,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args={
        "timeout": settings.DB_CONNECT_TIMEOUT,
        "connect_timeout": settings.DB_CONNECT_TIMEOUT,
    },
)
_SyncSession = sessionmaker(bind=_sync_engine, autoflush=True, expire_on_commit=False)



def _set_status_sync(document_id: str, status: str, progress: int, message: str) -> None:
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



@celery_app.task(  # type: ignore[untyped-decorator]
    name="src.infrastructure.celery.tasks.document_processing.process_document",
    queue="document_processing",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def process_document(self: Any, document_id: str) -> dict[str, Any]:
    log = logger.bind(document_id=document_id, task_id=self.request.id)
    log.info("Document processing started")

    try:
        import asyncio

        from src.infrastructure.celery.dependencies import dispose_worker_engine

        async def safe_process() -> dict[str, str]:
            try:
                return await _run_process_document_use_case(document_id)
            finally:
                await dispose_worker_engine()

        return asyncio.run(safe_process())
    except Exception as exc:
        is_retryable, reason = classify_error(exc)

        log.error(
            "document_processing_error",
            error_type=type(exc).__name__,
            error_reason=reason,
            is_retryable=is_retryable,
            retry_count=self.request.retries,
            max_retries=self.max_retries,
            error=str(exc),
        )

        if is_retryable and self.request.retries < self.max_retries:
            countdown = min(2 ** self.request.retries * 60, 3600)  # Up to 1 hour
            log.info("retrying_task", countdown=countdown)
            raise self.retry(exc=exc, countdown=countdown) from exc

        log.error("document_processing_permanent_failure", reason=reason)
        _handle_failure(document_id, str(exc), log)
        return {"document_id": document_id, "status": "FAILED", "error": str(exc)}


async def _run_process_document_use_case(document_id: str) -> dict[str, str]:
    factory = get_worker_session_factory()
    redis = get_worker_redis(decode_responses=True)

    async with factory() as session:
        use_case = ProcessDocumentIngestionUseCase(
            uow=SQLAlchemyUnitOfWork(session),
            status_cache=RedisDocumentStatusCache(redis),
            task_dispatcher=CeleryTaskDispatcher(),
            text_chunker=SimpleTextChunker(),
            file_storage=build_file_storage(),
            url_extractor=UrlExtractor(),
            youtube_extractor=YoutubeExtractor(),
            pdf_extractor=PdfExtractor(),
        )
        result = await use_case(document_id)
        return {"document_id": result.document_id, "status": result.status}


def _handle_failure(document_id: str, reason: str, log: Any) -> None:
    try:
        with _SyncSession() as session:
            _mark_document_status(session, document_id, DocumentStatus.FAILED)
    except Exception:
        log.exception("Failed to mark document as FAILED in DB")
    _set_status_sync(document_id, "FAILED", 0, f"Processing failed: {reason}")
    log.error("Document processing permanently failed", reason=reason)
