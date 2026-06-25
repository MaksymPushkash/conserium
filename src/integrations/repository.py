from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.integrations.schemas import ExternalConnectionRecord
from src.models.external_connection import ExternalConnectionModel
from src.models.telegram import TelegramChatBindingModel, TelegramPairingCodeModel

if TYPE_CHECKING:
    from datetime import datetime
    from typing import Any
    from uuid import UUID

    from src.api_keys.repository import ApiKeyRepository as FeatureApiKeyRepository
    from src.postgres import AsyncSession


@dataclass(slots=True)
class TelegramPairingCodeRecord:
    id: UUID
    user_id: UUID
    api_key_id: UUID
    code_hash: str
    expires_at: datetime
    consumed_at: datetime | None
    created_at: datetime
    updated_at: datetime | None = None


@dataclass(slots=True)
class TelegramChatBindingRecord:
    id: UUID
    user_id: UUID
    api_key_id: UUID | None
    chat_id: str
    chat_username: str | None
    chat_title: str | None
    paired_at: datetime
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime | None = None


class ApiKeyRepository:
    @classmethod
    def from_session(cls, session: AsyncSession) -> FeatureApiKeyRepository:
        from src.api_keys.repository import ApiKeyRepository as FeatureApiKeyRepository

        return FeatureApiKeyRepository(session)


class ExternalConnectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @classmethod
    def from_session(cls, session: AsyncSession) -> ExternalConnectionRepository:
        return cls(session)

    async def get_by_provider(self, *, user_id: UUID, provider: str) -> ExternalConnectionRecord | None:
        result = await self._session.execute(
            select(ExternalConnectionModel).where(
                ExternalConnectionModel.user_id == user_id,
                ExternalConnectionModel.provider == provider,
            )
        )
        model = result.scalar_one_or_none()
        return self._to_record(model) if model else None

    async def upsert(
        self,
        *,
        user_id: UUID,
        provider: str,
        workspace_id: str | None,
        workspace_name: str | None,
        access_token_encrypted: str,
        bot_id: str | None,
        owner: dict[str, Any] | None,
    ) -> ExternalConnectionRecord:
        result = await self._session.execute(
            select(ExternalConnectionModel).where(
                ExternalConnectionModel.user_id == user_id,
                ExternalConnectionModel.provider == provider,
            )
        )
        model = result.scalar_one_or_none()
        if model is None:
            model = ExternalConnectionModel(user_id=user_id, provider=provider, access_token_encrypted=access_token_encrypted)
            self._session.add(model)

        model.workspace_id = workspace_id
        model.workspace_name = workspace_name
        model.access_token_encrypted = access_token_encrypted
        model.bot_id = bot_id
        model.owner = owner
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_record(model)

    async def update_settings(
        self,
        *,
        user_id: UUID,
        provider: str,
        default_parent_page_id: str | None,
        default_parent_page_title: str | None,
    ) -> ExternalConnectionRecord | None:
        result = await self._session.execute(
            select(ExternalConnectionModel).where(
                ExternalConnectionModel.user_id == user_id,
                ExternalConnectionModel.provider == provider,
            )
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        model.default_parent_page_id = default_parent_page_id
        model.default_parent_page_title = default_parent_page_title if default_parent_page_id else None
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_record(model)

    async def delete_by_provider(self, *, user_id: UUID, provider: str) -> bool:
        result = await self._session.execute(
            delete(ExternalConnectionModel)
            .where(
                ExternalConnectionModel.user_id == user_id,
                ExternalConnectionModel.provider == provider,
            )
            .returning(ExternalConnectionModel.id)
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    def _to_record(model: ExternalConnectionModel) -> ExternalConnectionRecord:
        return ExternalConnectionRecord(
            id=model.id,
            user_id=model.user_id,
            provider=model.provider,
            workspace_id=model.workspace_id,
            workspace_name=model.workspace_name,
            access_token_encrypted=model.access_token_encrypted,
            bot_id=model.bot_id,
            owner=model.owner,
            default_parent_page_id=model.default_parent_page_id,
            default_parent_page_title=model.default_parent_page_title,
        )


class TelegramRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @classmethod
    def from_session(cls, session: AsyncSession) -> TelegramRepository:
        return cls(session)

    async def create_pairing_code(self, record: TelegramPairingCodeRecord) -> TelegramPairingCodeRecord:
        model = TelegramPairingCodeModel(
            id=record.id,
            user_id=record.user_id,
            api_key_id=record.api_key_id,
            code_hash=record.code_hash,
            expires_at=record.expires_at,
            consumed_at=record.consumed_at,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return self._pairing_to_record(model)

    async def get_pairing_code_by_hash(self, code_hash: str) -> TelegramPairingCodeRecord | None:
        result = await self._session.execute(
            select(TelegramPairingCodeModel).where(TelegramPairingCodeModel.code_hash == code_hash)
        )
        model = result.scalar_one_or_none()
        return self._pairing_to_record(model) if model is not None else None

    async def consume_pairing_code(self, pairing_code_id: UUID, consumed_at: datetime) -> TelegramPairingCodeRecord:
        result = await self._session.execute(
            select(TelegramPairingCodeModel).where(TelegramPairingCodeModel.id == pairing_code_id)
        )
        model = result.scalar_one()
        model.consumed_at = consumed_at
        await self._session.flush()
        await self._session.refresh(model)
        return self._pairing_to_record(model)

    async def list_bindings_by_user_id(self, user_id: UUID) -> list[TelegramChatBindingRecord]:
        result = await self._session.execute(
            select(TelegramChatBindingModel)
            .where(TelegramChatBindingModel.user_id == user_id)
            .order_by(TelegramChatBindingModel.created_at.desc())
        )
        return [self._binding_to_record(model) for model in result.scalars().all()]

    async def list_active_bindings(self, *, limit: int = 500) -> list[TelegramChatBindingRecord]:
        result = await self._session.execute(
            select(TelegramChatBindingModel)
            .where(TelegramChatBindingModel.revoked_at.is_(None))
            .order_by(TelegramChatBindingModel.created_at.desc())
            .limit(limit)
        )
        return [self._binding_to_record(model) for model in result.scalars().all()]

    async def get_active_binding_by_chat_id(self, chat_id: str) -> TelegramChatBindingRecord | None:
        result = await self._session.execute(
            select(TelegramChatBindingModel).where(
                TelegramChatBindingModel.chat_id == chat_id,
                TelegramChatBindingModel.revoked_at.is_(None),
            )
        )
        model = result.scalar_one_or_none()
        return self._binding_to_record(model) if model is not None else None

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
        result = await self._session.execute(
            pg_insert(TelegramChatBindingModel)
            .values(
                id=uuid4(),
                user_id=user_id,
                api_key_id=api_key_id,
                chat_id=chat_id,
                chat_username=chat_username,
                chat_title=chat_title,
                paired_at=paired_at,
                revoked_at=None,
            )
            .on_conflict_do_update(
                index_elements=[TelegramChatBindingModel.chat_id],
                index_where=TelegramChatBindingModel.revoked_at.is_(None),
                set_={
                    "user_id": user_id,
                    "api_key_id": api_key_id,
                    "chat_username": chat_username,
                    "chat_title": chat_title,
                    "paired_at": paired_at,
                },
            )
            .returning(TelegramChatBindingModel)
        )
        return self._binding_to_record(result.scalar_one())

    async def revoke_binding(
        self,
        *,
        user_id: UUID,
        binding_id: UUID,
        revoked_at: datetime,
    ) -> TelegramChatBindingRecord | None:
        result = await self._session.execute(
            select(TelegramChatBindingModel).where(
                TelegramChatBindingModel.id == binding_id,
                TelegramChatBindingModel.user_id == user_id,
            )
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        model.revoked_at = revoked_at
        await self._session.flush()
        await self._session.refresh(model)
        return self._binding_to_record(model)

    @staticmethod
    def _pairing_to_record(model: TelegramPairingCodeModel) -> TelegramPairingCodeRecord:
        return TelegramPairingCodeRecord(
            id=model.id,
            user_id=model.user_id,
            api_key_id=model.api_key_id,
            code_hash=model.code_hash,
            expires_at=model.expires_at,
            consumed_at=model.consumed_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _binding_to_record(model: TelegramChatBindingModel) -> TelegramChatBindingRecord:
        return TelegramChatBindingRecord(
            id=model.id,
            user_id=model.user_id,
            api_key_id=model.api_key_id,
            chat_id=model.chat_id,
            chat_username=model.chat_username,
            chat_title=model.chat_title,
            paired_at=model.paired_at,
            revoked_at=model.revoked_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


__all__ = [
    "ApiKeyRepository",
    "ExternalConnectionRepository",
    "TelegramChatBindingRecord",
    "TelegramPairingCodeRecord",
    "TelegramRepository",
]
