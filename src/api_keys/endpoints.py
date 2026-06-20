from uuid import UUID

from fastapi import Depends, Response, status

from src.api_keys.schemas import ApiKeyListResponse, CreateApiKeyRequest, CreatedApiKeyResponse
from src.api_keys.service import api_keys
from src.auth.auth import CurrentUser
from src.postgres import AsyncReadSession, AsyncSession, get_db_read_session, get_db_session
from src.routing import APIRouter

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


@router.get("", response_model=ApiKeyListResponse)
async def list_api_keys(
    current_user: CurrentUser,
    session: AsyncReadSession = Depends(get_db_read_session),
) -> ApiKeyListResponse:
    return await api_keys.list_api_keys(session, user_id=current_user.id)


@router.post("", response_model=CreatedApiKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    body: CreateApiKeyRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> CreatedApiKeyResponse:
    return await api_keys.create(session, user_id=current_user.id, name=body.name, scopes=body.scopes)


@router.delete("/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    api_key_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    await api_keys.revoke(session, user_id=current_user.id, api_key_id=api_key_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

__all__ = ["router"]
