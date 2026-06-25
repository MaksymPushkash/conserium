from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.documents.schemas import DocumentProcessingOutboxRecord
from src.models.document_processing_outbox import DocumentProcessingOutboxModel

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession


class DocumentProcessingOutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @classmethod
    def from_session(cls, session: AsyncSession) -> DocumentProcessingOutboxRepository:
        return cls(session)

    async def create_outbox(self, *, document_id: UUID, task_name: str) -> DocumentProcessingOutboxRecord:
        result = await self._session.execute(
            pg_insert(DocumentProcessingOutboxModel)
            .values(
                id=uuid.uuid4(),
                document_id=document_id,
                task_name=task_name,
                status="pending",
                attempts=0,
            )
            .on_conflict_do_update(
                index_elements=[
                    DocumentProcessingOutboxModel.document_id,
                    DocumentProcessingOutboxModel.task_name,
                ],
                index_where=DocumentProcessingOutboxModel.status != "dispatched",
                set_={
                    "status": "pending",
                    "locked_at": None,
                    "last_error": None,
                },
            )
            .returning(DocumentProcessingOutboxModel)
        )
        return self._to_record(result.scalar_one())

    async def claim_batch(
        self,
        *,
        limit: int,
        locked_at: datetime,
        stale_before: datetime,
        max_attempts: int,
    ) -> list[DocumentProcessingOutboxRecord]:
        result = await self._session.execute(
            select(DocumentProcessingOutboxModel)
            .where(
                DocumentProcessingOutboxModel.status.in_(("pending", "dispatching", "processing")),
                DocumentProcessingOutboxModel.attempts < max_attempts,
                or_(
                    DocumentProcessingOutboxModel.status == "pending",
                    DocumentProcessingOutboxModel.locked_at <= stale_before,
                ),
            )
            .order_by(DocumentProcessingOutboxModel.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        models = result.scalars().all()
        for model in models:
            model.status = "dispatching"
            model.locked_at = locked_at
            model.attempts += 1
        await self._session.flush()
        return [self._to_record(model) for model in models]


    async def get_by_id(self, outbox_id: UUID) -> DocumentProcessingOutboxRecord | None:
        result = await self._session.execute(select(DocumentProcessingOutboxModel).where(DocumentProcessingOutboxModel.id == outbox_id))
        model = result.scalar_one_or_none()
        return self._to_record(model) if model is not None else None

    async def mark_dispatching(self, outbox_id: UUID, locked_at: datetime) -> DocumentProcessingOutboxRecord:
        result = await self._session.execute(select(DocumentProcessingOutboxModel).where(DocumentProcessingOutboxModel.id == outbox_id))
        model = result.scalar_one()
        model.status = "dispatching"
        model.locked_at = locked_at
        model.last_error = None
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_record(model)

    async def mark_dispatched(self, outbox_id: UUID, dispatched_at: datetime) -> DocumentProcessingOutboxRecord:
        result = await self._session.execute(select(DocumentProcessingOutboxModel).where(DocumentProcessingOutboxModel.id == outbox_id))
        model = result.scalar_one()
        model.status = "dispatched"
        model.dispatched_at = dispatched_at
        model.locked_at = None
        model.last_error = None
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_record(model)

    async def mark_failed(self, outbox_id: UUID, *, last_error: str, retryable: bool) -> DocumentProcessingOutboxRecord:
        result = await self._session.execute(select(DocumentProcessingOutboxModel).where(DocumentProcessingOutboxModel.id == outbox_id))
        model = result.scalar_one()
        model.status = "pending" if retryable else "failed"
        model.locked_at = None
        model.last_error = last_error
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_record(model)

    @staticmethod
    def _to_record(model: DocumentProcessingOutboxModel) -> DocumentProcessingOutboxRecord:
        return DocumentProcessingOutboxRecord(
            id=model.id,
            document_id=model.document_id,
            task_name=model.task_name,
            status=model.status,
            attempts=model.attempts,
            locked_at=model.locked_at,
            last_error=model.last_error,
            dispatched_at=model.dispatched_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
