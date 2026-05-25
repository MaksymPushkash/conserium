from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.persistence.api_key_repository import ApiKeyRecord, IApiKeyRepository
from src.infrastructure.database.models.api_key import ApiKeyModel


class SQLAlchemyApiKeyRepository(IApiKeyRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, record: ApiKeyRecord) -> ApiKeyRecord:
        model = ApiKeyModel(
            id=record.id,
            user_id=record.user_id,
            name=record.name,
            key_hash=record.key_hash,
            prefix=record.prefix,
            scopes=record.scopes,
            last_used_at=record.last_used_at,
            revoked_at=record.revoked_at,
            created_at=record.created_at,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_record(model)

    async def list_by_user_id(self, user_id: UUID) -> list[ApiKeyRecord]:
        result = await self._session.execute(
            select(ApiKeyModel)
            .where(ApiKeyModel.user_id == user_id)
            .order_by(ApiKeyModel.created_at.desc())
        )
        return [self._to_record(model) for model in result.scalars().all()]

    async def get_by_hash(self, key_hash: str) -> ApiKeyRecord | None:
        result = await self._session.execute(select(ApiKeyModel).where(ApiKeyModel.key_hash == key_hash))
        model = result.scalar_one_or_none()
        return self._to_record(model) if model else None

    async def mark_used(self, api_key_id: UUID, used_at: datetime) -> None:
        result = await self._session.execute(select(ApiKeyModel).where(ApiKeyModel.id == api_key_id))
        model = result.scalar_one()
        model.last_used_at = used_at
        await self._session.flush()

    async def revoke(self, *, api_key_id: UUID, user_id: UUID, revoked_at: datetime) -> None:
        result = await self._session.execute(
            select(ApiKeyModel).where(ApiKeyModel.id == api_key_id, ApiKeyModel.user_id == user_id)
        )
        model = result.scalar_one_or_none()
        if model is not None and model.revoked_at is None:
            model.revoked_at = revoked_at
            await self._session.flush()

    @staticmethod
    def _to_record(model: ApiKeyModel) -> ApiKeyRecord:
        return ApiKeyRecord(
            id=model.id,
            user_id=model.user_id,
            name=model.name,
            key_hash=model.key_hash,
            prefix=model.prefix,
            scopes=list(model.scopes),
            last_used_at=model.last_used_at,
            revoked_at=model.revoked_at,
            created_at=model.created_at,
        )
