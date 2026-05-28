from __future__ import annotations

import uuid
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from src.application.dtos.note_dtos import NoteDTO, NoteListItemDTO
from src.application.dtos.note_version_dtos import NoteVersionDTO
from src.application.ports.persistence.note_version_repository import NoteVersionRecord
from src.application.use_cases.documents.base import ensure_document_owner
from src.application.use_cases.documents.document_processing_outbox import (
    DOCUMENT_PROCESSING_TASK_NAME,
    kick_document_processing_outbox_item,
)
from src.domain.exceptions import DocumentNotFoundException
from src.domain.value_objects.document_type import DocumentType

if TYPE_CHECKING:
    from src.application.ports.cache.document_status_cache import IDocumentStatusCache
    from src.application.ports.ingestion.task_dispatcher import ITaskDispatcher
    from src.application.ports.persistence.unit_of_work import IUnitOfWork
    from src.domain.entities.document_entity import DocumentEntity

NOTE_VERSION_COALESCE_WINDOW = timedelta(seconds=60)


async def get_note(uow: IUnitOfWork, *, user_id: uuid.UUID, note_id: uuid.UUID) -> DocumentEntity:
    async with uow:
        document = await uow.document_repo.get_by_id(note_id)
    if document is None or document.type != DocumentType.MARKDOWN:
        raise DocumentNotFoundException("note not found")
    ensure_document_owner(document, user_id)
    return document


async def save_note_version(
    uow: IUnitOfWork,
    previous_document: DocumentEntity,
    current_document: DocumentEntity,
    *,
    force: bool = False,
) -> None:
    if not note_content_changed(previous_document, current_document):
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


def note_update_changed(
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


def note_content_changed(previous_document: DocumentEntity, current_document: DocumentEntity) -> bool:
    return (
        previous_document.title != current_document.title
        or (previous_document.raw_content or "") != (current_document.raw_content or "")
    )


async def queue_note_processing(
    *,
    document: DocumentEntity,
    status_cache: IDocumentStatusCache,
    task_dispatcher: ITaskDispatcher,
    uow: IUnitOfWork,
) -> None:
    document.mark_queued()
    async with uow:
        await uow.document_repo.update(document)
        outbox = await uow.document_processing_outbox_repo.create_outbox(
            document_id=document.id,
            task_name=DOCUMENT_PROCESSING_TASK_NAME,
        )
        await uow.commit()

    with suppress(Exception):
        await status_cache.set_status(
            document.id,
            status="QUEUED",
            progress=0,
            message="Queued note for memory indexing.",
        )
    with suppress(Exception):
        await kick_document_processing_outbox_item(
            outbox_id=outbox.id,
            document_id=document.id,
            uow=uow,
            task_dispatcher=task_dispatcher,
        )


def note_to_dto(document: DocumentEntity) -> NoteDTO:
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


def note_version_to_dto(version: NoteVersionRecord) -> NoteVersionDTO:
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


def note_to_list_item_dto(document: DocumentEntity) -> NoteListItemDTO:
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


def normalize_title(title: str | None, content: str | None) -> str:
    normalized = (title or "").strip()
    if normalized:
        return normalized[:120]
    first_line = next((line.strip() for line in (content or "").splitlines() if line.strip()), "")
    return first_line[:120] or "Untitled"


def normalize_content(content: str | None) -> str:
    return content or ""
