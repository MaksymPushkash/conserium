from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Self
from uuid import UUID

from src.billing.service import billing
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
from src.documents.bulk import DocumentBulkService
from src.documents.responses import (
    to_document_connections_response,
    to_document_list_response,
    to_document_response,
    to_document_search_response,
)
from src.documents.results import document_result
from src.documents.schemas import (
    BulkAddDocumentTagsRequest,
    CreateDocumentRequest,
    DocumentChunkResponse,
    DocumentConnection,
    DocumentConnectionsResult,
    DocumentListResult,
    DocumentQuestionHistoryItemResponse,
    DocumentQuestionHistoryResponse,
    DocumentResult,
    DocumentSearchResults,
    MoveDocumentRequest,
    RenameDocumentRequest,
)
from src.documents.search import DocumentSearchService
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
    from src.documents.status import DocumentStatus
    from src.documents.types import DocumentType
    from src.kit.ai.embedding_provider import EmbeddingProvider
    from src.kit.storage.file_storage import FileStorage
    from src.postgres import AsyncSession
    from src.query.repository import SearchQueryRepository


class DocumentService:
    def __init__(
        self,
        session: AsyncSession,
        document_repo: DocumentRepository,
        collection_access: DocumentCollectionAccess,
        activity_repo: DocumentActivityRepository,
        embedding_provider: EmbeddingProvider,
        chunk_repo: ChunkRepository,
        search_query_repo: SearchQueryRepository,
        file_storage: FileStorage,
        processing_service: DocumentProcessingService,
        search_service: DocumentSearchService | None = None,
        bulk_service: DocumentBulkService | None = None,
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
        self._search_service = search_service or DocumentSearchService(document_repo, chunk_repo, embedding_provider)
        self._bulk_service = bulk_service or DocumentBulkService(
            session,
            document_repo,
            collection_access,
            chunk_repo,
            processing_service,
        )

    @classmethod
    def from_session(
        cls,
        session: AsyncSession,
        *,
        embedding_provider: EmbeddingProvider,
        file_storage: FileStorage,
        processing_service: DocumentProcessingService,
    ) -> Self:
        from src.collections.repository import CollectionRepository
        from src.documents.activity_repository import DocumentActivityRepository
        from src.documents.chunk_repository import ChunkRepository
        from src.documents.document_repository import DocumentRepository
        from src.query.repository import SearchQueryRepository
        from src.workspaces.repository import SharedWorkspaceRepository

        return cls(
            session,
            DocumentRepository.from_session(session),
            DocumentCollectionAccess(
                session=session,
                collection_repo=CollectionRepository.from_session(session),
                shared_workspace_repo=SharedWorkspaceRepository.from_session(session),
            ),
            DocumentActivityRepository.from_session(session),
            embedding_provider,
            ChunkRepository.from_session(session),
            SearchQueryRepository.from_session(session),
            file_storage,
            processing_service,
        )

    async def create(self, *, user_id: UUID, body: CreateDocumentRequest) -> DocumentResult:
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
            title=body.title,
            type=body.type,
            source_url=body.source_url,
            file_path=body.file_path,
            file_size_bytes=body.file_size_bytes,
            raw_content=body.raw_content,
            summary=body.summary,
            word_count=body.word_count,
            language=body.language,
        )

        await self._document_repo.create(document)
        await self._activity_repo.record_event(
            user_id=document_owner_id,
            document_id=document.id,
            event_type="created",
        )
        if body.collection_id is not None:
            await record_shared_document_event(
                self._collection_access,
                collection_id=body.collection_id,
                actor_user_id=user_id,
                document_id=document.id,
                title=document.title,
            )
        await self._session.flush()

        return document_result(document)

    async def delete(self, *, user_id: UUID, document_id: UUID) -> None:
        document = await self._document_repo.get_by_id(document_id)
        if document is None:
            raise DocumentNotFoundException("document not found")

        ensure_document_owner(document, user_id)
        if document.file_path:
            await self._file_storage.delete_document_file(document.file_path)
        await self._document_repo.delete(document_id)
        await self._session.flush()

    async def list(
        self,
        *,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0,
        collection_id: UUID | None = None,
        status: DocumentStatus | None = None,
        document_type: DocumentType | None = None,
        tag_name: str | None = None,
    ) -> DocumentListResult:
        normalized_tag = tag_name.strip().lower() if tag_name else None
        documents = await self._document_repo.get_by_user_id(
            user_id,
            limit=limit,
            offset=offset,
            collection_id=collection_id,
            status=status,
            document_type=document_type,
            tag_name=normalized_tag,
        )
        activity = await self._activity_repo.summarize_by_document_ids(
            user_id=user_id,
            document_ids=[document.id for document in documents],
        )
        total = await self._document_repo.count_by_user_id(
            user_id,
            collection_id=collection_id,
            status=status,
            document_type=document_type,
            tag_name=normalized_tag,
        )

        return DocumentListResult(
            items=[document_result(document, activity.get(document.id)) for document in documents],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def search(
        self,
        *,
        user_id: UUID,
        query: str,
        limit: int = 20,
        collection_id: UUID | None = None,
        status: DocumentStatus | None = None,
        document_type: DocumentType | None = None,
        tag_name: str | None = None,
    ) -> DocumentSearchResults:
        return await self._search_service.search(
            user_id=user_id,
            query=query,
            limit=limit,
            collection_id=collection_id,
            status=status,
            document_type=document_type,
            tag_name=tag_name,
        )

    async def get(self, *, user_id: UUID, document_id: UUID) -> DocumentResult:
        document = await self._document_repo.get_by_id(document_id)
        if document is None:
            raise DocumentNotFoundException("document not found")
        if document.user_id != user_id:
            if document.collection_id is None:
                ensure_document_owner(document, user_id)
            else:
                await ensure_document_collection_visible(
                    self._collection_access,
                    collection_id=document.collection_id,
                    user_id=user_id,
                )
        await self._activity_repo.record_event(
            user_id=user_id,
            document_id=document.id,
            event_type="opened",
        )
        activity = await self._activity_repo.summarize_by_document_ids(
            user_id=user_id,
            document_ids=[document.id],
        )
        await self._session.flush()

        return document_result(document, activity.get(document.id))

    async def chunk(self, *, user_id: UUID, document_id: UUID, chunk_id: UUID) -> DocumentChunkResponse:
        document = await self._document_repo.get_by_id(document_id)
        chunk = await self._chunk_repo.get_by_id(chunk_id)

        if document is None:
            raise DocumentNotFoundException("document not found")
        ensure_document_owner(document, user_id)
        if chunk is None or chunk.document_id != document_id:
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

    async def connections(self, *, user_id: UUID, document_id: UUID, limit: int = 5) -> DocumentConnectionsResult:
        document = await self._document_repo.get_by_id(document_id)
        if document is None:
            raise DocumentNotFoundException("document not found")
        ensure_document_owner(document, user_id)
        records = await self._document_repo.get_related_documents(
            user_id=user_id,
            document_id=document_id,
            limit=limit,
        )
        activity = await self._activity_repo.summarize_by_document_ids(
            user_id=user_id,
            document_ids=[record.document.id for record in records],
        )

        return DocumentConnectionsResult(
            document_id=document_id,
            total=len(records),
            limit=limit,
            items=[
                DocumentConnection(
                    document=document_result(record.document, activity.get(record.document.id)),
                    reasons=record.reasons,
                    relationship_score=record.relationship_score,
                )
                for record in records
            ],
        )

    async def question_history(self, *, user_id: UUID, document_id: UUID, limit: int) -> DocumentQuestionHistoryResponse:
        document = await self._document_repo.get_by_id(document_id)
        if document is None:
            raise DocumentNotFoundException("document not found")
        ensure_document_owner(document, user_id)
        records = await self._search_query_repo.list_recent_by_document(
            user_id=user_id,
            document_id=document_id,
            limit=limit,
        )
        return DocumentQuestionHistoryResponse(
            document_id=document_id,
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

    async def rename(self, *, user_id: UUID, document_id: UUID, body: RenameDocumentRequest) -> DocumentResult:
        document = await _get_owned_document(self._document_repo, document_id, user_id)
        document.rename(body.title)
        await self._document_repo.update(document)
        await self._session.flush()
        return document_result(document)

    async def move(self, *, user_id: UUID, document_id: UUID, body: MoveDocumentRequest) -> DocumentResult:
        document = await _get_owned_document(self._document_repo, document_id, user_id)
        await ensure_collection_owner(self._collection_access, body.collection_id, user_id)
        document.assign_collection(body.collection_id)
        await self._document_repo.update(document)
        await self._session.flush()
        return document_result(document)

    async def bulk_delete(self, *, user_id: UUID, document_ids: Sequence[UUID]) -> None:
        await self._bulk_service.delete(user_id=user_id, document_ids=document_ids)

    async def bulk_move(self, *, user_id: UUID, document_ids: Sequence[UUID], collection_id: UUID | None) -> None:
        await self._bulk_service.move(user_id=user_id, document_ids=document_ids, collection_id=collection_id)

    async def bulk_add_tags(self, *, user_id: UUID, body: BulkAddDocumentTagsRequest) -> None:
        await self._bulk_service.add_tags(user_id=user_id, body=body)

    async def bulk_reprocess(self, *, user_id: UUID, document_ids: Sequence[UUID]) -> None:
        await self._bulk_service.reprocess(user_id=user_id, document_ids=document_ids)


async def _get_owned_document(document_repo: DocumentRepository, document_id: UUID, user_id: UUID) -> DocumentModel:
    document = await document_repo.get_by_id(document_id)
    if document is None:
        raise DocumentNotFoundException("document not found")
    ensure_document_owner(document, user_id)
    return document


__all__ = [
    "DocumentCollectionAccess",
    "DocumentService",
    "collection_document_owner_id",
    "ensure_collection_owner",
    "ensure_document_owner",
    "to_document_connections_response",
    "to_document_list_response",
    "to_document_response",
    "to_document_search_response",
]
