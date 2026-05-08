from src.application.dtos.auth_dtos import TokenResponseDTO
from src.presentation.schemas.auth import TokenResponse


def to_token_response(dto: TokenResponseDTO) -> TokenResponse:
    return TokenResponse(access_token=dto.access_token, refresh_token=dto.refresh_token)
