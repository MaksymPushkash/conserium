from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from src.application.use_cases.documents.base import document_to_dto, ensure_collection_owner
from src.application.use_cases.documents.queue_document_processing import queue_document_processing
from src.domain.entities.document_entity import DocumentEntity
from src.domain.exceptions import DocumentValidationException
from src.domain.value_objects.document_type import DocumentType

if TYPE_CHECKING:
    from src.application.dtos.document_dtos import DocumentDTO
    from src.application.dtos.ingestion_dtos import IngestDocumentDTO
    from src.application.ports.cache.document_status_cache import IDocumentStatusCache
    from src.application.ports.ingestion.task_dispatcher import ITaskDispatcher
    from src.application.ports.persistence.unit_of_work import IUnitOfWork


class IngestDocumentUseCase:
    def __init__(
        self,
        uow: IUnitOfWork,
        status_cache: IDocumentStatusCache,
        task_dispatcher: ITaskDispatcher,
    ) -> None:
        self._uow = uow
        self._status_cache = status_cache
        self._task_dispatcher = task_dispatcher

    async def __call__(self, dto: IngestDocumentDTO) -> DocumentDTO:
        if dto.type in (DocumentType.TEXT, DocumentType.MARKDOWN) and not (dto.raw_content and dto.raw_content.strip()):
            raise DocumentValidationException("raw_content is required for text ingestion")
        if dto.type in (DocumentType.URL, DocumentType.YOUTUBE) and not dto.source_url:
            raise DocumentValidationException(f"source_url is required for {dto.type.value.lower()} ingestion")
        if dto.type in (DocumentType.PDF, DocumentType.IMAGE) and not dto.file_path:
            raise DocumentValidationException(f"file_path is required for {dto.type.value} ingestion")

        async with self._uow:
            await ensure_collection_owner(self._uow, dto.collection_id, dto.user_id)

        document = DocumentEntity.create(
            id=uuid.uuid4(),
            user_id=dto.user_id,
            title=dto.title,
            type=dto.type,
            collection_id=dto.collection_id,
            source_url=dto.source_url,
            file_path=dto.file_path,
            file_size_bytes=dto.file_size_bytes,
            raw_content=dto.raw_content,
            word_count=len(dto.raw_content.split()) if dto.raw_content else None,
            language=dto.language,
            tags=dto.tags,
        )

        document.mark_queued()

        async with self._uow:
            await self._uow.document_repo.create(document)
            await self._uow.document_activity_repo.record_event(
                user_id=dto.user_id,
                document_id=document.id,
                event_type="created",
            )
            await self._uow.commit()

        await queue_document_processing(
            document=document,
            uow=self._uow,
            status_cache=self._status_cache,
            task_dispatcher=self._task_dispatcher,
            message="Queued for processing.",
        )

        return document_to_dto(document)
