from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.use_cases.documents.base import document_to_dto, ensure_collection_owner, ensure_document_owner
from src.application.use_cases.documents.queue_document_processing import queue_document_processing
from src.domain.exceptions import DocumentNotFoundException

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.dtos.document_dtos import (
        BulkAddDocumentTagsDTO,
        BulkDocumentOperationDTO,
        BulkMoveDocumentsDTO,
        DocumentDTO,
        MoveDocumentDTO,
        RenameDocumentDTO,
    )
    from src.application.ports.cache.document_status_cache import IDocumentStatusCache
    from src.application.ports.ingestion.task_dispatcher import ITaskDispatcher
    from src.application.ports.persistence.unit_of_work import IUnitOfWork
    from src.domain.entities.document_entity import DocumentEntity


class RenameDocumentUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, dto: RenameDocumentDTO) -> DocumentDTO:
        async with self._uow:
            document = await _get_owned_document(self._uow, dto.document_id, dto.user_id)
            document.rename(dto.title)
            await self._uow.document_repo.update(document)
            await self._uow.commit()
        return document_to_dto(document)


class MoveDocumentUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, dto: MoveDocumentDTO) -> DocumentDTO:
        async with self._uow:
            document = await _get_owned_document(self._uow, dto.document_id, dto.user_id)
            await ensure_collection_owner(self._uow, dto.collection_id, dto.user_id)
            document.assign_collection(dto.collection_id)
            await self._uow.document_repo.update(document)
            await self._uow.commit()
        return document_to_dto(document)


class BulkDeleteDocumentsUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, dto: BulkDocumentOperationDTO) -> None:
        async with self._uow:
            for document_id in set(dto.document_ids):
                document = await _get_owned_document(self._uow, document_id, dto.user_id)
                await self._uow.document_repo.delete(document.id)
            await self._uow.commit()


class BulkMoveDocumentsUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, dto: BulkMoveDocumentsDTO) -> None:
        async with self._uow:
            await ensure_collection_owner(self._uow, dto.collection_id, dto.user_id)
            for document_id in set(dto.document_ids):
                document = await _get_owned_document(self._uow, document_id, dto.user_id)
                document.assign_collection(dto.collection_id)
                await self._uow.document_repo.update(document)
            await self._uow.commit()


class BulkAddDocumentTagsUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, dto: BulkAddDocumentTagsDTO) -> None:
        tags = sorted({tag.strip().lower() for tag in dto.tags if tag.strip()})
        if not tags:
            return
        async with self._uow:
            for document_id in set(dto.document_ids):
                await _get_owned_document(self._uow, document_id, dto.user_id)
                await self._uow.document_repo.add_manual_tags(
                    document_id=document_id,
                    user_id=dto.user_id,
                    tag_names=tags,
                )
            await self._uow.commit()


class BulkReprocessDocumentsUseCase:
    def __init__(
        self,
        uow: IUnitOfWork,
        status_cache: IDocumentStatusCache,
        task_dispatcher: ITaskDispatcher,
    ) -> None:
        self._uow = uow
        self._status_cache = status_cache
        self._task_dispatcher = task_dispatcher

    async def __call__(self, dto: BulkDocumentOperationDTO) -> None:
        for document_id in set(dto.document_ids):
            async with self._uow:
                document = await _get_owned_document(self._uow, document_id, dto.user_id)
                document.mark_queued()
                await self._uow.document_repo.update(document)
                await self._uow.chunk_repo.delete_by_document_id(document.id)
                await self._uow.commit()
            await queue_document_processing(
                document=document,
                uow=self._uow,
                status_cache=self._status_cache,
                task_dispatcher=self._task_dispatcher,
                message="Queued for reprocessing.",
            )


async def _get_owned_document(uow: IUnitOfWork, document_id: UUID, user_id: UUID) -> DocumentEntity:
    document = await uow.document_repo.get_by_id(document_id)
    if document is None:
        raise DocumentNotFoundException("document not found")
    ensure_document_owner(document, user_id)
    return document
