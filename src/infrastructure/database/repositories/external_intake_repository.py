from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.persistence.external_intake_repository import (
    ExternalIntakeItemRecord,
    IExternalIntakeRepository,
)
from src.application.use_cases.external_intake import INTAKE_STATUS_FAILED, INTAKE_STATUS_QUEUED
from src.infrastructure.database.models.external_intake import ExternalIntakeItemModel


class SQLAlchemyExternalIntakeRepository(IExternalIntakeRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, record: ExternalIntakeItemRecord) -> ExternalIntakeItemRecord:
        result = await self._session.execute(
            pg_insert(ExternalIntakeItemModel)
            .values(
                id=record.id,
                user_id=record.user_id,
                api_key_id=record.api_key_id,
                provider=record.provider,
                external_id=record.external_id,
                idempotency_key=record.idempotency_key,
                title=record.title,
                type=record.type,
                collection_id=record.collection_id,
                tags=record.tags,
                source_url=record.source_url,
                raw_content=record.raw_content,
                language=record.language,
                status=record.status,
                error_reason=record.error_reason,
                document_id=record.document_id,
                payload_metadata=record.payload_metadata,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    ExternalIntakeItemModel.user_id,
                    ExternalIntakeItemModel.provider,
                    ExternalIntakeItemModel.idempotency_key,
                ]
            )
            .returning(ExternalIntakeItemModel)
        )
        model = result.scalar_one_or_none()
        if model is None and record.idempotency_key is not None:
            existing = await self.get_by_idempotency_key(
                user_id=record.user_id,
                provider=record.provider,
                idempotency_key=record.idempotency_key,
            )
            if existing is not None:
                return existing
        if model is None:
            model = await self._get_model(record.id)
        return self._to_record(model)

    async def get_by_id(self, *, user_id: UUID, intake_item_id: UUID) -> ExternalIntakeItemRecord | None:
        result = await self._session.execute(
            select(ExternalIntakeItemModel).where(
                ExternalIntakeItemModel.id == intake_item_id,
                ExternalIntakeItemModel.user_id == user_id,
            )
        )
        model = result.scalar_one_or_none()
        return self._to_record(model) if model is not None else None

    async def list_by_user_id(
        self,
        *,
        user_id: UUID,
        limit: int,
        offset: int,
    ) -> list[ExternalIntakeItemRecord]:
        result = await self._session.execute(
            select(ExternalIntakeItemModel)
            .where(ExternalIntakeItemModel.user_id == user_id)
            .order_by(ExternalIntakeItemModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [self._to_record(model) for model in result.scalars().all()]

    async def get_by_idempotency_key(
        self,
        *,
        user_id: UUID,
        provider: str,
        idempotency_key: str,
    ) -> ExternalIntakeItemRecord | None:
        result = await self._session.execute(
            select(ExternalIntakeItemModel).where(
                ExternalIntakeItemModel.user_id == user_id,
                ExternalIntakeItemModel.provider == provider,
                ExternalIntakeItemModel.idempotency_key == idempotency_key,
            )
        )
        model = result.scalar_one_or_none()
        return self._to_record(model) if model is not None else None

    async def mark_queued(
        self,
        *,
        intake_item_id: UUID,
        document_id: UUID,
    ) -> ExternalIntakeItemRecord:
        model = await self._get_model(intake_item_id)
        model.document_id = document_id
        model.status = INTAKE_STATUS_QUEUED
        model.error_reason = None
        await self._session.flush()
        return self._to_record(model)

    async def mark_failed(
        self,
        *,
        intake_item_id: UUID,
        error_reason: str,
    ) -> ExternalIntakeItemRecord:
        model = await self._get_model(intake_item_id)
        model.status = INTAKE_STATUS_FAILED
        model.error_reason = error_reason
        await self._session.flush()
        return self._to_record(model)

    async def _get_model(self, intake_item_id: UUID) -> ExternalIntakeItemModel:
        result = await self._session.execute(
            select(ExternalIntakeItemModel).where(ExternalIntakeItemModel.id == intake_item_id)
        )
        return result.scalar_one()

    @staticmethod
    def _to_record(model: ExternalIntakeItemModel) -> ExternalIntakeItemRecord:
        return ExternalIntakeItemRecord(
            id=model.id,
            user_id=model.user_id,
            api_key_id=model.api_key_id,
            provider=model.provider,
            external_id=model.external_id,
            idempotency_key=model.idempotency_key,
            title=model.title,
            type=model.type,
            collection_id=model.collection_id,
            tags=model.tags,
            source_url=model.source_url,
            raw_content=model.raw_content,
            language=model.language,
            status=model.status,
            error_reason=model.error_reason,
            document_id=model.document_id,
            payload_metadata=model.payload_metadata,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
