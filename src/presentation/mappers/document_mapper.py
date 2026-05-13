from src.application.dtos.document_dtos import DocumentChunkDTO, DocumentDTO, DocumentListDTO
from src.application.ports.cache.document_status_cache import DocumentStatusDTO
from src.presentation.schemas.document import (
    DocumentChunkResponse,
    DocumentListItemResponse,
    DocumentListResponse,
    DocumentProcessingStepResponse,
    DocumentResponse,
    DocumentStatusResponse,
)


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
        suggested_questions=_suggested_questions(dto.visual_metadata),
        tags=dto.tags or [],
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
        suggested_questions=_suggested_questions(dto.visual_metadata),
        tags=dto.tags or [],
        is_duplicate=dto.is_duplicate,
        duplicate_of_id=dto.duplicate_of_id,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
    )


def _suggested_questions(visual_metadata: dict[str, object] | None) -> list[str]:
    if not visual_metadata:
        return []
    value = visual_metadata.get("suggested_questions")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def to_document_chunk_response(dto: DocumentChunkDTO) -> DocumentChunkResponse:
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
