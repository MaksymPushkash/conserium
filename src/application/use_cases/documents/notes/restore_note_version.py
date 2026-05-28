from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.use_cases.documents.notes.helpers import (
    get_note,
    normalize_content,
    note_to_dto,
    note_update_changed,
    queue_note_processing,
    save_note_version,
)
from src.domain.exceptions import DocumentNotFoundException

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.dtos.note_dtos import NoteDTO
    from src.application.ports.cache.document_status_cache import IDocumentStatusCache
    from src.application.ports.ingestion.task_dispatcher import ITaskDispatcher
    from src.application.ports.persistence.unit_of_work import IUnitOfWork


class RestoreNoteVersionUseCase:
    def __init__(
        self,
        uow: IUnitOfWork,
        status_cache: IDocumentStatusCache,
        task_dispatcher: ITaskDispatcher,
    ) -> None:
        self._uow = uow
        self._status_cache = status_cache
        self._task_dispatcher = task_dispatcher

    async def __call__(self, *, user_id: UUID, note_id: UUID, version_id: UUID) -> NoteDTO:
        document = await get_note(self._uow, user_id=user_id, note_id=note_id)
        async with self._uow:
            version = await self._uow.note_version_repo.get_by_id(
                version_id=version_id,
                note_id=note_id,
                user_id=user_id,
            )
        if version is None:
            raise DocumentNotFoundException("note version not found")

        previous_document = document.snapshot()
        content = normalize_content(version.content)
        has_content = bool(content.strip())
        if not note_update_changed(
            document,
            title=version.title,
            content=content,
            collection_id=document.collection_id,
            language=document.language,
        ):
            return note_to_dto(document)

        document.rename(version.title)
        document.update_content(
            raw_content=content if has_content else None,
            word_count=len(content.split()),
            language=document.language,
        )
        if not has_content:
            document.mark_ready()

        async with self._uow:
            await save_note_version(self._uow, previous_document, document, force=True)
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
