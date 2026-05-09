from uuid import UUID

from src.application.dtos.query_dtos import QueryDTO
from src.presentation.schemas.query import QueryRequest


def to_query_dto(body: QueryRequest, user_id: UUID) -> QueryDTO:
    return QueryDTO(
        user_id=user_id,
        query=body.query,
        conversation_id=body.conversation_id,
        collection_id=body.collection_id,
        document_types=tuple(body.document_types) if body.document_types else None,
        limit=body.limit,
    )
