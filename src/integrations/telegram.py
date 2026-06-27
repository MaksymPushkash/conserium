from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from src.api_keys.repository import ApiKeyRecord
from src.api_keys.service import generate_api_key_token, hash_api_key
from src.integrations.repository import TelegramChatBindingRecord, TelegramPairingCodeRecord
from src.integrations.schemas import (
    TelegramChatBindingResponse,
    TelegramChatBindingResult,
    TelegramPairingCodeResponse,
    TelegramStatus,
    TelegramStatusResponse,
)
from src.kit.exceptions import ResourceNotFoundException, ValidationException

if TYPE_CHECKING:
    from src.api_keys.repository import ApiKeyRepository
    from src.documents.ingestion import ExternalItemIngester
    from src.documents.schemas import ExternalIngestResult
    from src.documents.types import DocumentType
    from src.integrations.repository import TelegramRepository
    from src.postgres import AsyncSession


TELEGRAM_PAIRING_TTL = timedelta(minutes=10)
TELEGRAM_API_KEY_SCOPES = ["ingest:write", "status:read"]


class TelegramPairingService:
    def __init__(
        self,
        session: AsyncSession,
        api_key_repository: ApiKeyRepository,
        telegram_repository: TelegramRepository,
    ) -> None:
        self._session = session
        self._api_key_repository = api_key_repository
        self._telegram_repository = telegram_repository

    async def create_pairing_code(self, *, user_id: UUID) -> TelegramPairingCodeResponse:
        code = generate_pairing_code()
        token = generate_api_key_token()
        now = datetime.now(UTC)
        api_key = ApiKeyRecord(
            id=uuid4(),
            user_id=user_id,
            name="Telegram bot",
            key_hash=hash_api_key(token),
            prefix=token[:12],
            scopes=TELEGRAM_API_KEY_SCOPES,
            last_used_at=None,
            revoked_at=None,
            created_at=now,
        )
        pairing = TelegramPairingCodeRecord(
            id=uuid4(),
            user_id=user_id,
            api_key_id=api_key.id,
            code_hash=hash_pairing_code(code),
            expires_at=now + TELEGRAM_PAIRING_TTL,
            consumed_at=None,
            created_at=now,
        )
        await self._api_key_repository.create(api_key)
        created = await self._telegram_repository.create_pairing_code(pairing)
        await self._session.flush()
        return TelegramPairingCodeResponse(id=created.id, code=code, expires_at=created.expires_at)

    async def get_status(self, *, user_id: UUID) -> TelegramStatus:
        bindings = await self._telegram_repository.list_bindings_by_user_id(user_id)
        return TelegramStatus(bindings=[telegram_binding_result(binding) for binding in bindings])

    async def revoke_binding(self, *, user_id: UUID, binding_id: UUID) -> None:
        now = datetime.now(UTC)
        binding = await self._telegram_repository.revoke_binding(
            user_id=user_id,
            binding_id=binding_id,
            revoked_at=now,
        )
        if binding is None:
            raise ResourceNotFoundException("telegram binding not found")
        if binding.api_key_id is not None:
            await self._api_key_repository.revoke(api_key_id=binding.api_key_id, user_id=user_id, revoked_at=now)
        await self._session.flush()

    async def consume_pairing_code(
        self,
        *,
        code: str,
        chat_id: str,
        chat_username: str | None,
        chat_title: str | None,
    ) -> TelegramChatBindingResult:
        now = datetime.now(UTC)
        pairing = await self._telegram_repository.get_pairing_code_by_hash(hash_pairing_code(code))
        if pairing is None or pairing.consumed_at is not None or pairing.expires_at < now:
            raise ValidationException("invalid telegram pairing code")
        await self._telegram_repository.consume_pairing_code(pairing.id, now)
        binding = await self._telegram_repository.upsert_binding(
            user_id=pairing.user_id,
            api_key_id=pairing.api_key_id,
            chat_id=normalize_chat_id(chat_id),
            chat_username=normalize_optional(chat_username),
            chat_title=normalize_optional(chat_title),
            paired_at=now,
        )
        await self._session.flush()
        return telegram_binding_result(binding)


class TelegramIngestionService:
    def __init__(self, repository: TelegramRepository, ingest_external_item: ExternalItemIngester) -> None:
        self._repository = repository
        self._ingest_external_item = ingest_external_item

    async def ingest(
        self,
        *,
        chat_id: str,
        provider: str,
        title: str,
        type: DocumentType,
        collection_id: UUID | None,
        tags: list[str],
        source_url: str | None,
        raw_content: str | None,
        language: str | None,
        external_id: str | None,
        idempotency_key: str | None,
        payload_metadata: dict[str, object],
    ) -> ExternalIngestResult:
        binding = await self._repository.get_active_binding_by_chat_id(normalize_chat_id(chat_id))
        if binding is None:
            raise ResourceNotFoundException("telegram chat is not paired")
        return await self._ingest_external_item(
            user_id=binding.user_id,
            api_key_id=binding.api_key_id,
            provider=provider,
            title=title,
            type=type,
            collection_id=collection_id,
            tags=tags,
            source_url=source_url,
            raw_content=raw_content,
            language=language,
            external_id=external_id,
            idempotency_key=idempotency_key,
            payload_metadata=payload_metadata,
        )


def telegram_binding_result(record: TelegramChatBindingRecord) -> TelegramChatBindingResult:
    return TelegramChatBindingResult(
        id=record.id,
        user_id=record.user_id,
        api_key_id=record.api_key_id,
        chat_id=record.chat_id,
        chat_username=record.chat_username,
        chat_title=record.chat_title,
        paired_at=record.paired_at,
        revoked_at=record.revoked_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def generate_pairing_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(8))


def hash_pairing_code(code: str) -> str:
    return hashlib.sha256(normalize_pairing_code(code).encode("utf-8")).hexdigest()


def normalize_pairing_code(code: str) -> str:
    normalized = code.strip().upper().replace(" ", "")
    if not normalized:
        raise ValidationException("telegram pairing code is required")
    return normalized


def normalize_chat_id(chat_id: str) -> str:
    normalized = str(chat_id).strip()
    if not normalized:
        raise ValidationException("telegram chat id is required")
    return normalized[:64]


def normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def to_telegram_binding_response(dto: TelegramChatBindingResult) -> TelegramChatBindingResponse:
    return TelegramChatBindingResponse(
        id=dto.id,
        chat_id=dto.chat_id,
        chat_username=dto.chat_username,
        chat_title=dto.chat_title,
        paired_at=dto.paired_at,
        revoked_at=dto.revoked_at,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
    )


def to_telegram_status_response(dto: TelegramStatus) -> TelegramStatusResponse:
    return TelegramStatusResponse(bindings=[to_telegram_binding_response(binding) for binding in dto.bindings])


__all__ = [
    "TELEGRAM_API_KEY_SCOPES",
    "TELEGRAM_PAIRING_TTL",
    "TelegramIngestionService",
    "TelegramPairingService",
    "generate_pairing_code",
    "hash_pairing_code",
    "normalize_chat_id",
    "normalize_optional",
    "normalize_pairing_code",
    "telegram_binding_result",
    "to_telegram_binding_response",
    "to_telegram_status_response",
]
