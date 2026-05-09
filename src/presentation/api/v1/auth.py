import secrets

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Request, Response, status
from fastapi.responses import RedirectResponse

from src.application.ports.auth.oauth_provider import IOAuthProviderClient
from src.application.use_cases.auth.complete_oauth_login_use_case import CompleteOAuthLoginUseCase
from src.application.use_cases.auth.login_use_case import LoginUserUseCase
from src.application.use_cases.auth.refresh_token_use_case import RefreshTokenUseCase
from src.application.use_cases.auth.register_use_case import RegisterUserUseCase
from src.domain.exceptions import InvalidTokenException, OAuthAuthenticationException, UserInactiveException
from src.infrastructure.auth.oauth_clients import GithubOAuthClient, GoogleOAuthClient
from src.presentation.mappers.auth_mapper import to_token_response
from src.presentation.mappers.auth_request_mapper import (
    to_complete_oauth_login_dto,
    to_login_dto,
    to_refresh_dto,
    to_register_dto,
)
from src.presentation.oauth_redirects import (
    OAUTH_REFRESH_COOKIE,
    OAUTH_STATE_COOKIE,
    build_callback_uri,
    build_frontend_error_redirect,
    build_frontend_token_redirect,
    set_oauth_refresh_cookie,
    set_oauth_state_cookie,
)
from src.presentation.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@inject
async def register(
    body: RegisterRequest,
    use_case: FromDishka[RegisterUserUseCase],
) -> TokenResponse:
    result = await use_case(to_register_dto(body))
    return to_token_response(result)


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
@inject
async def login(
    body: LoginRequest,
    use_case: FromDishka[LoginUserUseCase],
) -> TokenResponse:
    result = await use_case(to_login_dto(body))
    return to_token_response(result)


@router.post("/refresh", response_model=TokenResponse, status_code=status.HTTP_200_OK)
@inject
async def refresh(
    request: Request,
    response: Response,
    use_case: FromDishka[RefreshTokenUseCase],
    body: RefreshRequest | None = None,
) -> TokenResponse:
    refresh_token = (body.refresh_token if body else None) or request.cookies.get(OAUTH_REFRESH_COOKIE)
    if refresh_token is None:
        raise InvalidTokenException("refresh token invalid")
    result = await use_case(to_refresh_dto(refresh_token))
    set_oauth_refresh_cookie(response, request, result.refresh_token)
    return to_token_response(result)


@router.get("/google")
@inject
async def google_start(
    request: Request,
    provider: FromDishka[GoogleOAuthClient],
) -> RedirectResponse:
    return _start_oauth(request, provider, "/api/v1/auth/google/callback")


@router.get("/google/callback")
@inject
async def google_callback(
    request: Request,
    provider: FromDishka[GoogleOAuthClient],
    use_case: FromDishka[CompleteOAuthLoginUseCase],
) -> RedirectResponse:
    return await _complete_oauth(
        request=request,
        provider=provider,
        use_case=use_case,
        callback_path="/api/v1/auth/google/callback",
    )


@router.get("/github")
@inject
async def github_start(
    request: Request,
    provider: FromDishka[GithubOAuthClient],
) -> RedirectResponse:
    return _start_oauth(request, provider, "/api/v1/auth/github/callback")


@router.get("/github/callback")
@inject
async def github_callback(
    request: Request,
    provider: FromDishka[GithubOAuthClient],
    use_case: FromDishka[CompleteOAuthLoginUseCase],
) -> RedirectResponse:
    return await _complete_oauth(
        request=request,
        provider=provider,
        use_case=use_case,
        callback_path="/api/v1/auth/github/callback",
    )


def _start_oauth(request: Request, provider: IOAuthProviderClient, callback_path: str) -> RedirectResponse:
    state = secrets.token_urlsafe(32)
    redirect_uri = build_callback_uri(request, callback_path)
    response = RedirectResponse(provider.authorization_url(redirect_uri=redirect_uri, state=state), status_code=307)
    set_oauth_state_cookie(response, request, state)
    return response


async def _complete_oauth(
    *,
    request: Request,
    provider: IOAuthProviderClient,
    use_case: CompleteOAuthLoginUseCase,
    callback_path: str,
) -> RedirectResponse:
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    cookie_state = request.cookies.get(OAUTH_STATE_COOKIE)

    if not code:
        return RedirectResponse(build_frontend_error_redirect("missing_code"), status_code=302)
    if not state or not cookie_state or state != cookie_state:
        return RedirectResponse(build_frontend_error_redirect("invalid_state"), status_code=302)

    try:
        tokens = await use_case(
            to_complete_oauth_login_dto(
                code=code,
                redirect_uri=build_callback_uri(request, callback_path),
            ),
            provider,
        )
    except OAuthAuthenticationException as exc:
        response = RedirectResponse(build_frontend_error_redirect(exc.code), status_code=302)
        response.delete_cookie(OAUTH_STATE_COOKIE)
        return response
    except UserInactiveException:
        response = RedirectResponse(build_frontend_error_redirect("user_inactive"), status_code=302)
        response.delete_cookie(OAUTH_STATE_COOKIE)
        return response

    response = RedirectResponse(url=build_frontend_token_redirect(tokens), status_code=302)
    set_oauth_refresh_cookie(response, request, tokens.refresh_token)
    response.delete_cookie(OAUTH_STATE_COOKIE)
    return response
