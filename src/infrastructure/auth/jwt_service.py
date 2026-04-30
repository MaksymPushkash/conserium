from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from jose import JWTError, jwt

from src.application.ports.auth.jwt_service import IJWTService
from src.core.config import settings
from src.domain.exceptions import InvalidTokenException


class JWTService(IJWTService):
    def generate_access_token(self, user_id: UUID) -> str:
        now = datetime.now(UTC)
        payload = {
            "sub": str(user_id),
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
        }
        return cast("str", jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM))

    def generate_refresh_token(self, user_id: UUID) -> str:
        now = datetime.now(UTC)
        payload = {
            "sub": str(user_id),
            "type": "refresh",
            "iat": now,
            "exp": now + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
        }
        return cast("str", jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM))

    def verify_access_token(self, token: str) -> UUID:
        return self._verify_token(token, expected_type="access")

    def verify_refresh_token(self, token: str) -> UUID:
        return self._verify_token(token, expected_type="refresh")

    def _verify_token(self, token: str, *, expected_type: str) -> UUID:
        try:
            payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        except JWTError as e:
            raise InvalidTokenException("invalid or expired token") from e

        if payload.get("type") != expected_type:
            article = "an" if expected_type == "access" else "a"
            raise InvalidTokenException(f"not {article} {expected_type} token")

        sub = payload.get("sub")
        if sub is None:
            raise InvalidTokenException("missing subject")

        try:
            return UUID(sub)
        except ValueError as e:
            raise InvalidTokenException("invalid subject") from e
