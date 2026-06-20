from __future__ import annotations

import uuid
from typing import TYPE_CHECKING
from uuid import UUID

from src.documents.access import (
    DocumentCollectionAccess as DocumentCollectionAccess,
)
from src.documents.access import (
    collection_document_owner_id as collection_document_owner_id,
)
from src.documents.access import (
    ensure_collection_owner as ensure_collection_owner,
)
from src.documents.access import (
    ensure_document_collection_visible,
    record_shared_document_event,
)
from src.documents.access import (
    ensure_document_owner as ensure_document_owner,
)
from src.documents.mapping import (
    document_to_dto,
    to_bulk_add_document_tags_dto,
    to_bulk_document_operation_dto,
    to_bulk_move_documents_dto,
    to_create_document_dto,
    to_delete_document_dto,
    to_document_chunk_response,
    to_document_connections_response,
    to_document_list_response,
    to_document_question_history_response,
    to_document_response,
    to_document_search_response,
    to_document_status_response,
    to_get_document_chunk_dto,
    to_get_document_dto,
    to_list_documents_dto,
    to_move_document_dto,
    to_rename_document_dto,
    to_reprocess_document_dto,
    to_retry_document_dto,
    to_search_documents_dto,
)
from src.documents.schemas import (
    BulkAddDocumentTagsDTO,
    BulkDocumentOperationDTO,
    BulkMoveDocumentsDTO,
    CreateDocumentDTO,
    DeleteDocumentDTO,
    DocumentChunkResponse,
    DocumentConnectionDTO,
    DocumentConnectionsDTO,
    DocumentDTO,
    DocumentListDTO,
    DocumentQuestionHistoryItemResponse,
    DocumentQuestionHistoryResponse,
    DocumentSearchDTO,
    DocumentSearchResultDTO,
    GetDocumentChunkDTO,
    GetDocumentDTO,
    ListDocumentsDTO,
    MoveDocumentDTO,
    RenameDocumentDTO,
    SearchDocumentsDTO,
)
from src.documents.status_cache import (
    DocumentProcessingStepDTO,
    DocumentStatusDTO,
    IDocumentStatusCache,
)
from src.kit.exceptions import (
    DocumentNotFoundException,
)
from src.models.document import DocumentModel

if TYPE_CHECKING:
    from collections.abc import Sequence

    from src.documents.activity_repository import (
        DocumentActivityRepository as DocumentActivityRepository,
    )
    from src.documents.chunk_repository import ChunkRepository as ChunkRepository
    from src.documents.document_repository import DocumentRepository
    from src.documents.processing import DocumentProcessingService
    from src.documents.repository import ChunkSearchResult
    from src.kit.ports.ai.embedding_provider import IEmbeddingProvider
    from src.kit.ports.ingestion.file_storage import IFileStorage
    from src.postgres import AsyncSession
    from src.query.repository import SearchQueryRepository


class DocumentService:
    def __init__(
        self,
        session: AsyncSession,
        document_repo: DocumentRepository,
        collection_access: DocumentCollectionAccess,
        activity_repo: DocumentActivityRepository,
        embedding_provider: IEmbeddingProvider,
        chunk_repo: ChunkRepository,
        search_query_repo: SearchQueryRepository,
        file_storage: IFileStorage,
        processing_service: DocumentProcessingService,
    ) -> None:
        self._session = session
        self._document_repo = document_repo
        self._collection_access = collection_access
        self._activity_repo = activity_repo
        self._embedding_provider = embedding_provider
        self._chunk_repo = chunk_repo
        self._search_query_repo = search_query_repo
        self._file_storage = file_storage
        self._processing_service = processing_service

    async def create(self, dto: CreateDocumentDTO) -> DocumentDTO:
        document_owner_id = await collection_document_owner_id(
            self._collection_access,
            dto.collection_id,
            dto.user_id,
        )

        document = DocumentModel.create(
            id=uuid.uuid4(),
            user_id=document_owner_id,
            collection_id=dto.collection_id,
            title=dto.title,
            type=dto.type,
            source_url=dto.source_url,
            file_path=dto.file_path,
            file_size_bytes=dto.file_size_bytes,
            raw_content=dto.raw_content,
            summary=dto.summary,
            word_count=dto.word_count,
            language=dto.language,
        )

        await self._document_repo.create(document)
        await self._activity_repo.record_event(
            user_id=document_owner_id,
            document_id=document.id,
            event_type="created",
        )
        if dto.collection_id is not None:
            await record_shared_document_event(
                self._collection_access,
                collection_id=dto.collection_id,
                actor_user_id=dto.user_id,
                document_id=document.id,
                title=document.title,
            )
        await self._session.flush()

        return document_to_dto(document)

    async def delete(self, dto: DeleteDocumentDTO) -> None:
        document = await self._document_repo.get_by_id(dto.document_id)
        if document is None:
            raise DocumentNotFoundException("document not found")

        ensure_document_owner(document, dto.user_id)
        if document.file_path:
            await self._file_storage.delete_document_file(document.file_path)
        await self._document_repo.delete(dto.document_id)
        await self._session.flush()

    async def list(self, dto: ListDocumentsDTO) -> DocumentListDTO:
        documents = await self._document_repo.get_by_user_id(
            dto.user_id,
            limit=dto.limit,
            offset=dto.offset,
            collection_id=dto.collection_id,
            status=dto.status,
            document_type=dto.document_type,
            tag_name=dto.tag_name,
        )
        activity = await self._activity_repo.summarize_by_document_ids(
            user_id=dto.user_id,
            document_ids=[document.id for document in documents],
        )
        total = await self._document_repo.count_by_user_id(
            dto.user_id,
            collection_id=dto.collection_id,
            status=dto.status,
            document_type=dto.document_type,
            tag_name=dto.tag_name,
        )

        return DocumentListDTO(
            items=[document_to_dto(document, activity.get(document.id)) for document in documents],
            total=total,
            limit=dto.limit,
            offset=dto.offset,
        )

    async def search(self, dto: SearchDocumentsDTO) -> DocumentSearchDTO:
        query = dto.query.strip()
        if not query:
            return DocumentSearchDTO(items=[], query=query, total=0, limit=dto.limit)

        embedding = await self._embedding_provider.embed_text(query)
        chunk_results = await self._chunk_repo.hybrid_search(
            query=query,
            embedding=embedding,
            user_id=dto.user_id,
            limit=max(dto.limit * 4, dto.limit),
            collection_id=dto.collection_id,
            tag_names=(dto.tag_name,) if dto.tag_name else None,
            document_types=(dto.document_type,) if dto.document_type else None,
        )
        results = await self._document_results(chunk_results, dto)

        return DocumentSearchDTO(items=[*results[: dto.limit]], query=query, total=len(results), limit=dto.limit)

    async def _document_results(
        self,
        chunk_results: Sequence[ChunkSearchResult],
        dto: SearchDocumentsDTO,
    ) -> Sequence[DocumentSearchResultDTO]:
        best_chunks = self._best_chunk_by_document(chunk_results)
        results = []
        for document_id, chunk_result in best_chunks.items():
            document = await self._document_repo.get_by_id(document_id)
            if document is None or document.user_id != dto.user_id:
                continue
            if dto.status is not None and document.status != dto.status:
                continue
            results.append(
                DocumentSearchResultDTO(
                    document=document_to_dto(document),
                    snippet=chunk_result.chunk.content,
                    score=chunk_result.score,
                    chunk_id=chunk_result.chunk.id,
                    page_number=chunk_result.chunk.page_number,
                )
            )
        return results

    @staticmethod
    def _best_chunk_by_document(chunk_results: Sequence[ChunkSearchResult]) -> dict[UUID, ChunkSearchResult]:
        best_chunks: dict[UUID, ChunkSearchResult] = {}
        for result in chunk_results:
            document_id = result.chunk.document_id
            if document_id not in best_chunks:
                best_chunks[document_id] = result
        return best_chunks

    async def get(self, dto: GetDocumentDTO) -> DocumentDTO:
        document = await self._document_repo.get_by_id(dto.document_id)
        if document is None:
            raise DocumentNotFoundException("document not found")
        if document.user_id != dto.user_id:
            if document.collection_id is None:
                ensure_document_owner(document, dto.user_id)
            else:
                await ensure_document_collection_visible(
                    self._collection_access,
                    collection_id=document.collection_id,
                    user_id=dto.user_id,
                )
        await self._activity_repo.record_event(
            user_id=dto.user_id,
            document_id=document.id,
            event_type="opened",
        )
        activity = await self._activity_repo.summarize_by_document_ids(
            user_id=dto.user_id,
            document_ids=[document.id],
        )
        await self._session.flush()

        return document_to_dto(document, activity.get(document.id))

    async def chunk(self, dto: GetDocumentChunkDTO) -> DocumentChunkResponse:
        document = await self._document_repo.get_by_id(dto.document_id)
        chunk = await self._chunk_repo.get_by_id(dto.chunk_id)

        if document is None:
            raise DocumentNotFoundException("document not found")
        ensure_document_owner(document, dto.user_id)
        if chunk is None or chunk.document_id != dto.document_id:
            raise DocumentNotFoundException("chunk not found")

        return DocumentChunkResponse(
            id=chunk.id,
            document_id=chunk.document_id,
            content=chunk.content,
            chunk_index=chunk.chunk_index,
            start_char=chunk.start_char,
            end_char=chunk.end_char,
            page_number=chunk.page_number,
            token_count=chunk.token_count,
        )

    async def connections(self, dto: GetDocumentDTO, *, limit: int = 5) -> DocumentConnectionsDTO:
        document = await self._document_repo.get_by_id(dto.document_id)
        if document is None:
            raise DocumentNotFoundException("document not found")
        ensure_document_owner(document, dto.user_id)
        records = await self._document_repo.get_related_documents(
            user_id=dto.user_id,
            document_id=dto.document_id,
            limit=limit,
        )
        activity = await self._activity_repo.summarize_by_document_ids(
            user_id=dto.user_id,
            document_ids=[record.document.id for record in records],
        )

        return DocumentConnectionsDTO(
            document_id=dto.document_id,
            total=len(records),
            limit=limit,
            items=[
                DocumentConnectionDTO(
                    document=document_to_dto(record.document, activity.get(record.document.id)),
                    reasons=record.reasons,
                    relationship_score=record.relationship_score,
                )
                for record in records
            ],
        )

    async def question_history(self, dto: GetDocumentDTO, *, limit: int) -> DocumentQuestionHistoryResponse:
        document = await self._document_repo.get_by_id(dto.document_id)
        if document is None:
            raise DocumentNotFoundException("document not found")
        ensure_document_owner(document, dto.user_id)
        records = await self._search_query_repo.list_recent_by_document(
            user_id=dto.user_id,
            document_id=dto.document_id,
            limit=limit,
        )
        return DocumentQuestionHistoryResponse(
            document_id=dto.document_id,
            limit=limit,
            items=[
                DocumentQuestionHistoryItemResponse(
                    query_text=record.query_text,
                    answer_text=record.answer_text,
                    result_count=record.result_count,
                    created_at=record.created_at,
                )
                for record in records
            ],
        )

    async def rename(self, dto: RenameDocumentDTO) -> DocumentDTO:
        document = await _get_owned_document(self._document_repo, dto.document_id, dto.user_id)
        document.rename(dto.title)
        await self._document_repo.update(document)
        await self._session.flush()
        return document_to_dto(document)

    async def move(self, dto: MoveDocumentDTO) -> DocumentDTO:
        document = await _get_owned_document(self._document_repo, dto.document_id, dto.user_id)
        await ensure_collection_owner(self._collection_access, dto.collection_id, dto.user_id)
        document.assign_collection(dto.collection_id)
        await self._document_repo.update(document)
        await self._session.flush()
        return document_to_dto(document)

    async def bulk_delete(self, dto: BulkDocumentOperationDTO) -> None:
        for document_id in set(dto.document_ids):
            document = await _get_owned_document(self._document_repo, document_id, dto.user_id)
            await self._document_repo.delete(document.id)
        await self._session.flush()

    async def bulk_move(self, dto: BulkMoveDocumentsDTO) -> None:
        await ensure_collection_owner(self._collection_access, dto.collection_id, dto.user_id)
        for document_id in set(dto.document_ids):
            document = await _get_owned_document(self._document_repo, document_id, dto.user_id)
            document.assign_collection(dto.collection_id)
            await self._document_repo.update(document)
        await self._session.flush()

    async def bulk_add_tags(self, dto: BulkAddDocumentTagsDTO) -> None:
        tags = sorted({tag.strip().lower() for tag in dto.tags if tag.strip()})
        if not tags:
            return
        for document_id in set(dto.document_ids):
            await _get_owned_document(self._document_repo, document_id, dto.user_id)
            await self._document_repo.add_manual_tags(
                document_id=document_id,
                user_id=dto.user_id,
                tag_names=tags,
            )
        await self._session.flush()

    async def bulk_reprocess(self, dto: BulkDocumentOperationDTO) -> None:
        for document_id in set(dto.document_ids):
            document = await _get_owned_document(self._document_repo, document_id, dto.user_id)
            document.mark_queued()
            await self._document_repo.update(document)
            await self._chunk_repo.delete_by_document_id(document.id)
            await self._session.flush()
            await self._processing_service.queue(document, message="Queued for reprocessing.")


class DocumentStatusService:
    def __init__(self, document_repo: DocumentRepository, status_cache: IDocumentStatusCache) -> None:
        self._document_repo = document_repo
        self._status_cache = status_cache

    async def get(self, document_id: UUID, user_id: UUID) -> DocumentStatusDTO:
        document = await self._document_repo.get_by_id(document_id)

        if document is None or document.user_id != user_id:
            raise DocumentNotFoundException("document not found")

        cached = await self._status_cache.get_status(document.id)
        if cached is not None:
            return cached

        status = document.status.value
        progress = 100 if status == "READY" else 0
        message = f"Document status is {status}."
        return DocumentStatusDTO(
            document_id=document.id,
            status=status,
            progress=progress,
            message=message,
            failure_reason=message if status == "FAILED" else None,
            timeline=_fallback_timeline(status, progress, message),
        )


def _fallback_timeline(status: str, progress: int, message: str) -> list[DocumentProcessingStepDTO]:
    steps = [
        ("uploaded", "Uploaded", 0),
        ("extracted", "Extracted", 40),
        ("embedded", "Embedded", 90),
        ("enriched", "Enriched", 95),
        ("ready", "Ready", 100),
    ]
    return [
        DocumentProcessingStepDTO(
            key=key,
            label=label,
            state=_fallback_step_state(status, progress, threshold),
            progress=threshold,
            message=message if status == "FAILED" and progress < threshold else None,
        )
        for key, label, threshold in steps
    ]


def _fallback_step_state(status: str, progress: int, threshold: int) -> str:
    if status == "FAILED" and progress < threshold:
        return "failed"
    if status == "READY" or progress >= threshold:
        return "complete"
    return "pending"


async def _get_owned_document(document_repo: DocumentRepository, document_id: UUID, user_id: UUID) -> DocumentModel:
    document = await document_repo.get_by_id(document_id)
    if document is None:
        raise DocumentNotFoundException("document not found")
    ensure_document_owner(document, user_id)
    return document






__all__ = [
    "DocumentCollectionAccess",
    "DocumentService",
    "DocumentStatusService",
    "collection_document_owner_id",
    "document_to_dto",
    "ensure_collection_owner",
    "ensure_document_owner",
    "to_bulk_add_document_tags_dto",
    "to_bulk_document_operation_dto",
    "to_bulk_move_documents_dto",
    "to_create_document_dto",
    "to_delete_document_dto",
    "to_document_chunk_response",
    "to_document_connections_response",
    "to_document_list_response",
    "to_document_question_history_response",
    "to_document_response",
    "to_document_search_response",
    "to_document_status_response",
    "to_get_document_chunk_dto",
    "to_get_document_dto",
    "to_list_documents_dto",
    "to_move_document_dto",
    "to_rename_document_dto",
    "to_reprocess_document_dto",
    "to_retry_document_dto",
    "to_search_documents_dto",
]
