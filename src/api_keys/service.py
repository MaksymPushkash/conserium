from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from src.api_keys.repository import ApiKeyRecord, ApiKeyRepository
from src.api_keys.schemas import ApiKeyListResponse, ApiKeyResponse, CreatedApiKeyResponse
from src.billing.service import billing
from src.kit.exceptions import ValidationException

if TYPE_CHECKING:
    from uuid import UUID

    from src.postgres import AsyncReadSession, AsyncSession


DEFAULT_API_KEY_SCOPES = ["ingest:write"]
ALLOWED_API_KEY_SCOPES = {"ingest:write", "status:read", "collections:read", "query:write"}
API_KEY_PREFIX = "con_"


class ApiKeyService:
    async def list_api_keys(self, session: AsyncReadSession, *, user_id: UUID) -> ApiKeyListResponse:
        records = await ApiKeyRepository.from_session(session).list_by_user_id(user_id)
        return ApiKeyListResponse(items=[_api_key_response(record) for record in records])

    async def create(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        name: str,
        scopes: list[str],
    ) -> CreatedApiKeyResponse:
        await billing.ensure_can_create_api_key(session, user_id=user_id)
        token = generate_api_key_token()
        record = ApiKeyRecord(
            id=uuid4(),
            user_id=user_id,
            name=normalize_api_key_name(name),
            key_hash=hash_api_key(token),
            prefix=token[:12],
            scopes=normalize_api_key_scopes(scopes),
            last_used_at=None,
            revoked_at=None,
            created_at=datetime.now(UTC),
        )
        created = await ApiKeyRepository.from_session(session).create(record)
        return CreatedApiKeyResponse(api_key=_api_key_response(created), token=token)

    async def revoke(self, session: AsyncSession, *, user_id: UUID, api_key_id: UUID) -> None:
        await ApiKeyRepository.from_session(session).revoke(
            api_key_id=api_key_id,
            user_id=user_id,
            revoked_at=datetime.now(UTC),
        )


def generate_api_key_token() -> str:
    return f"{API_KEY_PREFIX}{secrets.token_urlsafe(32)}"


def hash_api_key(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalize_api_key_name(name: str) -> str:
    normalized = name.strip()
    if not normalized:
        raise ValidationException("api key name is required")
    if len(normalized) > 120:
        raise ValidationException("api key name is too long")
    return normalized


def normalize_api_key_scopes(scopes: list[str]) -> list[str]:
    values = scopes or DEFAULT_API_KEY_SCOPES
    normalized: list[str] = []
    for scope in values:
        value = scope.strip()
        if value not in ALLOWED_API_KEY_SCOPES:
            raise ValidationException(f"unsupported api key scope: {value}")
        if value not in normalized:
            normalized.append(value)
    return normalized or DEFAULT_API_KEY_SCOPES


def _api_key_response(record: ApiKeyRecord) -> ApiKeyResponse:
    return ApiKeyResponse(
        id=record.id,
        name=record.name,
        prefix=record.prefix,
        scopes=record.scopes,
        last_used_at=record.last_used_at,
        revoked_at=record.revoked_at,
        created_at=record.created_at,
    )


api_keys = ApiKeyService()

__all__ = [
    "ALLOWED_API_KEY_SCOPES",
    "API_KEY_PREFIX",
    "DEFAULT_API_KEY_SCOPES",
    "ApiKeyService",
    "api_keys",
    "generate_api_key_token",
    "hash_api_key",
    "normalize_api_key_name",
    "normalize_api_key_scopes",
]
