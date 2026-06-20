from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from uuid import UUID, uuid4

import pytest

from src.api_keys.repository import ApiKeyRecord
from src.documents.schemas import (
    ExternalIngestDTO,
    ExternalIngestResultDTO,
    ExternalIntakeItemDTO,
)
from src.documents.types import DocumentType
from src.integrations.repository import TelegramChatBindingRecord, TelegramPairingCodeRecord
from src.integrations.service import (
    ConsumeTelegramPairingCodeDTO,
    TelegramIngestionService,
    TelegramPairingService,
)
from src.kit.exceptions import ResourceNotFoundException

if TYPE_CHECKING:
    from src.documents.ingestion import ExternalItemIngester


@pytest.mark.asyncio
async def test_telegram_pairing_code_consumes_and_creates_binding() -> None:
    user_id = uuid4()
    persistence = _TelegramPersistence()
    service = TelegramPairingService(persistence, persistence.api_key_repo, persistence.telegram_repo)

    created_code = await service.create_pairing_code(user_id=user_id)
    binding = await service.consume_pairing_code(
        ConsumeTelegramPairingCodeDTO(
            code=created_code.code,
            chat_id="123",
            chat_username="max",
            chat_title="Max",
        )
    )
    status = await service.get_status(user_id=user_id)

    assert binding.user_id == user_id
    assert binding.chat_id == "123"
    assert status.bindings == [binding]
    assert persistence.telegram_repo.pairing_codes[0].consumed_at is not None
    assert persistence.api_key_repo.records[0].scopes == ["ingest:write", "status:read"]


@pytest.mark.asyncio
async def test_telegram_ingest_uses_chat_binding_user() -> None:
    user_id = uuid4()
    api_key_id = uuid4()
    persistence = _TelegramPersistence()
    persistence.telegram_repo.bindings.append(_binding(user_id=user_id, api_key_id=api_key_id, chat_id="123"))
    ingest = _RecordingExternalIngest()

    await TelegramIngestionService(persistence.telegram_repo, cast("ExternalItemIngester", ingest)).ingest(
        chat_id="123",
        dto=ExternalIngestDTO(
            user_id=uuid4(),
            api_key_id=None,
            provider="telegram",
            title="Link",
            type=DocumentType.URL,
            source_url="https://example.com",
        ),
    )

    assert ingest.received is not None
    assert ingest.received.user_id == user_id
    assert ingest.received.api_key_id == api_key_id


@pytest.mark.asyncio
async def test_revoke_telegram_binding_revokes_api_key() -> None:
    user_id = uuid4()
    api_key_id = uuid4()
    binding = _binding(user_id=user_id, api_key_id=api_key_id, chat_id="123")
    persistence = _TelegramPersistence()
    persistence.telegram_repo.bindings.append(binding)
    persistence.api_key_repo.records.append(_api_key(user_id=user_id, api_key_id=api_key_id))

    await TelegramPairingService(persistence, persistence.api_key_repo, persistence.telegram_repo).revoke_binding(
        user_id=user_id, binding_id=binding.id
    )

    assert persistence.telegram_repo.bindings[0].revoked_at is not None
    assert persistence.api_key_repo.records[0].revoked_at is not None


@pytest.mark.asyncio
async def test_telegram_ingest_rejects_unpaired_chat() -> None:
    persistence = _TelegramPersistence()
    ingest = _RecordingExternalIngest()

    with pytest.raises(ResourceNotFoundException):
        await TelegramIngestionService(persistence.telegram_repo, cast("ExternalItemIngester", ingest)).ingest(
            chat_id="missing",
            dto=ExternalIngestDTO(
                user_id=uuid4(),
                api_key_id=None,
                provider="telegram",
                title="Text",
                type=DocumentType.TEXT,
                raw_content="hello",
            ),
        )


class _TelegramPersistence:
    def __init__(self) -> None:
        self.api_key_repo = _ApiKeyRepo()
        self.telegram_repo = _TelegramRepo()

    async def flush(self) -> None:
        return None


class _ApiKeyRepo:
    def __init__(self) -> None:
        self.records: list[ApiKeyRecord] = []

    async def create(self, record: ApiKeyRecord) -> ApiKeyRecord:
        self.records.append(record)
        return record

    async def revoke(self, *, api_key_id: UUID, user_id: UUID, revoked_at: datetime) -> None:
        self.records = [
            ApiKeyRecord(
                id=record.id,
                user_id=record.user_id,
                name=record.name,
                key_hash=record.key_hash,
                prefix=record.prefix,
                scopes=record.scopes,
                last_used_at=record.last_used_at,
                revoked_at=revoked_at if record.id == api_key_id and record.user_id == user_id else record.revoked_at,
                created_at=record.created_at,
            )
            for record in self.records
        ]


class _TelegramRepo:
    def __init__(self) -> None:
        self.pairing_codes: list[TelegramPairingCodeRecord] = []
        self.bindings: list[TelegramChatBindingRecord] = []

    async def create_pairing_code(self, record: TelegramPairingCodeRecord) -> TelegramPairingCodeRecord:
        self.pairing_codes.append(record)
        return record

    async def get_pairing_code_by_hash(self, code_hash: str) -> TelegramPairingCodeRecord | None:
        return next((record for record in self.pairing_codes if record.code_hash == code_hash), None)

    async def consume_pairing_code(self, pairing_code_id: UUID, consumed_at: datetime) -> TelegramPairingCodeRecord:
        record = next(record for record in self.pairing_codes if record.id == pairing_code_id)
        record.consumed_at = consumed_at
        return record

    async def list_bindings_by_user_id(self, user_id: UUID) -> list[TelegramChatBindingRecord]:
        return [record for record in self.bindings if record.user_id == user_id]

    async def get_active_binding_by_chat_id(self, chat_id: str) -> TelegramChatBindingRecord | None:
        return next((record for record in self.bindings if record.chat_id == chat_id and record.revoked_at is None), None)

    async def upsert_binding(
        self,
        *,
        user_id: UUID,
        api_key_id: UUID,
        chat_id: str,
        chat_username: str | None,
        chat_title: str | None,
        paired_at: datetime,
    ) -> TelegramChatBindingRecord:
        binding = _binding(
            user_id=user_id,
            api_key_id=api_key_id,
            chat_id=chat_id,
            chat_username=chat_username,
            chat_title=chat_title,
            paired_at=paired_at,
        )
        self.bindings = [record for record in self.bindings if record.chat_id != chat_id]
        self.bindings.append(binding)
        return binding

    async def revoke_binding(
        self,
        *,
        user_id: UUID,
        binding_id: UUID,
        revoked_at: datetime,
    ) -> TelegramChatBindingRecord | None:
        for record in self.bindings:
            if record.id == binding_id and record.user_id == user_id:
                record.revoked_at = revoked_at
                return record
        return None


class _RecordingExternalIngest:
    def __init__(self) -> None:
        self.received: ExternalIngestDTO | None = None

    async def __call__(self, dto: ExternalIngestDTO) -> ExternalIngestResultDTO:
        self.received = dto
        now = datetime.now(UTC)
        return ExternalIngestResultDTO(
            intake_item=ExternalIntakeItemDTO(
                id=uuid4(),
                user_id=dto.user_id,
                api_key_id=dto.api_key_id,
                provider=dto.provider,
                external_id=dto.external_id,
                idempotency_key=dto.idempotency_key,
                title=dto.title,
                type=dto.type,
                collection_id=dto.collection_id,
                tags=dto.tags or [],
                source_url=dto.source_url,
                status="QUEUED",
                error_reason=None,
                document_id=None,
                payload_metadata={},
                created_at=now,
                updated_at=None,
            ),
            document=None,
        )


def _api_key(*, user_id: UUID, api_key_id: UUID) -> ApiKeyRecord:
    return ApiKeyRecord(
        id=api_key_id,
        user_id=user_id,
        name="Telegram bot",
        key_hash="hash",
        prefix="ctx_prefix",
        scopes=["ingest:write"],
        last_used_at=None,
        revoked_at=None,
        created_at=datetime.now(UTC),
    )


def _binding(
    *,
    user_id: UUID,
    api_key_id: UUID,
    chat_id: str,
    chat_username: str | None = None,
    chat_title: str | None = None,
    paired_at: datetime | None = None,
) -> TelegramChatBindingRecord:
    now = datetime.now(UTC)
    return TelegramChatBindingRecord(
        id=uuid4(),
        user_id=user_id,
        api_key_id=api_key_id,
        chat_id=chat_id,
        chat_username=chat_username,
        chat_title=chat_title,
        paired_at=paired_at or now,
        revoked_at=None,
        created_at=now,
    )
