from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from src.application.dtos.api_key_dtos import ApiKeyDTO, ApiKeyPrincipalDTO, CreateApiKeyDTO, CreatedApiKeyDTO
from src.application.ports.persistence.api_key_repository import ApiKeyRecord
from src.domain.exceptions import InvalidTokenException, ValidationException

if TYPE_CHECKING:
    from src.application.ports.persistence.unit_of_work import IUnitOfWork


DEFAULT_API_KEY_SCOPES = ["ingest:write"]
ALLOWED_API_KEY_SCOPES = {"ingest:write", "status:read", "collections:read", "query:write"}
API_KEY_PREFIX = "ctx_"


class CreateApiKeyUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, dto: CreateApiKeyDTO) -> CreatedApiKeyDTO:
        name = normalize_api_key_name(dto.name)
        scopes = normalize_api_key_scopes(dto.scopes)
        token = generate_api_key_token()
        now = datetime.now(UTC)
        record = ApiKeyRecord(
            id=uuid4(),
            user_id=dto.user_id,
            name=name,
            key_hash=hash_api_key(token),
            prefix=token[:12],
            scopes=scopes,
            last_used_at=None,
            revoked_at=None,
            created_at=now,
        )
        async with self._uow:
            created = await self._uow.api_key_repo.create(record)
            await self._uow.commit()
        return CreatedApiKeyDTO(api_key=api_key_dto(created), token=token)


class ListApiKeysUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: UUID) -> list[ApiKeyDTO]:
        async with self._uow:
            records = await self._uow.api_key_repo.list_by_user_id(user_id)
        return [api_key_dto(record) for record in records]


class RevokeApiKeyUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: UUID, api_key_id: UUID) -> None:
        async with self._uow:
            await self._uow.api_key_repo.revoke(
                api_key_id=api_key_id,
                user_id=user_id,
                revoked_at=datetime.now(UTC),
            )
            await self._uow.commit()


class AuthenticateApiKeyUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, token: str, *, required_scope: str) -> ApiKeyPrincipalDTO:
        if required_scope not in ALLOWED_API_KEY_SCOPES:
            raise ValidationException("unsupported api key scope")
        normalized = normalize_bearer_token(token)
        async with self._uow:
            record = await self._uow.api_key_repo.get_by_hash(hash_api_key(normalized))
            if record is None or record.revoked_at is not None or required_scope not in record.scopes:
                raise InvalidTokenException("invalid api key")
            await self._uow.api_key_repo.mark_used(record.id, datetime.now(UTC))
            await self._uow.commit()
        return ApiKeyPrincipalDTO(user_id=record.user_id, api_key_id=record.id, scopes=record.scopes)


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
    normalized = []
    for scope in values:
        value = scope.strip()
        if value not in ALLOWED_API_KEY_SCOPES:
            raise ValidationException(f"unsupported api key scope: {value}")
        if value not in normalized:
            normalized.append(value)
    return normalized or DEFAULT_API_KEY_SCOPES


def normalize_bearer_token(value: str) -> str:
    token = value.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token.startswith(API_KEY_PREFIX):
        raise InvalidTokenException("invalid api key")
    return token


def api_key_dto(record: ApiKeyRecord) -> ApiKeyDTO:
    return ApiKeyDTO(
        id=record.id,
        user_id=record.user_id,
        name=record.name,
        prefix=record.prefix,
        scopes=record.scopes,
        last_used_at=record.last_used_at,
        revoked_at=record.revoked_at,
        created_at=record.created_at,
    )
