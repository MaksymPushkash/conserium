from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Response, status

from src.application.dtos.api_key_dtos import CreateApiKeyDTO
from src.application.use_cases.api_keys import CreateApiKeyUseCase, ListApiKeysUseCase, RevokeApiKeyUseCase
from src.presentation.dependencies.auth import CurrentUser
from src.presentation.mappers.api_key_mapper import to_api_key_list_response, to_created_api_key_response
from src.presentation.schemas.api_key import ApiKeyListResponse, CreateApiKeyRequest, CreatedApiKeyResponse

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


@router.get("", response_model=ApiKeyListResponse)
@inject
async def list_api_keys(
    current_user: CurrentUser,
    use_case: FromDishka[ListApiKeysUseCase],
) -> ApiKeyListResponse:
    return to_api_key_list_response(await use_case(user_id=current_user.id))


@router.post("", response_model=CreatedApiKeyResponse, status_code=status.HTTP_201_CREATED)
@inject
async def create_api_key(
    body: CreateApiKeyRequest,
    current_user: CurrentUser,
    use_case: FromDishka[CreateApiKeyUseCase],
) -> CreatedApiKeyResponse:
    result = await use_case(CreateApiKeyDTO(user_id=current_user.id, name=body.name, scopes=body.scopes))
    return to_created_api_key_response(result)


@router.delete("/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
@inject
async def revoke_api_key(
    api_key_id: UUID,
    current_user: CurrentUser,
    use_case: FromDishka[RevokeApiKeyUseCase],
) -> Response:
    await use_case(user_id=current_user.id, api_key_id=api_key_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
