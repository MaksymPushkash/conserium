from uuid import UUID

from src.collections.schemas import (
    CollectionRequest,
    CreateCollectionDTO,
    DeleteCollectionDTO,
    ListCollectionsDTO,
    UpdateCollectionDTO,
)


def to_create_collection_dto(body: CollectionRequest, user_id: UUID) -> CreateCollectionDTO:
    return CreateCollectionDTO(
        user_id=user_id,
        name=body.name,
        workspace_id=body.workspace_id,
        description=body.description,
        color=body.color,
    )


def to_list_collections_dto(
    user_id: UUID,
    limit: int,
    offset: int,
    workspace_id: UUID | None = None,
) -> ListCollectionsDTO:
    return ListCollectionsDTO(user_id=user_id, limit=limit, offset=offset, workspace_id=workspace_id)


def to_update_collection_dto(collection_id: UUID, body: CollectionRequest, user_id: UUID) -> UpdateCollectionDTO:
    return UpdateCollectionDTO(
        user_id=user_id,
        collection_id=collection_id,
        name=body.name,
        workspace_id=body.workspace_id,
        description=body.description,
        color=body.color,
    )


def to_delete_collection_dto(collection_id: UUID, user_id: UUID) -> DeleteCollectionDTO:
    return DeleteCollectionDTO(user_id=user_id, collection_id=collection_id)
