from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import create_engine, update
from sqlalchemy.orm import Session, sessionmaker

from src.documents.status import DocumentStatus
from src.documents.status_cache import _build_timeline, _step_payload
from src.models.document import DocumentModel
from src.settings import settings

_sync_engine = create_engine(
    settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://"),
    pool_size=5,
    max_overflow=2,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args={
        "connect_timeout": settings.DB_CONNECT_TIMEOUT,
    },
)
_SyncSession = sessionmaker(bind=_sync_engine, autoflush=True, expire_on_commit=False)


def handle_document_failure(document_id: str, reason: str, log: Any) -> None:
    try:
        with _SyncSession() as session:
            _mark_document_status(session, document_id, DocumentStatus.FAILED)
    except Exception:
        log.exception("Failed to mark document as FAILED in DB")
    _set_status_sync(document_id, "FAILED", 0, f"Processing failed: {reason}")
    log.error("Document processing permanently failed", reason=reason)


def _mark_document_status(session: Session, document_id: str, status: DocumentStatus) -> None:
    from datetime import UTC, datetime

    session.execute(
        update(DocumentModel)
        .where(DocumentModel.id == uuid.UUID(document_id))
        .values(status=status, updated_at=datetime.now(UTC))
    )
    session.commit()


def _set_status_sync(document_id: str, status: str, progress: int, message: str) -> None:
    import redis as redis_sync

    client = redis_sync.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        payload = json.dumps(
            {
                "document_id": document_id,
                "status": status,
                "progress": max(0, min(100, progress)),
                "message": message,
                "failure_reason": message.removeprefix("Processing failed: ").strip() if status == "FAILED" else None,
                "timeline": [_step_payload(step) for step in _build_timeline(status, progress, message)],
            }
        )
        client.set(f"doc:status:{document_id}", payload, ex=settings.REDIS_DOC_STATUS_TTL)
    finally:
        client.close()
