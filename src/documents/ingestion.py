from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from src.documents.access import record_shared_document_event
from src.documents.repository import ExternalIntakeItemRecord
from src.documents.results import document_result
from src.documents.schemas import (
    DocumentResult,
    ExternalIngestResult,
    ExternalIntakeItem,
)
from src.documents.service import (
    DocumentCollectionAccess,
    collection_document_owner_id,
    ensure_document_owner,
)
from src.documents.status import DocumentStatus
from src.documents.types import DocumentType
from src.kit.exceptions import (
    DocumentNotFoundException,
    DocumentValidationException,
    ResourceNotFoundException,
    ValidationException,
)
from src.models.chunk import ChunkModel
from src.models.document import DocumentModel

if TYPE_CHECKING:
    from src.documents.activity_repository import DocumentActivityRepository
    from src.documents.chunk_repository import ChunkRepository
    from src.documents.document_repository import DocumentRepository
    from src.documents.external_intake_repository import ExternalIntakeRepository
    from src.documents.processing import DocumentProcessingService
    from src.documents.status_cache import RedisDocumentStatusCache
    from src.documents.text_chunker import SimpleTextChunker
    from src.postgres import AsyncSession
    from src.worker.dispatcher import CeleryTaskDispatcher

logger = logging.getLogger(__name__)


class TextDocumentIngester:
    def __init__(
        self,
        session: AsyncSession,
        document_repo: DocumentRepository,
        text_chunker: SimpleTextChunker,
        collection_access: DocumentCollectionAccess,
        chunk_repo: ChunkRepository,
    ) -> None:
        self._session = session
        self._document_repo = document_repo
        self._text_chunker = text_chunker
        self._collection_access = collection_access
        self._chunk_repo = chunk_repo

    async def __call__(
        self,
        *,
        user_id: UUID,
        title: str,
        raw_text: str,
        collection_id: UUID | None = None,
        type: DocumentType = DocumentType.TEXT,
        source_url: str | None = None,
        language: str | None = None,
    ) -> DocumentResult:
        if not raw_text.strip():
            raise DocumentValidationException("raw_text cannot be empty")

        document_owner_id = await collection_document_owner_id(
            self._collection_access,
            collection_id,
            user_id,
        )

        document = DocumentModel.create(
            id=uuid.uuid4(),
            user_id=document_owner_id,
            collection_id=collection_id,
            title=title,
            type=type,
            source_url=source_url,
            file_size_bytes=len(raw_text.encode()),
            raw_content=raw_text,
            word_count=len(raw_text.split()),
            language=language,
        )

        await self._document_repo.create(document)

        text_chunks = self._text_chunker.chunk_text(raw_text)
        if not text_chunks:
            raise DocumentValidationException("raw_text produced no chunks")

        chunks = [
            ChunkModel.create(
                id=uuid.uuid4(),
                document_id=document.id,
                content=text_chunk.content,
                embedding=[0.0] * ChunkModel.EMBEDDING_DIMENSIONS,
                chunk_index=text_chunk.chunk_index,
                start_char=text_chunk.start_char,
                end_char=text_chunk.end_char,
                token_count=text_chunk.token_count,
            )
            for text_chunk in text_chunks
        ]

        await self._chunk_repo.create_batch(chunks)
        document.mark_ready()
        await self._document_repo.update(document)
        if collection_id is not None:
            await record_shared_document_event(
                self._collection_access,
                collection_id=collection_id,
                actor_user_id=user_id,
                document_id=document.id,
                title=document.title,
            )
        await self._session.flush()

        return document_result(document)

class DocumentIngester:
    def __init__(
        self,
        session: AsyncSession,
        document_repo: DocumentRepository,
        status_cache: RedisDocumentStatusCache,
        task_dispatcher: CeleryTaskDispatcher,
        collection_access: DocumentCollectionAccess,
        activity_repo: DocumentActivityRepository,
        processing_service: DocumentProcessingService,
    ) -> None:
        self._session = session
        self._document_repo = document_repo
        self._status_cache = status_cache
        self._task_dispatcher = task_dispatcher
        self._collection_access = collection_access
        self._activity_repo = activity_repo
        self._processing_service = processing_service

    async def __call__(
        self,
        *,
        user_id: UUID,
        title: str,
        type: DocumentType,
        collection_id: UUID | None = None,
        tags: list[str] | None = None,
        source_url: str | None = None,
        file_path: str | None = None,
        file_size_bytes: int | None = None,
        raw_content: str | None = None,
        language: str | None = None,
    ) -> DocumentResult:
        if type in (DocumentType.TEXT, DocumentType.MARKDOWN) and not (raw_content and raw_content.strip()):
            raise DocumentValidationException("raw_content is required for text ingestion")
        if type in (DocumentType.URL, DocumentType.YOUTUBE) and not source_url:
            raise DocumentValidationException(f"source_url is required for {type.value.lower()} ingestion")
        if type in (DocumentType.PDF, DocumentType.IMAGE) and not file_path:
            raise DocumentValidationException(f"file_path is required for {type.value} ingestion")

        document_owner_id = await collection_document_owner_id(
            self._collection_access,
            collection_id,
            user_id,
        )

        document = DocumentModel.create(
            id=uuid.uuid4(),
            user_id=document_owner_id,
            title=title,
            type=type,
            collection_id=collection_id,
            source_url=source_url,
            file_path=file_path,
            file_size_bytes=file_size_bytes,
            raw_content=raw_content,
            word_count=len(raw_content.split()) if raw_content else None,
            language=language,
            tags=tags,
        )

        await self._document_repo.create(document)
        await self._activity_repo.record_event(
            user_id=document_owner_id,
            document_id=document.id,
            event_type="created",
        )
        if collection_id is not None:
            await record_shared_document_event(
                self._collection_access,
                collection_id=collection_id,
                actor_user_id=user_id,
                document_id=document.id,
                title=document.title,
            )
        await self._session.flush()

        await self._processing_service.queue(document, message="Queued for processing.")

        return document_result(document)




class DocumentRetryer:
    def __init__(
        self,
        document_repo: DocumentRepository,
        processing_service: DocumentProcessingService,
    ) -> None:
        self._document_repo = document_repo
        self._processing_service = processing_service

    async def __call__(self, *, user_id: UUID, document_id: UUID) -> DocumentResult:
        document = await self._document_repo.get_by_id(document_id)

        if document is None:
            raise DocumentNotFoundException("document not found")
        ensure_document_owner(document, user_id)
        if document.status != DocumentStatus.FAILED:
            raise DocumentValidationException("only failed documents can be retried")

        await self._processing_service.queue(document, message="Queued retry for failed document.")
        return document_result(document)




class DocumentReprocessor:
    def __init__(
        self,
        document_repo: DocumentRepository,
        processing_service: DocumentProcessingService,
    ) -> None:
        self._document_repo = document_repo
        self._processing_service = processing_service

    async def __call__(self, *, user_id: UUID, document_id: UUID) -> DocumentResult:
        document = await self._document_repo.get_by_id(document_id)

        if document is None:
            raise DocumentNotFoundException("document not found")
        ensure_document_owner(document, user_id)
        await self._processing_service.queue(document, message="Queued for reprocessing.")
        return document_result(document)




INTAKE_STATUS_RECEIVED = "RECEIVED"
INTAKE_STATUS_QUEUED = "QUEUED"
INTAKE_STATUS_FAILED = "FAILED"


class ExternalItemIngester:
    def __init__(
        self,
        session: AsyncSession,
        external_intake_repo: ExternalIntakeRepository,
        document_repo: DocumentRepository,
        ingest_document: DocumentIngester,
    ) -> None:
        self._session = session
        self._external_intake_repo = external_intake_repo
        self._document_repo = document_repo
        self._ingest_document = ingest_document

    async def __call__(
        self,
        *,
        user_id: UUID,
        api_key_id: UUID | None,
        provider: str,
        title: str,
        type: DocumentType,
        collection_id: UUID | None = None,
        tags: list[str] | None = None,
        source_url: str | None = None,
        raw_content: str | None = None,
        language: str | None = None,
        external_id: str | None = None,
        idempotency_key: str | None = None,
        payload_metadata: dict[str, object] | None = None,
    ) -> ExternalIngestResult:
        normalized_provider = normalize_provider(provider)
        normalized_idempotency_key = normalize_idempotency_key(
            explicit=idempotency_key,
            external_id=external_id,
            source_url=source_url,
        )
        normalized_tags = normalize_tags(tags or [])
        metadata = dict(payload_metadata or {})
        if normalized_tags:
            metadata["tags"] = normalized_tags

        existing = await self._get_existing(user_id, normalized_provider, normalized_idempotency_key)
        if existing is not None:
            return await self._existing_result(existing)

        intake_item, created = await self._create_intake_item(
            user_id=user_id,
            api_key_id=api_key_id,
            provider=normalized_provider,
            title=title,
            type=type,
            collection_id=collection_id,
            tags=normalized_tags,
            source_url=source_url,
            raw_content=raw_content,
            language=language,
            external_id=external_id,
            idempotency_key=normalized_idempotency_key,
            payload_metadata=metadata,
        )
        if not created:
            return await self._existing_result(intake_item)

        try:
            document = await self._ingest_document(
                user_id=user_id,
                title=title,
                type=type,
                collection_id=collection_id,
                tags=normalized_tags,
                source_url=source_url,
                raw_content=raw_content,
                language=language,
            )
        except Exception as exc:
            await self._mark_failed(intake_item.id, sanitize_error(exc))
            raise

        queued = await self._mark_queued(intake_item.id, document.id)
        return ExternalIngestResult(intake_item=external_intake_item(queued), document=document)

    async def _get_existing(
        self,
        user_id: UUID,
        provider: str,
        idempotency_key: str | None,
    ) -> ExternalIntakeItemRecord | None:
        if idempotency_key is None:
            return None
        return await self._external_intake_repo.get_by_idempotency_key(
            user_id=user_id,
            provider=provider,
            idempotency_key=idempotency_key,
        )

    async def _existing_result(self, record: ExternalIntakeItemRecord) -> ExternalIngestResult:
        document = None
        if record.document_id is not None:
            entity = await self._document_repo.get_by_id(record.document_id)
            if entity is not None and entity.user_id == record.user_id:
                document = document_result(entity)
        return ExternalIngestResult(intake_item=external_intake_item(record), document=document)

    async def _create_intake_item(
        self,
        *,
        user_id: UUID,
        api_key_id: UUID | None,
        provider: str,
        title: str,
        type: DocumentType,
        collection_id: UUID | None,
        idempotency_key: str | None,
        tags: list[str],
        source_url: str | None,
        raw_content: str | None,
        language: str | None,
        external_id: str | None,
        payload_metadata: dict[str, object],
    ) -> tuple[ExternalIntakeItemRecord, bool]:
        now = datetime.now(UTC)
        record = ExternalIntakeItemRecord(
            id=uuid4(),
            user_id=user_id,
            api_key_id=api_key_id,
            provider=provider,
            external_id=normalize_optional(external_id),
            idempotency_key=idempotency_key,
            title=title.strip(),
            type=type,
            collection_id=collection_id,
            tags=tags,
            source_url=normalize_optional(source_url),
            raw_content=raw_content,
            language=normalize_optional(language),
            status=INTAKE_STATUS_RECEIVED,
            error_reason=None,
            document_id=None,
            payload_metadata=payload_metadata,
            created_at=now,
        )
        created = await self._external_intake_repo.create(record)
        await self._session.flush()
        return created, created.id == record.id

    async def _mark_queued(self, intake_item_id: UUID, document_id: UUID) -> ExternalIntakeItemRecord:
        queued = await self._external_intake_repo.mark_queued(
            intake_item_id=intake_item_id,
            document_id=document_id,
        )
        await self._session.flush()
        return queued

    async def _mark_failed(self, intake_item_id: UUID, error_reason: str) -> ExternalIntakeItemRecord:
        failed = await self._external_intake_repo.mark_failed(
            intake_item_id=intake_item_id,
            error_reason=error_reason,
        )
        await self._session.flush()
        return failed


class ExternalIntakeService:
    def __init__(
        self,
        session: AsyncSession,
        external_intake_repo: ExternalIntakeRepository,
        document_repo: DocumentRepository,
        ingest_document: DocumentIngester,
    ) -> None:
        self._session = session
        self._external_intake_repo = external_intake_repo
        self._document_repo = document_repo
        self._ingest_document = ingest_document

    async def get(self, *, user_id: UUID, intake_item_id: UUID) -> ExternalIngestResult:
        record = await self._external_intake_repo.get_by_id(user_id=user_id, intake_item_id=intake_item_id)
        if record is None:
            raise ResourceNotFoundException("intake item not found")
        return await _intake_result(self._document_repo, record)

    async def list(self, *, user_id: UUID, limit: int = 20, offset: int = 0) -> list[ExternalIntakeItem]:
        records = await self._external_intake_repo.list_by_user_id(
            user_id=user_id,
            limit=limit,
            offset=offset,
        )
        return [external_intake_item(record) for record in records]

    async def retry(self, *, user_id: UUID, intake_item_id: UUID) -> ExternalIngestResult:
        record = await self._external_intake_repo.get_by_id(user_id=user_id, intake_item_id=intake_item_id)
        if record is None:
            raise ResourceNotFoundException("intake item not found")
        if record.status != INTAKE_STATUS_FAILED:
            return await _intake_result(self._document_repo, record)

        try:
            document = await self._ingest_document(
                user_id=record.user_id,
                title=record.title,
                type=record.type,
                collection_id=record.collection_id,
                tags=record.tags,
                source_url=record.source_url,
                raw_content=record.raw_content,
                language=record.language,
            )
        except Exception as exc:
            await self._external_intake_repo.mark_failed(
                intake_item_id=record.id,
                error_reason=sanitize_error(exc),
            )
            await self._session.flush()
            raise

        queued = await self._external_intake_repo.mark_queued(
            intake_item_id=record.id,
            document_id=document.id,
        )
        await self._session.flush()
        return ExternalIngestResult(intake_item=external_intake_item(queued), document=document)


def normalize_provider(provider: str) -> str:
    normalized = provider.strip().lower()
    if not normalized:
        raise ValidationException("provider is required")
    if len(normalized) > 80:
        raise ValidationException("provider is too long")
    return normalized


def normalize_idempotency_key(*, explicit: str | None, external_id: str | None, source_url: str | None) -> str | None:
    explicit = normalize_optional(explicit)
    if explicit:
        return explicit[:200]
    external_id = normalize_optional(external_id)
    if external_id:
        return external_id[:200]
    if source_url:
        return hashlib.sha256(source_url.strip().encode("utf-8")).hexdigest()
    return None


def normalize_tags(tags: list[str]) -> list[str]:
    normalized: list[str] = []
    for tag in tags:
        value = tag.strip()
        if not value or value in normalized:
            continue
        if len(value) > 80:
            raise ValidationException("tag is too long")
        normalized.append(value)
    return normalized[:20]


def normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def sanitize_error(exc: Exception) -> str:
    message = str(exc).strip() or type(exc).__name__
    return message[:500]


def external_intake_item(record: ExternalIntakeItemRecord) -> ExternalIntakeItem:
    return ExternalIntakeItem(
        id=record.id,
        user_id=record.user_id,
        api_key_id=record.api_key_id,
        provider=record.provider,
        external_id=record.external_id,
        idempotency_key=record.idempotency_key,
        title=record.title,
        type=record.type,
        collection_id=record.collection_id,
        tags=record.tags,
        source_url=record.source_url,
        status=record.status,
        error_reason=record.error_reason,
        document_id=record.document_id,
        payload_metadata=record.payload_metadata,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


async def _intake_result(
    document_repo: DocumentRepository,
    record: ExternalIntakeItemRecord,
) -> ExternalIngestResult:
    document = None
    if record.document_id is not None:
        entity = await document_repo.get_by_id(record.document_id)
        if entity is not None and entity.user_id == record.user_id:
            document = document_result(entity)
    return ExternalIngestResult(intake_item=external_intake_item(record), document=document)
