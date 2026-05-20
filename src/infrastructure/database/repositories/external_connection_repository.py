from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.dtos.external_connection_dtos import ExternalConnectionDTO
from src.application.ports.persistence.external_connection_repository import IExternalConnectionRepository
from src.infrastructure.database.models.external_connection import ExternalConnectionModel


class SQLAlchemyExternalConnectionRepository(IExternalConnectionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_provider(self, *, user_id: UUID, provider: str) -> ExternalConnectionDTO | None:
        result = await self._session.execute(
            select(ExternalConnectionModel).where(
                ExternalConnectionModel.user_id == user_id,
                ExternalConnectionModel.provider == provider,
            )
        )
        model = result.scalar_one_or_none()
        return self._to_dto(model) if model else None

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
    ) -> ExternalConnectionDTO:
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
        return self._to_dto(model)

    async def update_settings(
        self,
        *,
        user_id: UUID,
        provider: str,
        default_parent_page_id: str | None,
        default_parent_page_title: str | None,
    ) -> ExternalConnectionDTO | None:
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
        return self._to_dto(model)

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
    def _to_dto(model: ExternalConnectionModel) -> ExternalConnectionDTO:
        return ExternalConnectionDTO(
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
