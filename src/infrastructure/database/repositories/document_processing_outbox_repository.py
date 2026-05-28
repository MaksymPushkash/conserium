import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.dtos.document_processing_outbox_dtos import DocumentProcessingOutboxDTO
from src.application.ports.persistence.document_processing_outbox_repository import IDocumentProcessingOutboxRepository
from src.infrastructure.database.models.document_processing_outbox import DocumentProcessingOutboxModel


class SQLAlchemyDocumentProcessingOutboxRepository(IDocumentProcessingOutboxRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_outbox(self, *, document_id: UUID, task_name: str) -> DocumentProcessingOutboxDTO:
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
        return self._to_dto(result.scalar_one())

    async def claim_batch(
        self,
        *,
        limit: int,
        locked_at: datetime,
        stale_before: datetime,
        max_attempts: int,
    ) -> list[DocumentProcessingOutboxDTO]:
        result = await self._session.execute(
            select(DocumentProcessingOutboxModel)
            .where(
                DocumentProcessingOutboxModel.status.in_(("pending", "processing")),
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
            model.status = "processing"
            model.locked_at = locked_at
            model.attempts += 1
        await self._session.flush()
        return [self._to_dto(model) for model in models]

    async def mark_dispatched(self, outbox_id: UUID, dispatched_at: datetime) -> DocumentProcessingOutboxDTO:
        result = await self._session.execute(select(DocumentProcessingOutboxModel).where(DocumentProcessingOutboxModel.id == outbox_id))
        model = result.scalar_one()
        model.status = "dispatched"
        model.dispatched_at = dispatched_at
        model.locked_at = None
        model.last_error = None
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_dto(model)

    async def mark_failed(self, outbox_id: UUID, *, last_error: str, retryable: bool) -> DocumentProcessingOutboxDTO:
        result = await self._session.execute(select(DocumentProcessingOutboxModel).where(DocumentProcessingOutboxModel.id == outbox_id))
        model = result.scalar_one()
        model.status = "pending" if retryable else "failed"
        model.locked_at = None
        model.last_error = last_error
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_dto(model)

    @staticmethod
    def _to_dto(model: DocumentProcessingOutboxModel) -> DocumentProcessingOutboxDTO:
        return DocumentProcessingOutboxDTO(
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
