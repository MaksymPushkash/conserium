from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from src.api_keys.repository import ApiKeyRecord, ApiKeyRepository
from src.api_keys.service import ApiKeyService
from src.integrations.service import ApiKeyAuthenticator
from src.kit.exceptions import InvalidTokenException


@pytest.mark.asyncio
async def test_api_key_lifecycle_authenticates_and_revokes_token(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid4()
    persistence = _ApiKeyPersistence()
    monkeypatch.setattr(ApiKeyRepository, "from_session", classmethod(lambda cls, session: persistence.api_key_repo))

    async def allow_api_keys(session: object, *, user_id: UUID) -> None:
        return None

    monkeypatch.setattr("src.api_keys.service.billing.ensure_can_create_api_key", allow_api_keys)
    service = ApiKeyService()

    created = await service.create(
        persistence,
        user_id=user_id,
        name="Telegram bot",
        scopes=["ingest:write"],
    )
    automation_key = await service.create(
        persistence,
        user_id=user_id,
        name="Automation",
        scopes=["status:read", "collections:read", "query:write"],
    )
    listed = await service.list_api_keys(persistence, user_id=user_id)
    principal = await ApiKeyAuthenticator(persistence, persistence.api_key_repo)(created.token, required_scope="ingest:write")
    automation_principal = await ApiKeyAuthenticator(persistence, persistence.api_key_repo)(
        automation_key.token, required_scope="query:write"
    )

    assert created.token.startswith("con_")
    assert created.api_key.prefix == created.token[:12]
    assert listed.items[0].name == "Telegram bot"
    assert automation_principal.scopes == ["status:read", "collections:read", "query:write"]
    assert principal.user_id == user_id
    assert persistence.api_key_repo.records[0].last_used_at is not None

    await service.revoke(persistence, user_id=user_id, api_key_id=created.api_key.id)

    with pytest.raises(InvalidTokenException):
        await ApiKeyAuthenticator(persistence, persistence.api_key_repo)(created.token, required_scope="ingest:write")


class _ApiKeyPersistence:
    def __init__(self) -> None:
        self.api_key_repo = _ApiKeyRepo()

    async def flush(self) -> None:
        pass


class _ApiKeyRepo:
    def __init__(self) -> None:
        self.records: list[ApiKeyRecord] = []

    async def create(self, record: ApiKeyRecord) -> ApiKeyRecord:
        self.records.append(record)
        return record

    async def list_by_user_id(self, user_id: UUID) -> list[ApiKeyRecord]:
        return [record for record in self.records if record.user_id == user_id]

    async def get_by_hash(self, key_hash: str) -> ApiKeyRecord | None:
        return next((record for record in self.records if record.key_hash == key_hash), None)

    async def mark_used(self, api_key_id: UUID, used_at: datetime) -> None:
        self.records = [
            ApiKeyRecord(
                id=record.id,
                user_id=record.user_id,
                name=record.name,
                key_hash=record.key_hash,
                prefix=record.prefix,
                scopes=record.scopes,
                last_used_at=used_at if record.id == api_key_id else record.last_used_at,
                revoked_at=record.revoked_at,
                created_at=record.created_at,
            )
            for record in self.records
        ]

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


def _record(*, user_id: UUID) -> ApiKeyRecord:
    return ApiKeyRecord(
        id=uuid4(),
        user_id=user_id,
        name="Key",
        key_hash="hash",
        prefix="ctx_prefix",
        scopes=["ingest:write"],
        last_used_at=None,
        revoked_at=None,
        created_at=datetime.now(UTC),
    )
