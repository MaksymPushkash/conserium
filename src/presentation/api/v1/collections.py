from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Query, Response, status

from src.application.use_cases.collection_shares import (
    CreateCollectionShareUseCase,
    GetCollectionShareUseCase,
    RevokeCollectionShareUseCase,
)
from src.application.use_cases.documents.collection_use_cases import (
    CreateCollectionUseCase,
    DeleteCollectionUseCase,
    ListCollectionsUseCase,
    UpdateCollectionUseCase,
)
from src.presentation.dependencies.auth import CurrentUser
from src.presentation.mappers.collection_mapper import to_collection_list_response, to_collection_response
from src.presentation.mappers.collection_request_mapper import (
    to_create_collection_dto,
    to_delete_collection_dto,
    to_list_collections_dto,
    to_update_collection_dto,
)
from src.presentation.mappers.collection_share_mapper import to_collection_share_response
from src.presentation.schemas.collection import CollectionListResponse, CollectionRequest, CollectionResponse
from src.presentation.schemas.collection_share import CollectionShareResponse

router = APIRouter(prefix="/collections", tags=["collections"])


@router.post("", response_model=CollectionResponse, status_code=status.HTTP_201_CREATED)
@inject
async def create_collection(
    body: CollectionRequest,
    current_user: CurrentUser,
    use_case: FromDishka[CreateCollectionUseCase],
) -> CollectionResponse:
    result = await use_case(to_create_collection_dto(body, current_user.id))
    return to_collection_response(result)


@router.get("", response_model=CollectionListResponse)
@inject
async def list_collections(
    current_user: CurrentUser,
    use_case: FromDishka[ListCollectionsUseCase],
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> CollectionListResponse:
    result = await use_case(to_list_collections_dto(current_user.id, limit, offset))
    return to_collection_list_response(result)


@router.patch("/{collection_id}", response_model=CollectionResponse)
@inject
async def update_collection(
    collection_id: UUID,
    body: CollectionRequest,
    current_user: CurrentUser,
    use_case: FromDishka[UpdateCollectionUseCase],
) -> CollectionResponse:
    result = await use_case(to_update_collection_dto(collection_id, body, current_user.id))
    return to_collection_response(result)


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
@inject
async def delete_collection(
    collection_id: UUID,
    current_user: CurrentUser,
    use_case: FromDishka[DeleteCollectionUseCase],
) -> Response:
    await use_case(to_delete_collection_dto(collection_id, current_user.id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{collection_id}/share", response_model=CollectionShareResponse | None)
@inject
async def get_collection_share(
    collection_id: UUID,
    current_user: CurrentUser,
    use_case: FromDishka[GetCollectionShareUseCase],
) -> CollectionShareResponse | None:
    result = await use_case(user_id=current_user.id, collection_id=collection_id)
    return to_collection_share_response(result) if result is not None else None


@router.post("/{collection_id}/share", response_model=CollectionShareResponse, status_code=status.HTTP_201_CREATED)
@inject
async def create_collection_share(
    collection_id: UUID,
    current_user: CurrentUser,
    use_case: FromDishka[CreateCollectionShareUseCase],
) -> CollectionShareResponse:
    result = await use_case(user_id=current_user.id, collection_id=collection_id)
    return to_collection_share_response(result)


@router.delete("/{collection_id}/share", status_code=status.HTTP_204_NO_CONTENT)
@inject
async def revoke_collection_share(
    collection_id: UUID,
    current_user: CurrentUser,
    use_case: FromDishka[RevokeCollectionShareUseCase],
) -> Response:
    await use_case(user_id=current_user.id, collection_id=collection_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
