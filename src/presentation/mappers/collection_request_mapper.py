from uuid import UUID

from src.application.dtos.collection_dtos import (
    CreateCollectionDTO,
    DeleteCollectionDTO,
    ListCollectionsDTO,
    UpdateCollectionDTO,
)
from src.presentation.schemas.collection import CollectionRequest


def to_create_collection_dto(body: CollectionRequest, user_id: UUID) -> CreateCollectionDTO:
    return CreateCollectionDTO(
        user_id=user_id,
        name=body.name,
        description=body.description,
        color=body.color,
    )


def to_list_collections_dto(user_id: UUID, limit: int, offset: int) -> ListCollectionsDTO:
    return ListCollectionsDTO(user_id=user_id, limit=limit, offset=offset)


def to_update_collection_dto(collection_id: UUID, body: CollectionRequest, user_id: UUID) -> UpdateCollectionDTO:
    return UpdateCollectionDTO(
        user_id=user_id,
        collection_id=collection_id,
        name=body.name,
        description=body.description,
        color=body.color,
    )


def to_delete_collection_dto(collection_id: UUID, user_id: UUID) -> DeleteCollectionDTO:
    return DeleteCollectionDTO(user_id=user_id, collection_id=collection_id)
