from __future__ import annotations

import uuid
from contextlib import suppress
from typing import TYPE_CHECKING

from src.application.dtos.note_dtos import (
    CreateNoteDTO,
    GetNoteDTO,
    ListNotesDTO,
    NoteDTO,
    NoteListDTO,
    NoteListItemDTO,
    UpdateNoteDTO,
)
from src.application.use_cases.documents.base import ensure_document_owner
from src.domain.entities.document_entity import DocumentEntity
from src.domain.exceptions import DocumentNotFoundException
from src.domain.value_objects.document_type import DocumentType

if TYPE_CHECKING:
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
        title = _normalize_title(dto.title, dto.content)
        content = _normalize_content(dto.content)
        has_content = bool(content.strip())
        document = DocumentEntity.create(
            id=uuid.uuid4(),
            user_id=dto.user_id,
            title=title,
            type=DocumentType.MARKDOWN,
            raw_content=content if has_content else None,
            word_count=len(content.split()),
            language=dto.language,
        )
        if has_content:
            document.mark_queued()
        else:
            document.mark_ready()

        async with self._uow:
            await self._uow.document_repo.create(document)
            await self._uow.commit()

        if has_content:
            await _queue_note_processing(
                document=document,
                status_cache=self._status_cache,
                task_dispatcher=self._task_dispatcher,
                uow=self._uow,
            )
        return _note_to_dto(document)


class ListNotesUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, dto: ListNotesDTO) -> NoteListDTO:
        async with self._uow:
            paged_notes = await self._uow.document_repo.get_by_user_id(
                dto.user_id,
                limit=dto.limit,
                offset=dto.offset,
                document_type=DocumentType.MARKDOWN,
            )
            total = await self._uow.document_repo.count_by_user_id(
                dto.user_id,
                document_type=DocumentType.MARKDOWN,
            )
        return NoteListDTO(
            items=[_note_to_list_item_dto(document) for document in paged_notes],
            total=total,
            limit=dto.limit,
            offset=dto.offset,
        )


class GetNoteUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, dto: GetNoteDTO) -> NoteDTO:
        document = await _get_note(self._uow, user_id=dto.user_id, note_id=dto.note_id)
        return _note_to_dto(document)


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
        document = await _get_note(self._uow, user_id=dto.user_id, note_id=dto.note_id)
        content = _normalize_content(dto.content)
        has_content = bool(content.strip())
        document.rename(_normalize_title(dto.title, content))
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
            await self._uow.document_repo.update(document)
            if not has_content:
                await self._uow.chunk_repo.delete_by_document_id(document.id)
            await self._uow.commit()

        if has_content:
            await _queue_note_processing(
                document=document,
                status_cache=self._status_cache,
                task_dispatcher=self._task_dispatcher,
                uow=self._uow,
            )
        return _note_to_dto(document)


class DeleteNoteUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: uuid.UUID, note_id: uuid.UUID) -> None:
        document = await _get_note(self._uow, user_id=user_id, note_id=note_id)
        async with self._uow:
            await self._uow.document_repo.delete(document.id)
            await self._uow.commit()


async def _get_note(uow: IUnitOfWork, *, user_id: uuid.UUID, note_id: uuid.UUID) -> DocumentEntity:
    async with uow:
        document = await uow.document_repo.get_by_id(note_id)
    if document is None or document.type != DocumentType.MARKDOWN:
        raise DocumentNotFoundException("note not found")
    ensure_document_owner(document, user_id)
    return document


async def _queue_note_processing(
    *,
    document: DocumentEntity,
    status_cache: IDocumentStatusCache,
    task_dispatcher: ITaskDispatcher,
    uow: IUnitOfWork,
) -> None:
    await status_cache.set_status(
        document.id,
        status="QUEUED",
        progress=0,
        message="Queued note for memory indexing.",
    )
    try:
        await task_dispatcher.dispatch_process_document(str(document.id))
    except Exception:
        document.mark_failed()
        try:
            async with uow:
                await uow.document_repo.update(document)
                await uow.commit()
        finally:
            with suppress(Exception):
                await status_cache.set_status(
                    document.id,
                    status="FAILED",
                    progress=0,
                    message="Failed to queue note for memory indexing.",
                )
        raise


def _note_to_dto(document: DocumentEntity) -> NoteDTO:
    return NoteDTO(
        id=document.id,
        title=document.title,
        content=document.raw_content or "",
        status=document.status,
        word_count=document.word_count or 0,
        language=document.language,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def _note_to_list_item_dto(document: DocumentEntity) -> NoteListItemDTO:
    return NoteListItemDTO(
        id=document.id,
        title=document.title,
        status=document.status,
        word_count=document.word_count or 0,
        language=document.language,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def _normalize_title(title: str | None, content: str | None) -> str:
    normalized = (title or "").strip()
    if normalized:
        return normalized[:120]
    first_line = next((line.strip() for line in (content or "").splitlines() if line.strip()), "")
    return first_line[:120] or "Untitled"


def _normalize_content(content: str | None) -> str:
    return content or ""
