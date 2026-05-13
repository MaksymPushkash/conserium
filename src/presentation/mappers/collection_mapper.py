from src.application.dtos.collection_dtos import CollectionDTO, CollectionListDTO
from src.presentation.schemas.collection import CollectionListResponse, CollectionResponse


def to_collection_response(dto: CollectionDTO) -> CollectionResponse:
    return CollectionResponse(
        id=dto.id,
        user_id=dto.user_id,
        name=dto.name,
        description=dto.description,
        color=dto.color,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
    )


def to_collection_list_response(dto: CollectionListDTO) -> CollectionListResponse:
    return CollectionListResponse(
        items=[to_collection_response(item) for item in dto.items],
        total=dto.total,
        limit=dto.limit,
        offset=dto.offset,
    )
