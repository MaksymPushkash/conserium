import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.persistence.flashcard_repository import (
    FlashcardRecord,
    FlashcardReviewRecord,
    IFlashcardRepository,
)
from src.infrastructure.database.models.document import DocumentModel
from src.infrastructure.database.models.flashcard import FlashcardModel, FlashcardReviewModel


class SQLAlchemyFlashcardRepository(IFlashcardRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_many(self, records: list[FlashcardRecord]) -> list[FlashcardRecord]:
        models = [self._to_model(record) for record in records]
        self._session.add_all(models)
        await self._session.flush()
        return [self._to_record(model) for model in models]

    async def list_due(self, *, user_id: UUID, now: datetime, limit: int = 20) -> list[FlashcardRecord]:
        statement = (
            select(FlashcardModel, DocumentModel.title)
            .outerjoin(DocumentModel, FlashcardModel.source_document_id == DocumentModel.id)
            .where(FlashcardModel.user_id == user_id)
            .where(FlashcardModel.due_at <= now)
            .order_by(FlashcardModel.due_at.asc(), FlashcardModel.created_at.asc())
            .limit(limit)
        )
        rows = (await self._session.execute(statement)).all()
        return [self._to_record(model, source_title=title) for model, title in rows]

    async def count_due(self, *, user_id: UUID, now: datetime) -> int:
        result = await self._session.execute(
            select(func.count(FlashcardModel.id))
            .where(FlashcardModel.user_id == user_id)
            .where(FlashcardModel.due_at <= now)
        )
        return int(result.scalar_one() or 0)

    async def get_by_id(self, flashcard_id: UUID) -> FlashcardRecord | None:
        row = (
            await self._session.execute(
                select(FlashcardModel, DocumentModel.title)
                .outerjoin(DocumentModel, FlashcardModel.source_document_id == DocumentModel.id)
                .where(FlashcardModel.id == flashcard_id)
            )
        ).one_or_none()
        if row is None:
            return None
        model, title = row
        return self._to_record(model, source_title=title)

    async def update_schedule(
        self,
        *,
        flashcard_id: UUID,
        due_at: datetime,
        interval_days: int,
        ease_factor: float,
        review_count: int,
    ) -> FlashcardRecord:
        model = await self._session.scalar(select(FlashcardModel).where(FlashcardModel.id == flashcard_id))
        if model is None:
            raise ValueError("flashcard not found")
        model.due_at = due_at
        model.interval_days = interval_days
        model.ease_factor = ease_factor
        model.review_count = review_count
        await self._session.flush()
        return self._to_record(model)

    async def create_review(self, record: FlashcardReviewRecord) -> None:
        self._session.add(
            FlashcardReviewModel(
                id=record.id,
                flashcard_id=record.flashcard_id,
                user_id=record.user_id,
                grade=record.grade,
                previous_interval_days=record.previous_interval_days,
                next_interval_days=record.next_interval_days,
                previous_ease_factor=record.previous_ease_factor,
                next_ease_factor=record.next_ease_factor,
                reviewed_at=record.reviewed_at,
            )
        )

    async def existing_questions_for_document(self, *, user_id: UUID, document_id: UUID) -> set[str]:
        result = await self._session.scalars(
            select(FlashcardModel.question)
            .where(FlashcardModel.user_id == user_id)
            .where(FlashcardModel.source_document_id == document_id)
        )
        return {question.strip().lower() for question in result.all()}

    def _to_model(self, record: FlashcardRecord) -> FlashcardModel:
        return FlashcardModel(
            id=record.id,
            user_id=record.user_id,
            scope_type=record.scope_type,
            collection_id=record.collection_id,
            topic=record.topic,
            source_document_id=record.source_document_id,
            source_chunk_id=record.source_chunk_id,
            question=record.question,
            answer=record.answer,
            citation_metadata=record.citation_metadata,
            due_at=record.due_at,
            interval_days=record.interval_days,
            ease_factor=record.ease_factor,
            review_count=record.review_count,
        )

    def _to_record(self, model: FlashcardModel, *, source_title: str | None = None) -> FlashcardRecord:
        return FlashcardRecord(
            id=model.id,
            user_id=model.user_id,
            scope_type=model.scope_type,
            collection_id=model.collection_id,
            topic=model.topic,
            source_document_id=model.source_document_id,
            source_chunk_id=model.source_chunk_id,
            question=model.question,
            answer=model.answer,
            citation_metadata=model.citation_metadata or {},
            due_at=model.due_at,
            interval_days=model.interval_days,
            ease_factor=model.ease_factor,
            review_count=model.review_count,
            source_title=source_title,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


def new_flashcard_id() -> uuid.UUID:
    return uuid.uuid4()
