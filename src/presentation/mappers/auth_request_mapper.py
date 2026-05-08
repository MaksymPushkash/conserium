from src.application.dtos.auth_dtos import CompleteOAuthLoginDTO, LoginDTO, RefreshDTO, RegisterDTO
from src.presentation.schemas.auth import LoginRequest, RegisterRequest


def to_register_dto(body: RegisterRequest) -> RegisterDTO:
    return RegisterDTO(email=body.email, password=body.password, display_name=body.display_name)


def to_login_dto(body: LoginRequest) -> LoginDTO:
    return LoginDTO(email=body.email, password=body.password)


def to_refresh_dto(refresh_token: str) -> RefreshDTO:
    return RefreshDTO(refresh_token=refresh_token)


def to_complete_oauth_login_dto(code: str, redirect_uri: str) -> CompleteOAuthLoginDTO:
    return CompleteOAuthLoginDTO(code=code, redirect_uri=redirect_uri)
