from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.api_keys.service import ALLOWED_API_KEY_SCOPES, API_KEY_PREFIX, hash_api_key
from src.integrations.schemas import ApiKeyPrincipal
from src.kit.exceptions import InvalidTokenException, ValidationException

if TYPE_CHECKING:
    from src.api_keys.repository import ApiKeyRepository
    from src.postgres import AsyncSession


LEGACY_API_KEY_PREFIXES = ("ctx_",)


class ApiKeyAuthenticator:
    def __init__(self, session: AsyncSession, repository: ApiKeyRepository) -> None:
        self._session = session
        self._repository = repository

    async def __call__(self, token: str, *, required_scope: str) -> ApiKeyPrincipal:
        if required_scope not in ALLOWED_API_KEY_SCOPES:
            raise ValidationException("unsupported api key scope")
        normalized = normalize_bearer_token(token)
        record = await self._repository.get_by_hash(hash_api_key(normalized))
        if record is None or record.revoked_at is not None or required_scope not in record.scopes:
            raise InvalidTokenException("invalid api key")
        await self._repository.mark_used(record.id, datetime.now(UTC))
        await self._session.flush()
        return ApiKeyPrincipal(user_id=record.user_id, api_key_id=record.id, scopes=record.scopes)


def normalize_bearer_token(value: str) -> str:
    token = value.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    valid_prefixes = (API_KEY_PREFIX, *LEGACY_API_KEY_PREFIXES)
    if not token.startswith(valid_prefixes):
        raise InvalidTokenException("invalid api key")
    return token


__all__ = ["ApiKeyAuthenticator", "normalize_bearer_token"]
