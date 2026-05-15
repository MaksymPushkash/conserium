from __future__ import annotations

import uuid
from contextlib import suppress
from datetime import UTC, datetime, timedelta
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
from src.application.dtos.note_version_dtos import NoteVersionDTO
from src.application.ports.persistence.note_version_repository import NoteVersionRecord
from src.application.use_cases.documents.base import ensure_collection_owner, ensure_document_owner
from src.domain.entities.document_entity import DocumentEntity
from src.domain.exceptions import DocumentNotFoundException
from src.domain.value_objects.document_type import DocumentType

if TYPE_CHECKING:
    from src.application.ports.cache.document_status_cache import IDocumentStatusCache
    from src.application.ports.ingestion.task_dispatcher import ITaskDispatcher
    from src.application.ports.persistence.unit_of_work import IUnitOfWork

NOTE_VERSION_COALESCE_WINDOW = timedelta(seconds=60)


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
                collection_id=dto.collection_id,
            )
            total = await self._uow.document_repo.count_by_user_id(
                dto.user_id,
                document_type=DocumentType.MARKDOWN,
                collection_id=dto.collection_id,
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
        async with self._uow:
            await ensure_collection_owner(self._uow, dto.collection_id, dto.user_id)
        previous_document = _copy_document(document)
        next_title = _normalize_title(dto.title, content)
        if not _note_update_changed(
            document,
            title=next_title,
            content=content,
            collection_id=dto.collection_id,
            language=dto.language,
        ):
            return _note_to_dto(document)

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
            await _save_note_version(self._uow, previous_document, document)
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


class ListNoteVersionsUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: uuid.UUID, note_id: uuid.UUID) -> list[NoteVersionDTO]:
        await _get_note(self._uow, user_id=user_id, note_id=note_id)
        async with self._uow:
            versions = await self._uow.note_version_repo.list_by_note_id(note_id=note_id, user_id=user_id)
        return [_note_version_to_dto(version) for version in versions]


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

    async def __call__(self, *, user_id: uuid.UUID, note_id: uuid.UUID, version_id: uuid.UUID) -> NoteDTO:
        document = await _get_note(self._uow, user_id=user_id, note_id=note_id)
        async with self._uow:
            version = await self._uow.note_version_repo.get_by_id(
                version_id=version_id,
                note_id=note_id,
                user_id=user_id,
            )
        if version is None:
            raise DocumentNotFoundException("note version not found")

        previous_document = _copy_document(document)
        content = _normalize_content(version.content)
        has_content = bool(content.strip())
        if not _note_update_changed(
            document,
            title=version.title,
            content=content,
            collection_id=document.collection_id,
            language=document.language,
        ):
            return _note_to_dto(document)

        document.rename(version.title)
        document.update_content(
            raw_content=content if has_content else None,
            word_count=len(content.split()),
            language=document.language,
        )
        if has_content:
            document.mark_queued()
        else:
            document.mark_ready()

        async with self._uow:
            await _save_note_version(self._uow, previous_document, document, force=True)
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


async def _get_note(uow: IUnitOfWork, *, user_id: uuid.UUID, note_id: uuid.UUID) -> DocumentEntity:
    async with uow:
        document = await uow.document_repo.get_by_id(note_id)
    if document is None or document.type != DocumentType.MARKDOWN:
        raise DocumentNotFoundException("note not found")
    ensure_document_owner(document, user_id)
    return document


async def _save_note_version(
    uow: IUnitOfWork,
    previous_document: DocumentEntity,
    current_document: DocumentEntity,
    *,
    force: bool = False,
) -> None:
    if not _note_content_changed(previous_document, current_document):
        return
    if not force:
        versions = await uow.note_version_repo.list_by_note_id(
            note_id=previous_document.id,
            user_id=previous_document.user_id,
        )
        latest = versions[0] if versions else None
        if latest and latest.created_at and datetime.now(UTC) - latest.created_at < NOTE_VERSION_COALESCE_WINDOW:
            return
    version_number = await uow.note_version_repo.count_by_note_id(previous_document.id) + 1
    await uow.note_version_repo.create(
        NoteVersionRecord(
            id=uuid.uuid4(),
            note_id=previous_document.id,
            user_id=previous_document.user_id,
            version_number=version_number,
            title=previous_document.title,
            content=previous_document.raw_content or "",
        )
    )


def _note_update_changed(
    document: DocumentEntity,
    *,
    title: str,
    content: str,
    collection_id: uuid.UUID | None,
    language: str | None,
) -> bool:
    return (
        document.title != title
        or (document.raw_content or "") != content
        or document.collection_id != collection_id
        or document.language != language
    )


def _note_content_changed(previous_document: DocumentEntity, current_document: DocumentEntity) -> bool:
    return (
        previous_document.title != current_document.title
        or (previous_document.raw_content or "") != (current_document.raw_content or "")
    )


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
        collection_id=document.collection_id,
        title=document.title,
        content=document.raw_content or "",
        status=document.status,
        word_count=document.word_count or 0,
        language=document.language,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def _note_version_to_dto(version: NoteVersionRecord) -> NoteVersionDTO:
    if version.created_at is None:
        raise ValueError("note version created_at is required")
    return NoteVersionDTO(
        id=version.id,
        note_id=version.note_id,
        version_number=version.version_number,
        title=version.title,
        content=version.content,
        created_at=version.created_at,
    )


def _note_to_list_item_dto(document: DocumentEntity) -> NoteListItemDTO:
    return NoteListItemDTO(
        id=document.id,
        collection_id=document.collection_id,
        title=document.title,
        status=document.status,
        word_count=document.word_count or 0,
        language=document.language,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def _copy_document(document: DocumentEntity) -> DocumentEntity:
    return DocumentEntity(
        id=document.id,
        user_id=document.user_id,
        collection_id=document.collection_id,
        title=document.title,
        type=document.type,
        status=document.status,
        source_url=document.source_url,
        file_path=document.file_path,
        file_size_bytes=document.file_size_bytes,
        raw_content=document.raw_content,
        summary=document.summary,
        word_count=document.word_count,
        language=document.language,
        entities=document.entities,
        categories=document.categories,
        visual_metadata=document.visual_metadata,
        suggested_questions=document.suggested_questions,
        doc_embedding=document.doc_embedding,
        is_duplicate=document.is_duplicate,
        duplicate_of_id=document.duplicate_of_id,
        created_at=document.created_at,
        updated_at=document.updated_at,
        tags=document.tags,
    )


def _normalize_title(title: str | None, content: str | None) -> str:
    normalized = (title or "").strip()
    if normalized:
        return normalized[:120]
    first_line = next((line.strip() for line in (content or "").splitlines() if line.strip()), "")
    return first_line[:120] or "Untitled"


def _normalize_content(content: str | None) -> str:
    return content or ""
