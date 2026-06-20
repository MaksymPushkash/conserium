from __future__ import annotations

from typing import TYPE_CHECKING

from src.documents.activity import activity_temperature
from src.documents.schemas import (
    BulkAddDocumentTagsDTO,
    BulkAddDocumentTagsRequest,
    BulkDocumentOperationDTO,
    BulkMoveDocumentsDTO,
    CreateDocumentDTO,
    CreateDocumentRequest,
    DeleteDocumentDTO,
    DocumentChunkResponse,
    DocumentConnectionResponse,
    DocumentConnectionsDTO,
    DocumentConnectionsResponse,
    DocumentDTO,
    DocumentListDTO,
    DocumentListItemResponse,
    DocumentListResponse,
    DocumentProcessingStepResponse,
    DocumentQuestionHistoryItemResponse,
    DocumentQuestionHistoryResponse,
    DocumentResponse,
    DocumentSearchDTO,
    DocumentSearchResponse,
    DocumentSearchResultResponse,
    DocumentStatusResponse,
    GetDocumentChunkDTO,
    GetDocumentDTO,
    ListDocumentsDTO,
    MoveDocumentDTO,
    MoveDocumentRequest,
    RenameDocumentDTO,
    RenameDocumentRequest,
    ReprocessDocumentDTO,
    RetryDocumentDTO,
    SearchDocumentsDTO,
)

if TYPE_CHECKING:
    from uuid import UUID

    from src.documents.repository import DocumentActivitySummary
    from src.documents.status import DocumentStatus
    from src.documents.status_cache import DocumentStatusDTO
    from src.documents.types import DocumentType
    from src.models.document import DocumentModel


def to_create_document_dto(body: CreateDocumentRequest, user_id: UUID) -> CreateDocumentDTO:
    return CreateDocumentDTO(
        user_id=user_id,
        title=body.title,
        type=body.type,
        collection_id=body.collection_id,
        source_url=body.source_url,
        file_path=body.file_path,
        file_size_bytes=body.file_size_bytes,
        raw_content=body.raw_content,
        summary=body.summary,
        word_count=body.word_count,
        language=body.language,
    )


def to_list_documents_dto(
    user_id: UUID,
    limit: int,
    offset: int,
    collection_id: UUID | None,
    status: DocumentStatus | None,
    document_type: DocumentType | None,
    tag_name: str | None,
) -> ListDocumentsDTO:
    return ListDocumentsDTO(
        user_id=user_id,
        limit=limit,
        offset=offset,
        collection_id=collection_id,
        status=status,
        document_type=document_type,
        tag_name=tag_name.strip().lower() if tag_name else None,
    )


def to_search_documents_dto(
    *,
    user_id: UUID,
    query: str,
    limit: int,
    collection_id: UUID | None,
    status: DocumentStatus | None,
    document_type: DocumentType | None,
    tag_name: str | None,
) -> SearchDocumentsDTO:
    return SearchDocumentsDTO(
        user_id=user_id,
        query=query,
        limit=limit,
        collection_id=collection_id,
        status=status,
        document_type=document_type,
        tag_name=tag_name,
    )


def to_get_document_dto(document_id: UUID, user_id: UUID) -> GetDocumentDTO:
    return GetDocumentDTO(user_id=user_id, document_id=document_id)


def to_get_document_chunk_dto(document_id: UUID, chunk_id: UUID, user_id: UUID) -> GetDocumentChunkDTO:
    return GetDocumentChunkDTO(user_id=user_id, document_id=document_id, chunk_id=chunk_id)


def to_delete_document_dto(document_id: UUID, user_id: UUID) -> DeleteDocumentDTO:
    return DeleteDocumentDTO(user_id=user_id, document_id=document_id)


def to_rename_document_dto(document_id: UUID, body: RenameDocumentRequest, user_id: UUID) -> RenameDocumentDTO:
    return RenameDocumentDTO(user_id=user_id, document_id=document_id, title=body.title)


def to_move_document_dto(document_id: UUID, body: MoveDocumentRequest, user_id: UUID) -> MoveDocumentDTO:
    return MoveDocumentDTO(user_id=user_id, document_id=document_id, collection_id=body.collection_id)


def to_bulk_document_operation_dto(document_ids: list[UUID], user_id: UUID) -> BulkDocumentOperationDTO:
    return BulkDocumentOperationDTO(user_id=user_id, document_ids=document_ids)


def to_bulk_move_documents_dto(document_ids: list[UUID], collection_id: UUID | None, user_id: UUID) -> BulkMoveDocumentsDTO:
    return BulkMoveDocumentsDTO(user_id=user_id, document_ids=document_ids, collection_id=collection_id)


def to_bulk_add_document_tags_dto(body: BulkAddDocumentTagsRequest, user_id: UUID) -> BulkAddDocumentTagsDTO:
    return BulkAddDocumentTagsDTO(user_id=user_id, document_ids=body.document_ids, tags=body.tags)


def to_retry_document_dto(document_id: UUID, user_id: UUID) -> RetryDocumentDTO:
    return RetryDocumentDTO(user_id=user_id, document_id=document_id)


def to_reprocess_document_dto(document_id: UUID, user_id: UUID) -> ReprocessDocumentDTO:
    return ReprocessDocumentDTO(user_id=user_id, document_id=document_id)


def to_document_response(dto: DocumentDTO) -> DocumentResponse:
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


def to_document_list_item_response(dto: DocumentDTO) -> DocumentListItemResponse:
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


def to_document_chunk_response(dto: DocumentChunkResponse) -> DocumentChunkResponse:
    return DocumentChunkResponse(
        id=dto.id,
        document_id=dto.document_id,
        content=dto.content,
        chunk_index=dto.chunk_index,
        start_char=dto.start_char,
        end_char=dto.end_char,
        page_number=dto.page_number,
        token_count=dto.token_count,
    )


def to_document_list_response(dto: DocumentListDTO) -> DocumentListResponse:
    return DocumentListResponse(
        items=[to_document_list_item_response(item) for item in dto.items],
        total=dto.total,
        limit=dto.limit,
        offset=dto.offset,
    )


def to_document_search_response(dto: DocumentSearchDTO) -> DocumentSearchResponse:
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


def to_document_question_history_response(dto: DocumentQuestionHistoryResponse) -> DocumentQuestionHistoryResponse:
    return DocumentQuestionHistoryResponse(
        document_id=dto.document_id,
        limit=dto.limit,
        items=[
            DocumentQuestionHistoryItemResponse(
                query_text=item.query_text,
                answer_text=item.answer_text,
                result_count=item.result_count,
                created_at=item.created_at,
            )
            for item in dto.items
        ],
    )


def to_document_connections_response(dto: DocumentConnectionsDTO) -> DocumentConnectionsResponse:
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


def to_document_status_response(dto: DocumentStatusDTO) -> DocumentStatusResponse:
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


def document_to_dto(document: DocumentModel, activity: DocumentActivitySummary | None = None) -> DocumentDTO:
    last_used_at = activity.last_used_at if activity and activity.last_used_at else document.created_at
    return DocumentDTO(
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
