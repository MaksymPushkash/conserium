from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from src.billing.service import billing
from src.documents.repository import NoteVersionRecord
from src.documents.schemas import (
    CreateNoteRequest,
    NoteListItemResponse,
    NoteListResponse,
    NoteResponse,
    NoteVersionResponse,
    UpdateNoteRequest,
)
from src.documents.service import (
    DocumentCollectionAccess,
    collection_document_owner_id,
    ensure_collection_owner,
    ensure_document_owner,
)
from src.documents.types import DocumentType
from src.kit.exceptions import DocumentNotFoundException
from src.models.document import DocumentModel

if TYPE_CHECKING:
    from collections.abc import Sequence

    from src.documents.chunk_repository import ChunkRepository
    from src.documents.document_repository import DocumentRepository
    from src.documents.note_version_repository import NoteVersionRepository
    from src.documents.processing import DocumentProcessingService
    from src.postgres import AsyncSession

NOTE_VERSION_COALESCE_WINDOW = timedelta(seconds=60)


async def get_note(document_repo: DocumentRepository, *, user_id: uuid.UUID, note_id: uuid.UUID) -> DocumentModel:
    document = await document_repo.get_by_id(note_id)
    if document is None or document.type != DocumentType.MARKDOWN:
        raise DocumentNotFoundException("note not found")
    ensure_document_owner(document, user_id)
    return document


async def save_note_version(
    note_version_repo: NoteVersionRepository,
    previous_document: DocumentModel,
    current_document: DocumentModel,
    *,
    force: bool = False,
) -> None:
    if not note_content_changed(previous_document, current_document):
        return
    if not force:
        versions = await note_version_repo.list_by_note_id(
            note_id=previous_document.id,
            user_id=previous_document.user_id,
        )
        latest = versions[0] if versions else None
        if latest and latest.created_at and datetime.now(UTC) - latest.created_at < NOTE_VERSION_COALESCE_WINDOW:
            return
    version_number = await note_version_repo.count_by_note_id(previous_document.id) + 1
    await note_version_repo.create(
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
    document: DocumentModel,
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


def note_content_changed(previous_document: DocumentModel, current_document: DocumentModel) -> bool:
    return (
        previous_document.title != current_document.title
        or (previous_document.raw_content or "") != (current_document.raw_content or "")
    )


async def queue_note_processing(
    *,
    document: DocumentModel,
    processing_service: DocumentProcessingService,
) -> None:
    await processing_service.queue(document, message="Queued note for memory indexing.")


def note_response(document: DocumentModel) -> NoteResponse:
    return NoteResponse(
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


def note_version_response(version: NoteVersionRecord) -> NoteVersionResponse:
    if version.created_at is None:
        raise ValueError("note version created_at is required")
    return NoteVersionResponse(
        id=version.id,
        note_id=version.note_id,
        version_number=version.version_number,
        title=version.title,
        content=version.content,
        created_at=version.created_at,
    )


def note_list_item_response(document: DocumentModel) -> NoteListItemResponse:
    return NoteListItemResponse(
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




class NoteService:
    def __init__(
        self,
        session: AsyncSession,
        document_repo: DocumentRepository,
        collection_access: DocumentCollectionAccess,
        note_version_repo: NoteVersionRepository,
        processing_service: DocumentProcessingService,
        chunk_repo: ChunkRepository,
    ) -> None:
        self._session = session
        self._document_repo = document_repo
        self._collection_access = collection_access
        self._note_version_repo = note_version_repo
        self._processing_service = processing_service
        self._chunk_repo = chunk_repo

    async def create(self, *, user_id: UUID, body: CreateNoteRequest) -> NoteResponse:
        title = normalize_title(body.title, body.content)
        content = normalize_content(body.content)
        has_content = bool(content.strip())
        document_owner_id = await collection_document_owner_id(
            self._collection_access,
            body.collection_id,
            user_id,
        )
        await billing.ensure_can_create_document(self._session, user_id=document_owner_id)
        document = DocumentModel.create(
            id=uuid.uuid4(),
            user_id=document_owner_id,
            collection_id=body.collection_id,
            title=title,
            type=DocumentType.MARKDOWN,
            raw_content=content if has_content else None,
            word_count=len(content.split()),
            language=body.language,
        )
        if not has_content:
            document.mark_ready()

        await self._document_repo.create(document)
        await self._session.flush()

        if has_content:
            await queue_note_processing(
                document=document,
                processing_service=self._processing_service,
            )
        return note_response(document)

    async def delete(self, *, user_id: UUID, note_id: UUID) -> None:
        document = await get_note(self._document_repo, user_id=user_id, note_id=note_id)
        await self._document_repo.delete(document.id)
        await self._session.flush()

    async def get(self, *, user_id: UUID, note_id: UUID) -> NoteResponse:
        document = await get_note(self._document_repo, user_id=user_id, note_id=note_id)
        return note_response(document)

    async def list(
        self,
        *,
        user_id: UUID,
        limit: int = 100,
        offset: int = 0,
        collection_id: UUID | None = None,
    ) -> NoteListResponse:
        paged_notes = await self._document_repo.get_by_user_id(
            user_id,
            limit=limit,
            offset=offset,
            document_type=DocumentType.MARKDOWN,
            collection_id=collection_id,
        )
        total = await self._document_repo.count_by_user_id(
            user_id,
            document_type=DocumentType.MARKDOWN,
            collection_id=collection_id,
        )
        return NoteListResponse(
            items=[note_list_item_response(document) for document in paged_notes],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def list_versions(self, *, user_id: UUID, note_id: UUID) -> Sequence[NoteVersionResponse]:
        await get_note(self._document_repo, user_id=user_id, note_id=note_id)
        versions = await self._note_version_repo.list_by_note_id(note_id=note_id, user_id=user_id)
        return [note_version_response(version) for version in versions]

    async def restore_version(self, *, user_id: UUID, note_id: UUID, version_id: UUID) -> NoteResponse:
        document = await get_note(self._document_repo, user_id=user_id, note_id=note_id)
        version = await self._note_version_repo.get_by_id(
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
            return note_response(document)

        document.rename(version.title)
        document.update_content(
            raw_content=content if has_content else None,
            word_count=len(content.split()),
            language=document.language,
        )
        if not has_content:
            document.mark_ready()

        await save_note_version(self._note_version_repo, previous_document, document, force=True)
        await self._document_repo.update(document)
        if not has_content:
            await self._chunk_repo.delete_by_document_id(document.id)
        await self._session.flush()

        if has_content:
            await queue_note_processing(
                document=document,
                processing_service=self._processing_service,
            )
        return note_response(document)

    async def update(self, *, user_id: UUID, note_id: UUID, body: UpdateNoteRequest) -> NoteResponse:
        document = await get_note(self._document_repo, user_id=user_id, note_id=note_id)
        content = normalize_content(body.content)
        has_content = bool(content.strip())
        await ensure_collection_owner(self._collection_access, body.collection_id, user_id)
        previous_document = document.snapshot()
        next_title = normalize_title(body.title, content)
        if not note_update_changed(
            document,
            title=next_title,
            content=content,
            collection_id=body.collection_id,
            language=body.language,
        ):
            return note_response(document)

        document.rename(next_title)
        document.assign_collection(body.collection_id)
        document.update_content(
            raw_content=content if has_content else None,
            word_count=len(content.split()),
            language=body.language,
        )
        if not has_content:
            document.mark_ready()

        await save_note_version(self._note_version_repo, previous_document, document)
        await self._document_repo.update(document)
        if not has_content:
            await self._chunk_repo.delete_by_document_id(document.id)
        await self._session.flush()

        if has_content:
            await queue_note_processing(
                document=document,
                processing_service=self._processing_service,
            )
        return note_response(document)
