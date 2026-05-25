from src.application.dtos.api_key_dtos import ApiKeyDTO, CreatedApiKeyDTO
from src.presentation.schemas.api_key import ApiKeyListResponse, ApiKeyResponse, CreatedApiKeyResponse


def to_api_key_response(dto: ApiKeyDTO) -> ApiKeyResponse:
    return ApiKeyResponse(
        id=dto.id,
        name=dto.name,
        prefix=dto.prefix,
        scopes=dto.scopes,
        last_used_at=dto.last_used_at,
        revoked_at=dto.revoked_at,
        created_at=dto.created_at,
    )


def to_created_api_key_response(dto: CreatedApiKeyDTO) -> CreatedApiKeyResponse:
    return CreatedApiKeyResponse(api_key=to_api_key_response(dto.api_key), token=dto.token)


def to_api_key_list_response(items: list[ApiKeyDTO]) -> ApiKeyListResponse:
    return ApiKeyListResponse(items=[to_api_key_response(item) for item in items])
