from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, HTTPException, status

from src.application.dtos.auth_dtos import LoginDTO, RefreshDTO, RegisterDTO, TokenResponseDTO
from src.application.use_cases.auth.login_use_case import LoginUserUseCase
from src.application.use_cases.auth.refresh_token_use_case import RefreshTokenUseCase
from src.application.use_cases.auth.register_use_case import RegisterUserUseCase
from src.domain.exceptions import (
    EmailAlreadyExistsException,
    InvalidCredentialsException,
    InvalidTokenException,
    UserInactiveException,
)
from src.presentation.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])




@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
@inject
async def register(
    body: RegisterRequest,
    use_case: FromDishka[RegisterUserUseCase],
) -> TokenResponse:
    try:
        result: TokenResponseDTO = await use_case(
            RegisterDTO(
                email=body.email,
                password=body.password,
                display_name=body.display_name,
            )
        )
    except EmailAlreadyExistsException as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
 
    return TokenResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
    )
 
 
@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
)
@inject
async def login(
    body: LoginRequest,
    use_case: FromDishka[LoginUserUseCase],
) -> TokenResponse:
    try:
        result: TokenResponseDTO = await use_case(
            LoginDTO(
                email=body.email,
                password=body.password,
            )
        )
    except (InvalidCredentialsException, UserInactiveException) as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e
 
    return TokenResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
    )
 
 
@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
)
@inject
async def refresh(
    body: RefreshRequest,
    use_case: FromDishka[RefreshTokenUseCase],
) -> TokenResponse:
    try:
        result: TokenResponseDTO = await use_case(
            RefreshDTO(refresh_token=body.refresh_token)
        )
    except InvalidTokenException as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e
 
    return TokenResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
    )