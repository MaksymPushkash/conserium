from src.documents.schemas import (
    DocumentConnectionResponse,
    DocumentConnectionsResponse,
    DocumentConnectionsResult,
    DocumentListItemResponse,
    DocumentListResponse,
    DocumentListResult,
    DocumentResponse,
    DocumentResult,
    DocumentSearchResponse,
    DocumentSearchResultResponse,
    DocumentSearchResults,
)


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
    "to_document_connections_response",
    "to_document_list_item_response",
    "to_document_list_response",
    "to_document_response",
    "to_document_search_response",
]
