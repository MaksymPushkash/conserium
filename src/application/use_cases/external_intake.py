from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from src.application.dtos.external_intake_dtos import ExternalIngestDTO, ExternalIngestResultDTO, ExternalIntakeItemDTO
from src.application.dtos.ingestion_dtos import IngestDocumentDTO
from src.application.ports.persistence.external_intake_repository import ExternalIntakeItemRecord
from src.application.use_cases.documents.base import document_to_dto
from src.domain.exceptions import ResourceNotFoundException, ValidationException

if TYPE_CHECKING:
    from src.application.ports.persistence.unit_of_work import IUnitOfWork
    from src.application.use_cases.documents.ingest_document_use_case import IngestDocumentUseCase


INTAKE_STATUS_RECEIVED = "RECEIVED"
INTAKE_STATUS_QUEUED = "QUEUED"
INTAKE_STATUS_FAILED = "FAILED"


class IngestExternalItemUseCase:
    def __init__(self, uow: IUnitOfWork, ingest_document: IngestDocumentUseCase) -> None:
        self._uow = uow
        self._ingest_document = ingest_document

    async def __call__(self, dto: ExternalIngestDTO) -> ExternalIngestResultDTO:
        provider = normalize_provider(dto.provider)
        idempotency_key = normalize_idempotency_key(dto)
        tags = normalize_tags(dto.tags or [])
        payload_metadata = dict(dto.payload_metadata or {})
        if tags:
            payload_metadata["tags"] = tags

        existing = await self._get_existing(dto.user_id, provider, idempotency_key)
        if existing is not None:
            return await self._existing_result(existing)

        intake_item, created = await self._create_intake_item(dto, provider, idempotency_key, tags, payload_metadata)
        if not created:
            return await self._existing_result(intake_item)

        try:
            document = await self._ingest_document(
                IngestDocumentDTO(
                    user_id=dto.user_id,
                    title=dto.title,
                    type=dto.type,
                    collection_id=dto.collection_id,
                    tags=tags,
                    source_url=dto.source_url,
                    raw_content=dto.raw_content,
                    language=dto.language,
                )
            )
        except Exception as exc:
            await self._mark_failed(intake_item.id, sanitize_error(exc))
            raise

        queued = await self._mark_queued(intake_item.id, document.id)
        return ExternalIngestResultDTO(intake_item=external_intake_dto(queued), document=document)

    async def _get_existing(
        self,
        user_id: UUID,
        provider: str,
        idempotency_key: str | None,
    ) -> ExternalIntakeItemRecord | None:
        if idempotency_key is None:
            return None
        async with self._uow:
            return await self._uow.external_intake_repo.get_by_idempotency_key(
                user_id=user_id,
                provider=provider,
                idempotency_key=idempotency_key,
            )

    async def _existing_result(self, record: ExternalIntakeItemRecord) -> ExternalIngestResultDTO:
        document = None
        if record.document_id is not None:
            async with self._uow:
                entity = await self._uow.document_repo.get_by_id(record.document_id)
                if entity is not None and entity.user_id == record.user_id:
                    document = document_to_dto(entity)
        return ExternalIngestResultDTO(intake_item=external_intake_dto(record), document=document)

    async def _create_intake_item(
        self,
        dto: ExternalIngestDTO,
        provider: str,
        idempotency_key: str | None,
        tags: list[str],
        payload_metadata: dict[str, object],
    ) -> tuple[ExternalIntakeItemRecord, bool]:
        now = datetime.now(UTC)
        record = ExternalIntakeItemRecord(
            id=uuid4(),
            user_id=dto.user_id,
            api_key_id=dto.api_key_id,
            provider=provider,
            external_id=normalize_optional(dto.external_id),
            idempotency_key=idempotency_key,
            title=dto.title.strip(),
            type=dto.type,
            collection_id=dto.collection_id,
            tags=tags,
            source_url=normalize_optional(dto.source_url),
            raw_content=dto.raw_content,
            language=normalize_optional(dto.language),
            status=INTAKE_STATUS_RECEIVED,
            error_reason=None,
            document_id=None,
            payload_metadata=payload_metadata,
            created_at=now,
        )
        async with self._uow:
            created = await self._uow.external_intake_repo.create(record)
            await self._uow.commit()
        return created, created.id == record.id

    async def _mark_queued(self, intake_item_id: UUID, document_id: UUID) -> ExternalIntakeItemRecord:
        async with self._uow:
            queued = await self._uow.external_intake_repo.mark_queued(
                intake_item_id=intake_item_id,
                document_id=document_id,
            )
            await self._uow.commit()
        return queued

    async def _mark_failed(self, intake_item_id: UUID, error_reason: str) -> ExternalIntakeItemRecord:
        async with self._uow:
            failed = await self._uow.external_intake_repo.mark_failed(
                intake_item_id=intake_item_id,
                error_reason=error_reason,
            )
            await self._uow.commit()
        return failed


class GetExternalIntakeItemUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: UUID, intake_item_id: UUID) -> ExternalIngestResultDTO:
        async with self._uow:
            record = await self._uow.external_intake_repo.get_by_id(user_id=user_id, intake_item_id=intake_item_id)
        if record is None:
            raise ResourceNotFoundException("intake item not found")
        return await _intake_result(self._uow, record)


class ListExternalIntakeItemsUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: UUID, limit: int = 20, offset: int = 0) -> list[ExternalIntakeItemDTO]:
        async with self._uow:
            records = await self._uow.external_intake_repo.list_by_user_id(
                user_id=user_id,
                limit=limit,
                offset=offset,
            )
        return [external_intake_dto(record) for record in records]


class RetryExternalIntakeItemUseCase:
    def __init__(self, uow: IUnitOfWork, ingest_document: IngestDocumentUseCase) -> None:
        self._uow = uow
        self._ingest_document = ingest_document

    async def __call__(self, *, user_id: UUID, intake_item_id: UUID) -> ExternalIngestResultDTO:
        async with self._uow:
            record = await self._uow.external_intake_repo.get_by_id(user_id=user_id, intake_item_id=intake_item_id)
        if record is None:
            raise ResourceNotFoundException("intake item not found")
        if record.status != INTAKE_STATUS_FAILED:
            return await _intake_result(self._uow, record)

        try:
            document = await self._ingest_document(
                IngestDocumentDTO(
                    user_id=record.user_id,
                    title=record.title,
                    type=record.type,
                    collection_id=record.collection_id,
                    tags=record.tags,
                    source_url=record.source_url,
                    raw_content=record.raw_content,
                    language=record.language,
                )
            )
        except Exception as exc:
            async with self._uow:
                await self._uow.external_intake_repo.mark_failed(
                    intake_item_id=record.id,
                    error_reason=sanitize_error(exc),
                )
                await self._uow.commit()
            raise

        async with self._uow:
            queued = await self._uow.external_intake_repo.mark_queued(
                intake_item_id=record.id,
                document_id=document.id,
            )
            await self._uow.commit()
        return ExternalIngestResultDTO(intake_item=external_intake_dto(queued), document=document)


def normalize_provider(provider: str) -> str:
    normalized = provider.strip().lower()
    if not normalized:
        raise ValidationException("provider is required")
    if len(normalized) > 80:
        raise ValidationException("provider is too long")
    return normalized


def normalize_idempotency_key(dto: ExternalIngestDTO) -> str | None:
    explicit = normalize_optional(dto.idempotency_key)
    if explicit:
        return explicit[:200]
    external_id = normalize_optional(dto.external_id)
    if external_id:
        return external_id[:200]
    if dto.source_url:
        return hashlib.sha256(dto.source_url.strip().encode("utf-8")).hexdigest()
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


def external_intake_dto(record: ExternalIntakeItemRecord) -> ExternalIntakeItemDTO:
    return ExternalIntakeItemDTO(
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


async def _intake_result(uow: IUnitOfWork, record: ExternalIntakeItemRecord) -> ExternalIngestResultDTO:
    document = None
    if record.document_id is not None:
        async with uow:
            entity = await uow.document_repo.get_by_id(record.document_id)
            if entity is not None and entity.user_id == record.user_id:
                document = document_to_dto(entity)
    return ExternalIngestResultDTO(intake_item=external_intake_dto(record), document=document)
