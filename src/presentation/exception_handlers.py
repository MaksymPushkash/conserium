import structlog
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from src.domain.exceptions import (
    ApplicationStateException,
    ChatNotFoundException,
    DocumentAccessDeniedException,
    DocumentNotFoundException,
    DomainException,
    EmailAlreadyExistsException,
    InvalidCredentialsException,
    InvalidEmailException,
    InvalidPasswordException,
    InvalidTokenException,
    OAuthAuthenticationException,
    QueryProcessingException,
    ResourceNotFoundException,
    UserAlreadyInactiveException,
    UserInactiveException,
    ValidationException,
)

logger = structlog.get_logger(__name__)

DOMAIN_EXCEPTION_STATUS: dict[type[DomainException], int] = {
    DocumentAccessDeniedException: status.HTTP_403_FORBIDDEN,
    DocumentNotFoundException: status.HTTP_404_NOT_FOUND,
    ChatNotFoundException: status.HTTP_404_NOT_FOUND,
    ResourceNotFoundException: status.HTTP_404_NOT_FOUND,
    EmailAlreadyExistsException: status.HTTP_409_CONFLICT,
    InvalidCredentialsException: status.HTTP_401_UNAUTHORIZED,
    OAuthAuthenticationException: status.HTTP_401_UNAUTHORIZED,
    InvalidTokenException: status.HTTP_401_UNAUTHORIZED,
    UserInactiveException: status.HTTP_403_FORBIDDEN,
    UserAlreadyInactiveException: status.HTTP_409_CONFLICT,
    InvalidEmailException: status.HTTP_422_UNPROCESSABLE_CONTENT,
    InvalidPasswordException: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ValidationException: status.HTTP_422_UNPROCESSABLE_CONTENT,
    QueryProcessingException: status.HTTP_500_INTERNAL_SERVER_ERROR,
    ApplicationStateException: status.HTTP_500_INTERNAL_SERVER_ERROR,
}


def setup_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainException, _domain_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)


async def _domain_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    status_code = _status_code_for_exception(exc)
    detail = "Internal server error" if status_code == status.HTTP_500_INTERNAL_SERVER_ERROR else str(exc)
    return JSONResponse(status_code=status_code, content={"detail": detail})


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "Unhandled API exception",
        path=request.url.path,
        method=request.method,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


def _status_code_for_exception(exc: Exception) -> int:
    for exc_cls in type(exc).mro():
        status_code = DOMAIN_EXCEPTION_STATUS.get(exc_cls)
        if status_code is not None:
            return status_code
    return status.HTTP_400_BAD_REQUEST
