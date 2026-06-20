from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from src.models.document import DocumentModel
from src.models.flashcard import FlashcardModel, FlashcardReviewModel
from src.models.learning_path import LearningPathModel
from src.models.quiz import QuizAttemptModel, QuizModel

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class FlashcardRecord:
    id: UUID
    user_id: UUID
    scope_type: str
    collection_id: UUID | None
    topic: str | None
    source_document_id: UUID | None
    source_chunk_id: UUID | None
    question: str
    answer: str
    citation_metadata: dict[str, object]
    due_at: datetime
    interval_days: int
    ease_factor: float
    review_count: int
    source_title: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class FlashcardReviewRecord:
    id: UUID
    flashcard_id: UUID
    user_id: UUID
    grade: str
    previous_interval_days: int
    next_interval_days: int
    previous_ease_factor: float
    next_ease_factor: float
    reviewed_at: datetime


@dataclass(frozen=True, slots=True)
class LearningPathRecord:
    id: UUID
    user_id: UUID
    scope_type: str
    collection_id: UUID | None
    topic: str | None
    source_document_id: UUID | None
    title: str
    steps: list[dict[str, object]]
    created_at: datetime
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class QuizRecord:
    id: UUID
    user_id: UUID
    scope_type: str
    collection_id: UUID | None
    topic: str | None
    source_document_id: UUID | None
    title: str
    questions: list[dict[str, object]]
    source_title: str | None
    created_at: datetime
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class QuizAttemptRecord:
    id: UUID
    quiz_id: UUID
    user_id: UUID
    answers: list[dict[str, object]]
    score: int
    total: int
    weak_areas: list[str]
    created_at: datetime
    quiz_title: str | None = None


@dataclass(frozen=True, slots=True)
class QuizWeakAreaRecord:
    name: str
    count: int
    last_seen_at: datetime


class FlashcardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @classmethod
    def from_session(cls, session: AsyncSession) -> FlashcardRepository:
        return cls(session)

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


class LearningPathRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @classmethod
    def from_session(cls, session: AsyncSession) -> LearningPathRepository:
        return cls(session)

    async def create(self, record: LearningPathRecord) -> LearningPathRecord:
        model = LearningPathModel(
            id=record.id,
            user_id=record.user_id,
            scope_type=record.scope_type,
            collection_id=record.collection_id,
            topic=record.topic,
            source_document_id=record.source_document_id,
            title=record.title,
            steps=record.steps,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_record(model)

    async def get_by_id(self, path_id: UUID) -> LearningPathRecord | None:
        result = await self._session.scalars(select(LearningPathModel).where(LearningPathModel.id == path_id))
        model = result.one_or_none()
        return self._to_record(model) if model is not None else None

    async def update_steps(self, path_id: UUID, steps: list[dict[str, object]]) -> LearningPathRecord:
        result = await self._session.scalars(select(LearningPathModel).where(LearningPathModel.id == path_id))
        model = result.one()
        model.steps = steps
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_record(model)

    async def list_by_user(self, *, user_id: UUID, limit: int = 20) -> list[LearningPathRecord]:
        result = await self._session.scalars(
            select(LearningPathModel)
            .where(LearningPathModel.user_id == user_id)
            .order_by(LearningPathModel.created_at.desc())
            .limit(limit)
        )
        return [self._to_record(model) for model in result.all()]

    def _to_record(self, model: LearningPathModel) -> LearningPathRecord:
        return LearningPathRecord(
            id=model.id,
            user_id=model.user_id,
            scope_type=model.scope_type,
            collection_id=model.collection_id,
            topic=model.topic,
            source_document_id=model.source_document_id,
            title=model.title,
            steps=model.steps or [],
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class QuizRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @classmethod
    def from_session(cls, session: AsyncSession) -> QuizRepository:
        return cls(session)

    async def create(self, record: QuizRecord) -> QuizRecord:
        model = QuizModel(
            id=record.id,
            user_id=record.user_id,
            scope_type=record.scope_type,
            collection_id=record.collection_id,
            topic=record.topic,
            source_document_id=record.source_document_id,
            title=record.title,
            questions=record.questions,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_quiz_record(model, source_title=record.source_title)

    async def get_by_id(self, quiz_id: UUID) -> QuizRecord | None:
        row = (
            await self._session.execute(
                select(QuizModel, DocumentModel.title)
                .outerjoin(DocumentModel, QuizModel.source_document_id == DocumentModel.id)
                .where(QuizModel.id == quiz_id)
            )
        ).one_or_none()
        if row is None:
            return None
        model, source_title = row
        return self._to_quiz_record(model, source_title=source_title)

    async def create_attempt(self, record: QuizAttemptRecord) -> QuizAttemptRecord:
        model = QuizAttemptModel(
            id=record.id,
            quiz_id=record.quiz_id,
            user_id=record.user_id,
            answers=record.answers,
            score=record.score,
            total=record.total,
            weak_areas=record.weak_areas,
            created_at=record.created_at,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_attempt_record(model)

    async def list_by_user(self, *, user_id: UUID, limit: int = 20) -> list[QuizRecord]:
        rows = (
            await self._session.execute(
                select(QuizModel, DocumentModel.title)
                .outerjoin(DocumentModel, QuizModel.source_document_id == DocumentModel.id)
                .where(QuizModel.user_id == user_id)
                .order_by(QuizModel.created_at.desc())
                .limit(limit)
            )
        ).all()
        return [self._to_quiz_record(model, source_title=source_title) for model, source_title in rows]

    async def list_attempts_by_user(self, *, user_id: UUID, limit: int = 20) -> list[QuizAttemptRecord]:
        rows = (
            await self._session.execute(
                select(QuizAttemptModel, QuizModel.title)
                .join(QuizModel, QuizAttemptModel.quiz_id == QuizModel.id)
                .where(QuizAttemptModel.user_id == user_id)
                .order_by(QuizAttemptModel.created_at.desc())
                .limit(limit)
            )
        ).all()
        return [self._to_attempt_record(model, quiz_title=quiz_title) for model, quiz_title in rows]

    async def list_weak_areas(self, *, user_id: UUID, limit: int = 10) -> list[QuizWeakAreaRecord]:
        attempts = await self.list_attempts_by_user(user_id=user_id, limit=max(limit * 10, 50))
        counts: Counter[str] = Counter()
        last_seen: dict[str, datetime] = {}
        for attempt in attempts:
            for area in attempt.weak_areas:
                if not area:
                    continue
                counts[area] += 1
                last_seen[area] = max(last_seen.get(area, attempt.created_at), attempt.created_at)
        return [QuizWeakAreaRecord(name=name, count=count, last_seen_at=last_seen[name]) for name, count in counts.most_common(limit)]

    def _to_quiz_record(self, model: QuizModel, *, source_title: str | None = None) -> QuizRecord:
        return QuizRecord(
            id=model.id,
            user_id=model.user_id,
            scope_type=model.scope_type,
            collection_id=model.collection_id,
            topic=model.topic,
            source_document_id=model.source_document_id,
            title=model.title,
            questions=model.questions or [],
            source_title=source_title,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_attempt_record(self, model: QuizAttemptModel, *, quiz_title: str | None = None) -> QuizAttemptRecord:
        return QuizAttemptRecord(
            id=model.id,
            quiz_id=model.quiz_id,
            user_id=model.user_id,
            answers=model.answers or [],
            score=model.score,
            total=model.total,
            weak_areas=model.weak_areas or [],
            created_at=model.created_at,
            quiz_title=quiz_title,
        )


def new_flashcard_id() -> uuid.UUID:
    return uuid.uuid4()


__all__ = [
    "FlashcardRecord",
    "FlashcardRepository",
    "FlashcardReviewRecord",
    "LearningPathRecord",
    "LearningPathRepository",
    "QuizAttemptRecord",
    "QuizRecord",
    "QuizRepository",
    "QuizWeakAreaRecord",
    "new_flashcard_id",
]
