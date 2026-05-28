from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from src.application.dtos.telegram_dtos import TelegramChatBindingDTO, TelegramPairingCodeDTO, TelegramStatusDTO
from src.application.ports.persistence.api_key_repository import ApiKeyRecord
from src.application.ports.persistence.telegram_repository import TelegramPairingCodeRecord
from src.application.use_cases.api_keys import generate_api_key_token, hash_api_key
from src.domain.exceptions import ResourceNotFoundException, ValidationException

if TYPE_CHECKING:
    from src.application.dtos.external_intake_dtos import ExternalIngestDTO, ExternalIngestResultDTO
    from src.application.ports.persistence.telegram_repository import TelegramChatBindingRecord
    from src.application.ports.persistence.unit_of_work import IUnitOfWork
    from src.application.use_cases.external_intake import IngestExternalItemUseCase


TELEGRAM_PAIRING_TTL = timedelta(minutes=10)
TELEGRAM_API_KEY_SCOPES = ["ingest:write", "status:read"]


@dataclass(frozen=True, slots=True)
class ConsumeTelegramPairingCodeDTO:
    code: str
    chat_id: str
    chat_username: str | None = None
    chat_title: str | None = None


class CreateTelegramPairingCodeUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: UUID) -> TelegramPairingCodeDTO:
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
        async with self._uow:
            await self._uow.api_key_repo.create(api_key)
            created = await self._uow.telegram_repo.create_pairing_code(pairing)
            await self._uow.commit()
        return TelegramPairingCodeDTO(id=created.id, code=code, expires_at=created.expires_at)


class GetTelegramStatusUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: UUID) -> TelegramStatusDTO:
        async with self._uow:
            bindings = await self._uow.telegram_repo.list_bindings_by_user_id(user_id)
        return TelegramStatusDTO(bindings=[telegram_binding_dto(binding) for binding in bindings])


class RevokeTelegramBindingUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: UUID, binding_id: UUID) -> None:
        now = datetime.now(UTC)
        async with self._uow:
            binding = await self._uow.telegram_repo.revoke_binding(
                user_id=user_id,
                binding_id=binding_id,
                revoked_at=now,
            )
            if binding is None:
                raise ResourceNotFoundException("telegram binding not found")
            if binding.api_key_id is not None:
                await self._uow.api_key_repo.revoke(api_key_id=binding.api_key_id, user_id=user_id, revoked_at=now)
            await self._uow.commit()


class ConsumeTelegramPairingCodeUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, dto: ConsumeTelegramPairingCodeDTO) -> TelegramChatBindingDTO:
        now = datetime.now(UTC)
        async with self._uow:
            pairing = await self._uow.telegram_repo.get_pairing_code_by_hash(hash_pairing_code(dto.code))
            if pairing is None or pairing.consumed_at is not None or pairing.expires_at < now:
                raise ValidationException("invalid telegram pairing code")
            await self._uow.telegram_repo.consume_pairing_code(pairing.id, now)
            binding = await self._uow.telegram_repo.upsert_binding(
                user_id=pairing.user_id,
                api_key_id=pairing.api_key_id,
                chat_id=normalize_chat_id(dto.chat_id),
                chat_username=normalize_optional(dto.chat_username),
                chat_title=normalize_optional(dto.chat_title),
                paired_at=now,
            )
            await self._uow.commit()
        return telegram_binding_dto(binding)


class IngestTelegramItemUseCase:
    def __init__(self, uow: IUnitOfWork, ingest_external_item: IngestExternalItemUseCase) -> None:
        self._uow = uow
        self._ingest_external_item = ingest_external_item

    async def __call__(self, *, chat_id: str, dto: ExternalIngestDTO) -> ExternalIngestResultDTO:
        async with self._uow:
            binding = await self._uow.telegram_repo.get_active_binding_by_chat_id(normalize_chat_id(chat_id))
        if binding is None:
            raise ResourceNotFoundException("telegram chat is not paired")
        return await self._ingest_external_item(
            dataclass_replace_external_ingest_user(
                dto,
                user_id=binding.user_id,
                api_key_id=binding.api_key_id,
            )
        )


def telegram_binding_dto(record: TelegramChatBindingRecord) -> TelegramChatBindingDTO:
    return TelegramChatBindingDTO(
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


def dataclass_replace_external_ingest_user(
    dto: ExternalIngestDTO,
    *,
    user_id: UUID,
    api_key_id: UUID | None,
) -> ExternalIngestDTO:
    from dataclasses import replace

    return replace(dto, user_id=user_id, api_key_id=api_key_id)
