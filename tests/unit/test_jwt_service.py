import uuid
from datetime import UTC, datetime, timedelta

import pytest
from jose import jwt

from src.core.config import settings
from src.domain.exceptions import InvalidTokenException
from src.infrastructure.auth.jwt_service import JWTService


def test_verify_refresh_token_accepts_refresh_token() -> None:
    service = JWTService()
    user_id = uuid.uuid4()
    token = service.generate_refresh_token(user_id)

    assert service.verify_refresh_token(token) == user_id


def test_verify_refresh_token_rejects_access_token() -> None:
    service = JWTService()
    user_id = uuid.uuid4()
    token = service.generate_access_token(user_id)

    with pytest.raises(InvalidTokenException, match="not a refresh token"):
        service.verify_refresh_token(token)


def test_verify_access_token_rejects_refresh_token() -> None:
    service = JWTService()
    user_id = uuid.uuid4()
    token = service.generate_refresh_token(user_id)

    with pytest.raises(InvalidTokenException, match="not an access token"):
        service.verify_access_token(token)


def test_verify_refresh_token_rejects_malformed_token() -> None:
    service = JWTService()

    with pytest.raises(InvalidTokenException, match="invalid or expired token"):
        service.verify_refresh_token("not-a-jwt")


def test_verify_refresh_token_rejects_expired_token() -> None:
    service = JWTService()
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "type": "refresh",
            "iat": now - timedelta(days=2),
            "exp": now - timedelta(seconds=1),
        },
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )

    with pytest.raises(InvalidTokenException, match="invalid or expired token"):
        service.verify_refresh_token(token)
