from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.use_cases.documents.base import ensure_collection_owner
from src.application.use_cases.documents.notes.helpers import (
    get_note,
    normalize_content,
    normalize_title,
    note_to_dto,
    note_update_changed,
    queue_note_processing,
    save_note_version,
)

if TYPE_CHECKING:
    from src.application.dtos.note_dtos import NoteDTO, UpdateNoteDTO
    from src.application.ports.cache.document_status_cache import IDocumentStatusCache
    from src.application.ports.ingestion.task_dispatcher import ITaskDispatcher
    from src.application.ports.persistence.unit_of_work import IUnitOfWork


class UpdateNoteUseCase:
    def __init__(
        self,
        uow: IUnitOfWork,
        status_cache: IDocumentStatusCache,
        task_dispatcher: ITaskDispatcher,
    ) -> None:
        self._uow = uow
        self._status_cache = status_cache
        self._task_dispatcher = task_dispatcher

    async def __call__(self, dto: UpdateNoteDTO) -> NoteDTO:
        document = await get_note(self._uow, user_id=dto.user_id, note_id=dto.note_id)
        content = normalize_content(dto.content)
        has_content = bool(content.strip())
        async with self._uow:
            await ensure_collection_owner(self._uow, dto.collection_id, dto.user_id)
        previous_document = document.snapshot()
        next_title = normalize_title(dto.title, content)
        if not note_update_changed(
            document,
            title=next_title,
            content=content,
            collection_id=dto.collection_id,
            language=dto.language,
        ):
            return note_to_dto(document)

        document.rename(next_title)
        document.assign_collection(dto.collection_id)
        document.update_content(
            raw_content=content if has_content else None,
            word_count=len(content.split()),
            language=dto.language,
        )
        if has_content:
            document.mark_queued()
        else:
            document.mark_ready()

        async with self._uow:
            await save_note_version(self._uow, previous_document, document)
            await self._uow.document_repo.update(document)
            if not has_content:
                await self._uow.chunk_repo.delete_by_document_id(document.id)
            await self._uow.commit()

        if has_content:
            await queue_note_processing(
                document=document,
                status_cache=self._status_cache,
                task_dispatcher=self._task_dispatcher,
                uow=self._uow,
            )
        return note_to_dto(document)
