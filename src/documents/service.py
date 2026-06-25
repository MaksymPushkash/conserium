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
from src.documents.activity import activity_temperature
from src.documents.schemas import (
    BulkAddDocumentTagsRequest,
    CreateDocumentRequest,
    DocumentChunkResponse,
    DocumentConnection,
    DocumentConnectionResponse,
    DocumentConnectionsResponse,
    DocumentConnectionsResult,
    DocumentListItemResponse,
    DocumentListResponse,
    DocumentListResult,
    DocumentProcessingStepResponse,
    DocumentQuestionHistoryItemResponse,
    DocumentQuestionHistoryResponse,
    DocumentResponse,
    DocumentResult,
    DocumentSearchResponse,
    DocumentSearchResult,
    DocumentSearchResultResponse,
    DocumentSearchResults,
    DocumentStatusResponse,
    MoveDocumentRequest,
    RenameDocumentRequest,
)
from src.documents.status_cache import (
    DocumentProcessingStep,
    DocumentStatusSnapshot,
    RedisDocumentStatusCache,
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
    from src.documents.repository import ChunkSearchResult, DocumentActivitySummary
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

    async def create(self, *, user_id: UUID, body: CreateDocumentRequest) -> DocumentResult:
        document_owner_id = await collection_document_owner_id(
            self._collection_access,
            body.collection_id,
            user_id,
        )

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
        query = query.strip()
        if not query:
            return DocumentSearchResults(items=[], query=query, total=0, limit=limit)
        normalized_tag = tag_name.strip().lower() if tag_name else None

        embedding = await self._embedding_provider.embed_text(query)
        chunk_results = await self._chunk_repo.hybrid_search(
            query=query,
            embedding=embedding,
            user_id=user_id,
            limit=max(limit * 4, limit),
            collection_id=collection_id,
            tag_names=(normalized_tag,) if normalized_tag else None,
            document_types=(document_type,) if document_type else None,
        )
        results = await self._document_results(chunk_results, user_id=user_id, status=status)

        return DocumentSearchResults(items=[*results[:limit]], query=query, total=len(results), limit=limit)

    async def _document_results(
        self,
        chunk_results: Sequence[ChunkSearchResult],
        *,
        user_id: UUID,
        status: DocumentStatus | None,
    ) -> Sequence[DocumentSearchResult]:
        best_chunks = self._best_chunk_by_document(chunk_results)
        results = []
        for document_id, chunk_result in best_chunks.items():
            document = await self._document_repo.get_by_id(document_id)
            if document is None or document.user_id != user_id:
                continue
            if status is not None and document.status != status:
                continue
            results.append(
                DocumentSearchResult(
                    document=document_result(document),
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
        for document_id in set(document_ids):
            document = await _get_owned_document(self._document_repo, document_id, user_id)
            await self._document_repo.delete(document.id)
        await self._session.flush()

    async def bulk_move(self, *, user_id: UUID, document_ids: Sequence[UUID], collection_id: UUID | None) -> None:
        await ensure_collection_owner(self._collection_access, collection_id, user_id)
        for document_id in set(document_ids):
            document = await _get_owned_document(self._document_repo, document_id, user_id)
            document.assign_collection(collection_id)
            await self._document_repo.update(document)
        await self._session.flush()

    async def bulk_add_tags(self, *, user_id: UUID, body: BulkAddDocumentTagsRequest) -> None:
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

    async def bulk_reprocess(self, *, user_id: UUID, document_ids: Sequence[UUID]) -> None:
        for document_id in set(document_ids):
            document = await _get_owned_document(self._document_repo, document_id, user_id)
            document.mark_queued()
            await self._document_repo.update(document)
            await self._chunk_repo.delete_by_document_id(document.id)
            await self._session.flush()
            await self._processing_service.queue(document, message="Queued for reprocessing.")


class DocumentStatusService:
    def __init__(self, document_repo: DocumentRepository, status_cache: RedisDocumentStatusCache) -> None:
        self._document_repo = document_repo
        self._status_cache = status_cache

    async def get(self, document_id: UUID, user_id: UUID) -> DocumentStatusSnapshot:
        document = await self._document_repo.get_by_id(document_id)

        if document is None or document.user_id != user_id:
            raise DocumentNotFoundException("document not found")

        cached = await self._status_cache.get_status(document.id)
        if cached is not None:
            return cached

        status = document.status.value
        progress = 100 if status == "READY" else 0
        message = f"Document status is {status}."
        return DocumentStatusSnapshot(
            document_id=document.id,
            status=status,
            progress=progress,
            message=message,
            failure_reason=message if status == "FAILED" else None,
            timeline=_fallback_timeline(status, progress, message),
        )


def _fallback_timeline(status: str, progress: int, message: str) -> list[DocumentProcessingStep]:
    steps = [
        ("uploaded", "Uploaded", 0),
        ("extracted", "Extracted", 40),
        ("embedded", "Embedded", 90),
        ("enriched", "Enriched", 95),
        ("ready", "Ready", 100),
    ]
    return [
        DocumentProcessingStep(
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


def to_document_response(dto: DocumentResult) -> DocumentResponse:
    return DocumentResponse(
        id=dto.id,
        user_id=dto.user_id,
        collection_id=dto.collection_id,
        title=dto.title,
        type=dto.type,
        status=dto.status,
        source_url=dto.source_url,
        file_path=dto.file_path,
        file_size_bytes=dto.file_size_bytes,
        raw_content=dto.raw_content,
        summary=dto.summary,
        word_count=dto.word_count,
        language=dto.language,
        entities=dto.entities,
        categories=dto.categories,
        visual_metadata=dto.visual_metadata,
        suggested_questions=_suggested_questions(dto.suggested_questions, dto.visual_metadata),
        tags=dto.tags or [],
        last_used_at=dto.last_used_at,
        query_count=dto.query_count,
        citation_count=dto.citation_count,
        activity_temperature=dto.activity_temperature,
        is_duplicate=dto.is_duplicate,
        duplicate_of_id=dto.duplicate_of_id,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
    )


def to_document_list_item_response(dto: DocumentResult) -> DocumentListItemResponse:
    return DocumentListItemResponse(
        id=dto.id,
        user_id=dto.user_id,
        collection_id=dto.collection_id,
        title=dto.title,
        type=dto.type,
        status=dto.status,
        source_url=dto.source_url,
        file_path=dto.file_path,
        file_size_bytes=dto.file_size_bytes,
        summary=dto.summary,
        word_count=dto.word_count,
        language=dto.language,
        suggested_questions=_suggested_questions(dto.suggested_questions, dto.visual_metadata),
        tags=dto.tags or [],
        last_used_at=dto.last_used_at,
        query_count=dto.query_count,
        citation_count=dto.citation_count,
        activity_temperature=dto.activity_temperature,
        is_duplicate=dto.is_duplicate,
        duplicate_of_id=dto.duplicate_of_id,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
    )


def to_document_list_response(dto: DocumentListResult) -> DocumentListResponse:
    return DocumentListResponse(
        items=[to_document_list_item_response(item) for item in dto.items],
        total=dto.total,
        limit=dto.limit,
        offset=dto.offset,
    )


def to_document_search_response(dto: DocumentSearchResults) -> DocumentSearchResponse:
    return DocumentSearchResponse(
        items=[
            DocumentSearchResultResponse(
                document=to_document_list_item_response(item.document),
                snippet=item.snippet,
                score=item.score,
                chunk_id=item.chunk_id,
                page_number=item.page_number,
            )
            for item in dto.items
        ],
        query=dto.query,
        total=dto.total,
        limit=dto.limit,
    )


def to_document_connections_response(dto: DocumentConnectionsResult) -> DocumentConnectionsResponse:
    return DocumentConnectionsResponse(
        document_id=dto.document_id,
        total=dto.total,
        limit=dto.limit,
        items=[
            DocumentConnectionResponse(
                document=to_document_list_item_response(item.document),
                reasons=item.reasons,
                relationship_score=item.relationship_score,
            )
            for item in dto.items
        ],
    )


def to_document_status_response(dto: DocumentStatusSnapshot) -> DocumentStatusResponse:
    return DocumentStatusResponse(
        document_id=dto.document_id,
        status=dto.status,
        progress=dto.progress,
        message=dto.message,
        failure_reason=dto.failure_reason,
        timeline=[
            DocumentProcessingStepResponse(
                key=step.key,
                label=step.label,
                state=step.state,
                progress=step.progress,
                message=step.message,
            )
            for step in dto.timeline or []
        ],
    )


def document_result(document: DocumentModel, activity: DocumentActivitySummary | None = None) -> DocumentResult:
    last_used_at = activity.last_used_at if activity and activity.last_used_at else document.created_at
    return DocumentResult(
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
        tags=document.tags,
        last_used_at=last_used_at,
        query_count=activity.query_count if activity else 0,
        citation_count=activity.citation_count if activity else 0,
        activity_temperature=activity_temperature(last_used_at),
        is_duplicate=document.is_duplicate,
        duplicate_of_id=document.duplicate_of_id,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def _suggested_questions(
    suggested_questions: list[str] | None,
    visual_metadata: dict[str, object] | None,
) -> list[str]:
    if suggested_questions:
        return list(suggested_questions)
    if not visual_metadata:
        return []
    value = visual_metadata.get("suggested_questions")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]






__all__ = [
    "DocumentCollectionAccess",
    "DocumentService",
    "DocumentStatusService",
    "collection_document_owner_id",
    "document_result",
    "ensure_collection_owner",
    "ensure_document_owner",
    "to_document_connections_response",
    "to_document_list_response",
    "to_document_response",
    "to_document_search_response",
    "to_document_status_response",
]
