from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from src.application.use_cases.documents.base import ensure_collection_owner
from src.application.use_cases.documents.notes.helpers import (
    normalize_content,
    normalize_title,
    note_to_dto,
    queue_note_processing,
)
from src.domain.entities.document_entity import DocumentEntity
from src.domain.value_objects.document_type import DocumentType

if TYPE_CHECKING:
    from src.application.dtos.note_dtos import CreateNoteDTO, NoteDTO
    from src.application.ports.cache.document_status_cache import IDocumentStatusCache
    from src.application.ports.ingestion.task_dispatcher import ITaskDispatcher
    from src.application.ports.persistence.unit_of_work import IUnitOfWork


class CreateNoteUseCase:
    def __init__(
        self,
        uow: IUnitOfWork,
        status_cache: IDocumentStatusCache,
        task_dispatcher: ITaskDispatcher,
    ) -> None:
        self._uow = uow
        self._status_cache = status_cache
        self._task_dispatcher = task_dispatcher

    async def __call__(self, dto: CreateNoteDTO) -> NoteDTO:
        title = normalize_title(dto.title, dto.content)
        content = normalize_content(dto.content)
        has_content = bool(content.strip())
        async with self._uow:
            await ensure_collection_owner(self._uow, dto.collection_id, dto.user_id)
        document = DocumentEntity.create(
            id=uuid.uuid4(),
            user_id=dto.user_id,
            collection_id=dto.collection_id,
            title=title,
            type=DocumentType.MARKDOWN,
            raw_content=content if has_content else None,
            word_count=len(content.split()),
            language=dto.language,
        )
        if not has_content:
            document.mark_ready()

        async with self._uow:
            await self._uow.document_repo.create(document)
            await self._uow.commit()

        if has_content:
            await queue_note_processing(
                document=document,
                status_cache=self._status_cache,
                task_dispatcher=self._task_dispatcher,
                uow=self._uow,
            )
        return note_to_dto(document)
