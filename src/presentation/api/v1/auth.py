import secrets
import uuid
from urllib.parse import urlencode

from authlib.integrations.httpx_client import AsyncOAuth2Client
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse, RedirectResponse

from src.application.dtos.auth_dtos import (
    LoginDTO,
    RefreshDTO,
    RegisterDTO,
    TokenResponseDTO,
)
from src.application.ports.auth.jwt_service import IJWTService
from src.application.ports.cache.cache import ICache
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.auth.login_use_case import LoginUserUseCase
from src.application.use_cases.auth.refresh_token_use_case import RefreshTokenUseCase
from src.application.use_cases.auth.register_use_case import RegisterUserUseCase
from src.core.config import settings
from src.presentation.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


def _build_redirect_uri(request: Request, path: str) -> str:
    base = str(request.base_url).rstrip("/").replace("http://", "https://")
    return f"{base}{path}"


async def _issue_tokens_for_user(user_id: uuid.UUID, jwt_service: IJWTService, cache: ICache) -> TokenResponse:
    access = jwt_service.generate_access_token(user_id)
    refresh = jwt_service.generate_refresh_token(user_id)
    await cache.set(key=f"refresh:{refresh}", value=str(user_id), ttl=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600)
    return TokenResponse(access_token=access, refresh_token=refresh)


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
    result: TokenResponseDTO = await use_case(
        RegisterDTO(
            email=body.email,
            password=body.password,
            display_name=body.display_name,
        )
    )

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
    result: TokenResponseDTO = await use_case(
        LoginDTO(
            email=body.email,
            password=body.password,
        )
    )

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
    result: TokenResponseDTO = await use_case(RefreshDTO(refresh_token=body.refresh_token))

    return TokenResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
    )


@router.get("/google")
async def google_start(request: Request) -> RedirectResponse:
    state = secrets.token_urlsafe(32)
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "response_type": "code",
        "scope": "openid email profile",
        "redirect_uri": _build_redirect_uri(request, "/api/v1/auth/google/callback"),
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth"
    redirect = f"{url}?{urlencode(params)}"
    response = RedirectResponse(redirect, status_code=307)
    response.set_cookie(
        key="oauth_state",
        value=state,
        max_age=300,
        httponly=True,
        secure=_oauth_cookie_secure(request),
        samesite="lax",
    )
    return response


@router.get("/google/callback")
@inject
async def google_callback(
    request: Request,
    uow: FromDishka[IUnitOfWork],
    register_use_case: FromDishka[RegisterUserUseCase],
    jwt_service: FromDishka[IJWTService],
    cache: FromDishka[ICache],
) -> JSONResponse:
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    cookie_state = request.cookies.get("oauth_state")

    if not code:
        return JSONResponse({"error": "missing_code"}, status_code=400)
    if not state or not cookie_state or state != cookie_state:
        return JSONResponse({"error": "invalid_state"}, status_code=400)

    token_url = "https://oauth2.googleapis.com/token"
    redirect_uri = _build_redirect_uri(request, "/api/v1/auth/google/callback")
    async with AsyncOAuth2Client(client_id=settings.GOOGLE_CLIENT_ID, client_secret=settings.GOOGLE_CLIENT_SECRET) as client:
        await client.fetch_token(
            token_url,
            code=code,
            redirect_uri=redirect_uri,
        )
        userinfo = await client.get("https://www.googleapis.com/oauth2/v3/userinfo")
        info = userinfo.json()

    email = info.get("email")
    name = info.get("name") or info.get("email")
    if not email:
        return JSONResponse({"error": "no_email"}, status_code=400)

    async with uow:
        existing = await uow.user_repo.get_by_email(email)
        if existing is None:
            # create user with random password using register use case
            random_pw = uuid.uuid4().hex
            result = await register_use_case(RegisterDTO(email=email, password=random_pw, display_name=name))
            response = JSONResponse({"access_token": result.access_token, "refresh_token": result.refresh_token})
        else:
            tokens = await _issue_tokens_for_user(existing.id, jwt_service, cache)
            response = JSONResponse({"access_token": tokens.access_token, "refresh_token": tokens.refresh_token})
    
    response.delete_cookie("oauth_state")
    return response


@router.get("/github")
async def github_start(request: Request) -> RedirectResponse:
    state = secrets.token_urlsafe(32)
    params = {
        "client_id": settings.GITHUB_CLIENT_ID,
        "scope": "user:email",
        "state": state,
        "redirect_uri": _build_redirect_uri(request, "/api/v1/auth/github/callback"),
    }
    url = "https://github.com/login/oauth/authorize"
    redirect = f"{url}?{urlencode(params)}"
    response = RedirectResponse(redirect, status_code=307)
    response.set_cookie(
        key="oauth_state",
        value=state,
        max_age=300,
        httponly=True,
        secure=_oauth_cookie_secure(request),
        samesite="lax",
    )
    return response


@router.get("/github/callback")
@inject
async def github_callback(
    request: Request,
    uow: FromDishka[IUnitOfWork],
    register_use_case: FromDishka[RegisterUserUseCase],
    jwt_service: FromDishka[IJWTService],
    cache: FromDishka[ICache],
) -> JSONResponse:
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    cookie_state = request.cookies.get("oauth_state")

    if not code:
        return JSONResponse({"error": "missing_code"}, status_code=400)
    if not state or not cookie_state or state != cookie_state:
        return JSONResponse({"error": "invalid_state"}, status_code=400)

    token_url = "https://github.com/login/oauth/access_token"
    async with AsyncOAuth2Client(client_id=settings.GITHUB_CLIENT_ID, client_secret=settings.GITHUB_CLIENT_SECRET) as client:
        token_data = await client.fetch_token(token_url, code=code)
        access_token = token_data.get("access_token")
        if not access_token:
            return JSONResponse({"error": "no_access_token"}, status_code=400)

        user_resp = await client.get("https://api.github.com/user")
        user_info = user_resp.json()

        # GitHub may not return primary email in /user; fetch emails
        email = user_info.get("email")
        if not email:
            emails_resp = await client.get("https://api.github.com/user/emails")
            emails = emails_resp.json()
            primary = next((e for e in emails if e.get("primary") and e.get("verified")), None)
            email = primary.get("email") if primary else (emails[0].get("email") if emails else None)

    if not email:
        return JSONResponse({"error": "no_email"}, status_code=400)

    name = user_info.get("name") or email

    async with uow:
        existing = await uow.user_repo.get_by_email(email)
        if existing is None:
            random_pw = uuid.uuid4().hex
            result = await register_use_case(RegisterDTO(email=email, password=random_pw, display_name=name))
            response = JSONResponse({"access_token": result.access_token, "refresh_token": result.refresh_token})
        else:
            tokens = await _issue_tokens_for_user(existing.id, jwt_service, cache)
            response = JSONResponse({"access_token": tokens.access_token, "refresh_token": tokens.refresh_token})

    response.delete_cookie("oauth_state")
    return response


def _oauth_cookie_secure(request: Request) -> bool:
    return request.url.scheme == "https" or settings.FRONTEND_URL.startswith("https://")
