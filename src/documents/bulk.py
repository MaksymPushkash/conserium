from __future__ import annotations

from typing import TYPE_CHECKING

from src.documents.access import DocumentCollectionAccess, ensure_collection_owner, ensure_document_owner
from src.kit.exceptions import DocumentNotFoundException

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID

    from src.documents.chunk_repository import ChunkRepository
    from src.documents.document_repository import DocumentRepository
    from src.documents.processing import DocumentProcessingService
    from src.documents.schemas import BulkAddDocumentTagsRequest
    from src.models.document import DocumentModel
    from src.postgres import AsyncSession


class DocumentBulkService:
    def __init__(
        self,
        session: AsyncSession,
        document_repo: DocumentRepository,
        collection_access: DocumentCollectionAccess,
        chunk_repo: ChunkRepository,
        processing_service: DocumentProcessingService,
    ) -> None:
        self._session = session
        self._document_repo = document_repo
        self._collection_access = collection_access
        self._chunk_repo = chunk_repo
        self._processing_service = processing_service

    async def delete(self, *, user_id: UUID, document_ids: Sequence[UUID]) -> None:
        for document_id in set(document_ids):
            document = await _get_owned_document(self._document_repo, document_id, user_id)
            await self._document_repo.delete(document.id)
        await self._session.flush()

    async def move(self, *, user_id: UUID, document_ids: Sequence[UUID], collection_id: UUID | None) -> None:
        await ensure_collection_owner(self._collection_access, collection_id, user_id)
        for document_id in set(document_ids):
            document = await _get_owned_document(self._document_repo, document_id, user_id)
            document.assign_collection(collection_id)
            await self._document_repo.update(document)
        await self._session.flush()

    async def add_tags(self, *, user_id: UUID, body: BulkAddDocumentTagsRequest) -> None:
        tags = sorted({tag.strip().lower() for tag in body.tags if tag.strip()})
        if not tags:
            return
        for document_id in set(body.document_ids):
            await _get_owned_document(self._document_repo, document_id, user_id)
            await self._document_repo.add_manual_tags(
                document_id=document_id,
                user_id=user_id,
                tag_names=tags,
            )
        await self._session.flush()

    async def reprocess(self, *, user_id: UUID, document_ids: Sequence[UUID]) -> None:
        for document_id in set(document_ids):
            document = await _get_owned_document(self._document_repo, document_id, user_id)
            document.mark_queued()
            await self._document_repo.update(document)
            await self._chunk_repo.delete_by_document_id(document.id)
            await self._session.flush()
            await self._processing_service.queue(document, message="Queued for reprocessing.")


async def _get_owned_document(document_repo: DocumentRepository, document_id: UUID, user_id: UUID) -> DocumentModel:
    document = await document_repo.get_by_id(document_id)
    if document is None:
        raise DocumentNotFoundException("document not found")
    ensure_document_owner(document, user_id)
    return document


__all__ = ["DocumentBulkService"]
