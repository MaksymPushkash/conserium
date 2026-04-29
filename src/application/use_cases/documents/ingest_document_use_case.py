"""IngestDocumentUseCase — async ingestion entry point.

Responsibilities:
1. Create a DocumentEntity with status=PENDING.
2. Persist it to the database (so the caller gets an ID immediately).
3. Transition status to QUEUED + set initial Redis status.
4. Dispatch the Celery `process_document` task.
5. Return the DocumentDTO (status=QUEUED) with 202 semantics.

The use case deliberately does NOT know about Celery internals —
it receives an ICeleryDispatcher interface, keeping the application
layer decoupled from infrastructure.
"""

from __future__ import annotations

import uuid

from src.application.dtos.document_dtos import DocumentDTO
from src.application.dtos.ingestion_dtos import IngestDocumentDTO
from src.application.interfaces.document_status_cache import IDocumentStatusCache
from src.application.interfaces.task_dispatcher import ITaskDispatcher
from src.application.interfaces.unit_of_work import IUnitOfWork
from src.application.use_cases.documents.base import document_to_dto
from src.domain.entities.document_entity import DocumentEntity


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
        document = DocumentEntity.create(
            id=uuid.uuid4(),
            user_id=dto.user_id,
            title=dto.title,
            type=dto.type,
            collection_id=dto.collection_id,
            source_url=dto.source_url,
            file_path=dto.file_path,
            file_size_bytes=dto.file_size_bytes,
        )
        # PENDING → QUEUED before persisting so the DB row is never left in PENDING
        document.mark_queued()

        async with self._uow:
            await self._uow.document_repo.create(document)
            await self._uow.commit()

        # Set initial Redis status before dispatching so GET /status always
        # returns something meaningful from the moment the task is sent.
        await self._status_cache.set_status(
            document.id,
            status="QUEUED",
            progress=0,
            message="Queued for processing.",
        )

        # Dispatch — fire and forget
        await self._task_dispatcher.dispatch_process_document(str(document.id))

        return document_to_dto(document)
