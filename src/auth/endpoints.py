import secrets

from fastapi import Depends, Request, Response, status
from fastapi.responses import RedirectResponse

from src.auth.auth import CurrentUser
from src.auth.oauth_clients import GithubOAuthClient, GoogleOAuthClient, OAuthProviderClient
from src.auth.oauth_redirects import (
    OAUTH_REFRESH_COOKIE,
    OAUTH_STATE_COOKIE,
    build_callback_uri,
    build_frontend_error_redirect,
    build_frontend_token_redirect,
    clear_oauth_refresh_cookie,
    set_oauth_refresh_cookie,
    set_oauth_state_cookie,
)
from src.auth.schemas import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse
from src.auth.service import (
    AuthSessionService,
    OAuthLoginCompleter,
    RefreshTokenRotator,
    UserAuthenticator,
    UserRegistrar,
    get_auth_session_service,
    get_github_oauth_client,
    get_google_oauth_client,
    get_oauth_login_completer,
    get_refresh_token_rotator,
    get_user_authenticator,
    get_user_registrar,
    to_complete_oauth_login_dto,
    to_login_dto,
    to_refresh_dto,
    to_register_dto,
    to_token_response,
)
from src.kit.exceptions import InvalidTokenException, OAuthAuthenticationException, UserInactiveException
from src.routing import APIRouter

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: Request,
    response: Response,
    body: RegisterRequest,
    handler: UserRegistrar = Depends(get_user_registrar),
) -> TokenResponse:
    result = await handler(to_register_dto(body))
    set_oauth_refresh_cookie(response, request, result.refresh_token)
    return to_token_response(result)


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    handler: UserAuthenticator = Depends(get_user_authenticator),
) -> TokenResponse:
    result = await handler(to_login_dto(body))
    set_oauth_refresh_cookie(response, request, result.refresh_token)
    return to_token_response(result)


@router.post("/refresh", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def refresh(
    request: Request,
    response: Response,
    handler: RefreshTokenRotator = Depends(get_refresh_token_rotator),
    body: RefreshRequest | None = None,
) -> TokenResponse:
    refresh_token = (body.refresh_token if body else None) or request.cookies.get(OAUTH_REFRESH_COOKIE)
    if refresh_token is None:
        raise InvalidTokenException("refresh token invalid")
    result = await handler(to_refresh_dto(refresh_token))
    set_oauth_refresh_cookie(response, request, result.refresh_token)
    return to_token_response(result)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    service: AuthSessionService = Depends(get_auth_session_service),
    body: RefreshRequest | None = None,
) -> Response:
    refresh_token = (body.refresh_token if body else None) or request.cookies.get(OAUTH_REFRESH_COOKIE)
    if refresh_token is not None:
        await service.logout(to_refresh_dto(refresh_token))
    clear_oauth_refresh_cookie(response, request)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/logout/all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_everywhere(
    request: Request,
    response: Response,
    current_user: CurrentUser,
    service: AuthSessionService = Depends(get_auth_session_service),
) -> Response:
    await service.logout_all(current_user.id)
    clear_oauth_refresh_cookie(response, request)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/google")
async def google_start(
    request: Request,
    provider: GoogleOAuthClient = Depends(get_google_oauth_client),
) -> RedirectResponse:
    return _start_oauth(request, provider, "/api/v1/auth/google/callback")


@router.get("/google/callback")
async def google_callback(
    request: Request,
    provider: GoogleOAuthClient = Depends(get_google_oauth_client),
    handler: OAuthLoginCompleter = Depends(get_oauth_login_completer),
) -> RedirectResponse:
    return await _complete_oauth(
        request=request,
        provider=provider,
        handler=handler,
        callback_path="/api/v1/auth/google/callback",
    )


@router.get("/github")
async def github_start(
    request: Request,
    provider: GithubOAuthClient = Depends(get_github_oauth_client),
) -> RedirectResponse:
    return _start_oauth(request, provider, "/api/v1/auth/github/callback")


@router.get("/github/callback")
async def github_callback(
    request: Request,
    provider: GithubOAuthClient = Depends(get_github_oauth_client),
    handler: OAuthLoginCompleter = Depends(get_oauth_login_completer),
) -> RedirectResponse:
    return await _complete_oauth(
        request=request,
        provider=provider,
        handler=handler,
        callback_path="/api/v1/auth/github/callback",
    )


def _start_oauth(request: Request, provider: OAuthProviderClient, callback_path: str) -> RedirectResponse:
    state = secrets.token_urlsafe(32)
    redirect_uri = build_callback_uri(request, callback_path)
    response = RedirectResponse(provider.authorization_url(redirect_uri=redirect_uri, state=state), status_code=307)
    set_oauth_state_cookie(response, request, state)
    return response


async def _complete_oauth(
    *,
    request: Request,
    provider: OAuthProviderClient,
    handler: OAuthLoginCompleter,
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
        tokens = await handler(
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


__all__ = ["router"]
