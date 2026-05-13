from uuid import UUID

from src.application.dtos.query_dtos import QueryDTO
from src.presentation.schemas.query import QueryRequest


def to_query_dto(body: QueryRequest, user_id: UUID) -> QueryDTO:
    tag_names = tuple(tag.strip().lower() for tag in body.tag_names or [] if tag.strip())
    return QueryDTO(
        user_id=user_id,
        query=body.query,
        conversation_id=body.conversation_id,
        collection_id=body.collection_id,
        tag_names=tag_names or None,
        document_types=tuple(body.document_types) if body.document_types else None,
        limit=body.limit,
    )
