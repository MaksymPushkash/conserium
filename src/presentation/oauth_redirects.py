from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import RedirectResponse, Response

from src.application.dtos.auth_dtos import TokenResponseDTO
from src.core.config import settings

OAUTH_STATE_COOKIE = "oauth_state"
OAUTH_REFRESH_COOKIE = "oauth_refresh_token"
OAUTH_STATE_TTL_SECONDS = 300


def build_callback_uri(request: Request, path: str) -> str:
    scheme = _forwarded_header(request, "x-forwarded-proto") or request.url.scheme
    host = _forwarded_header(request, "x-forwarded-host") or request.headers.get("host") or request.url.netloc
    root_path = request.scope.get("root_path", "")
    return f"{scheme}://{host}{root_path}{path}"


def build_frontend_error_redirect(error: str) -> str:
    return f"{settings.FRONTEND_URL}/auth?{urlencode({'error': error})}"


def build_frontend_token_redirect(tokens: TokenResponseDTO) -> str:
    fragment_data = {
        "access_token": tokens.access_token,
        "token_type": "bearer",
    }
    if settings.OAUTH_INCLUDE_REFRESH_TOKEN_IN_FRAGMENT:
        fragment_data["refresh_token"] = tokens.refresh_token
    fragment = urlencode(fragment_data)
    return f"{settings.FRONTEND_URL}/auth/callback#{fragment}"


def set_oauth_state_cookie(response: RedirectResponse, request: Request, state: str) -> None:
    response.set_cookie(
        key=OAUTH_STATE_COOKIE,
        value=state,
        max_age=OAUTH_STATE_TTL_SECONDS,
        httponly=True,
        secure=oauth_cookie_secure(request),
        samesite="lax",
    )


def set_oauth_refresh_cookie(response: Response, request: Request, refresh_token: str) -> None:
    response.set_cookie(
        key=OAUTH_REFRESH_COOKIE,
        value=refresh_token,
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        httponly=True,
        secure=oauth_cookie_secure(request),
        samesite="lax",
    )


def oauth_cookie_secure(request: Request) -> bool:
    scheme = _forwarded_header(request, "x-forwarded-proto") or request.url.scheme
    return scheme == "https" or settings.FRONTEND_URL.startswith("https://")


def _forwarded_header(request: Request, name: str) -> str | None:
    value = request.headers.get(name)
    if value is None:
        return None
    first_value = value.split(",", maxsplit=1)[0].strip()
    return first_value or None
