import uuid
from dataclasses import replace
from datetime import UTC, datetime
from typing import cast

import pytest

from src.documents.status import DocumentStatus
from src.documents.types import DocumentType
from src.kit.exceptions import ResourceNotFoundException
from src.models.chunk import ChunkModel
from src.models.document import DocumentModel
from src.review.grade import ReviewGrade
from src.review.repository import FlashcardRecord, FlashcardReviewRecord
from src.review.schedule import next_review_schedule
from src.review.schemas import GenerateFlashcardsPayload, ReviewFlashcard
from src.review.service import (
    FlashcardGenerator,
    FlashcardReviewer,
    ReviewService,
    list_due_flashcards,
)
from src.topics.repository import TopicDetailRecord, TopicDocumentRecord, TopicRecord


async def test_generate_flashcards_uses_document_summary_and_suggested_questions() -> None:
    user_id = uuid.uuid4()
    document = _document(user_id=user_id, suggested_questions=["What is asyncio?"], summary="Asyncio runs cooperative I/O.")
    persistence = _ReviewPersistence([document], [_chunk(document.id, "Asyncio uses one event loop.")])
    handler = _flashcard_generator(persistence)

    result = await handler(GenerateFlashcardsPayload(user_id=user_id, document_id=document.id, limit=3))

    assert result.created_count == 3
    assert result.items[0].question == "What is asyncio?"
    assert result.items[0].answer == "Asyncio runs cooperative I/O."
    assert persistence.committed is True


async def test_generate_flashcards_preserves_collection_scope() -> None:
    user_id = uuid.uuid4()
    collection_id = uuid.uuid4()
    document = _document(
        user_id=user_id,
        suggested_questions=["What is collection scope?"],
        summary="Collection scoped cards stay attached.",
        collection_id=collection_id,
    )
    persistence = _ReviewPersistence([document], [])
    handler = _flashcard_generator(persistence)

    result = await handler(GenerateFlashcardsPayload(user_id=user_id, collection_id=collection_id, limit=1))

    assert result.items[0].scope_type == "collection"
    assert result.items[0].collection_id == collection_id
    assert result.items[0].topic is None


async def test_generate_flashcards_preserves_topic_scope() -> None:
    user_id = uuid.uuid4()
    document = _document(
        user_id=user_id,
        suggested_questions=["What is topic scope?"],
        summary="Topic scoped cards keep the topic name.",
    )
    persistence = _ReviewPersistence([document], [])
    persistence.topic_repo.detail = TopicDetailRecord(
        topic=TopicRecord(name="python", document_count=1, last_document_at=document.created_at),
        documents=[
            TopicDocumentRecord(
                id=document.id,
                title=document.title,
                type=document.type.value,
                status=document.status.value,
                summary=document.summary,
                created_at=document.created_at,
            )
        ],
    )
    handler = _flashcard_generator(persistence)

    result = await handler(GenerateFlashcardsPayload(user_id=user_id, topic="python", limit=1))

    assert result.items[0].scope_type == "topic"
    assert result.items[0].collection_id is None
    assert result.items[0].topic == "python"


async def test_due_flashcards_return_total() -> None:
    user_id = uuid.uuid4()
    card = _flashcard(user_id=user_id)
    persistence = _ReviewPersistence([], [])
    persistence.flashcard_repo.cards[card.id] = card
    result = await list_due_flashcards(persistence.flashcard_repo, user_id=user_id, limit=10)

    assert result.total == 1
    assert result.items[0].id == card.id


async def test_review_flashcard_updates_schedule_and_records_review() -> None:
    user_id = uuid.uuid4()
    card = _flashcard(user_id=user_id, interval_days=1, ease_factor=2.5)
    persistence = _ReviewPersistence([], [])
    persistence.flashcard_repo.cards[card.id] = card
    handler = FlashcardReviewer(persistence, persistence.flashcard_repo)

    result = await handler(ReviewFlashcard(user_id=user_id, flashcard_id=card.id, grade="good"))

    assert result.interval_days == 3
    assert result.review_count == 1
    assert persistence.flashcard_repo.reviews[0].grade == "good"
    assert persistence.committed is True


async def test_review_flashcard_hides_foreign_cards() -> None:
    card = _flashcard(user_id=uuid.uuid4())
    persistence = _ReviewPersistence([], [])
    persistence.flashcard_repo.cards[card.id] = card
    handler = FlashcardReviewer(persistence, persistence.flashcard_repo)

    with pytest.raises(ResourceNotFoundException):
        await handler(ReviewFlashcard(user_id=uuid.uuid4(), flashcard_id=card.id, grade="good"))


def test_schedule_next_review_handles_grades() -> None:
    assert next_review_schedule(grade=ReviewGrade.from_raw("again"), interval_days=10, ease_factor=2.5).interval_days == 1
    assert next_review_schedule(grade=ReviewGrade.from_raw("hard"), interval_days=5, ease_factor=2.5).interval_days == 6
    assert next_review_schedule(grade=ReviewGrade.from_raw("good"), interval_days=2, ease_factor=2.5).interval_days == 5
    assert next_review_schedule(grade=ReviewGrade.from_raw("easy"), interval_days=2, ease_factor=2.5).interval_days == 5


class _ReviewPersistence:
    def __init__(self, documents: list[DocumentModel], chunks: list[ChunkModel]) -> None:
        self.document_repo = _DocumentRepository(documents)
        self.chunk_repo = _ChunkRepository(chunks)
        self.flashcard_repo = _FlashcardRepository()
        self.topic_repo = _TopicRepository()
        self.committed = False
        self.service = ReviewService(
            session=self,
            document_repo=self.document_repo,
            chunk_repo=self.chunk_repo,
            topic_repo=self.topic_repo,
            flashcard_repo=self.flashcard_repo,
            quiz_repo=cast("object", _UnusedRepository()),
            learning_path_repo=cast("object", _UnusedRepository()),
        )

    async def flush(self) -> None:
        self.committed = True


def _flashcard_generator(persistence: _ReviewPersistence) -> FlashcardGenerator:
    return FlashcardGenerator(
        persistence,
        persistence.document_repo,
        persistence.chunk_repo,
        persistence.topic_repo,
        persistence.flashcard_repo,
    )


class _UnusedRepository:
    pass


class _DocumentRepository:
    def __init__(self, documents: list[DocumentModel]) -> None:
        self.documents = {document.id: document for document in documents}

    async def get_by_id(self, document_id: uuid.UUID) -> DocumentModel | None:
        return self.documents.get(document_id)

    async def get_by_user_id(
        self,
        user_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
        document_type: DocumentType | None = None,
        collection_id: uuid.UUID | None = None,
        status: DocumentStatus | None = None,
    ) -> list[DocumentModel]:
        return [document for document in self.documents.values() if document.user_id == user_id and (status is None or document.status == status)][:limit]


class _ChunkRepository:
    def __init__(self, chunks: list[ChunkModel]) -> None:
        self.chunks = chunks

    async def get_by_document_id(self, document_id: uuid.UUID) -> list[ChunkModel]:
        return [chunk for chunk in self.chunks if chunk.document_id == document_id]


class _FlashcardRepository:
    def __init__(self) -> None:
        self.cards: dict[uuid.UUID, FlashcardRecord] = {}
        self.reviews: list[FlashcardReviewRecord] = []

    async def create_many(self, records: list[FlashcardRecord]) -> list[FlashcardRecord]:
        for record in records:
            self.cards[record.id] = record
        return records

    async def list_due(self, *, user_id: uuid.UUID, now: datetime, limit: int = 20) -> list[FlashcardRecord]:
        return [card for card in self.cards.values() if card.user_id == user_id and card.due_at <= now][:limit]

    async def count_due(self, *, user_id: uuid.UUID, now: datetime) -> int:
        return len(await self.list_due(user_id=user_id, now=now, limit=100))

    async def get_by_id(self, flashcard_id: uuid.UUID) -> FlashcardRecord | None:
        return self.cards.get(flashcard_id)

    async def update_schedule(
        self,
        *,
        flashcard_id: uuid.UUID,
        due_at: datetime,
        interval_days: int,
        ease_factor: float,
        review_count: int,
    ) -> FlashcardRecord:
        record = self.cards[flashcard_id]
        updated = replace(
            record,
            due_at=due_at,
            interval_days=interval_days,
            ease_factor=ease_factor,
            review_count=review_count,
        )
        self.cards[flashcard_id] = updated
        return updated

    async def create_review(self, record: FlashcardReviewRecord) -> None:
        self.reviews.append(record)

    async def existing_questions_for_document(self, *, user_id: uuid.UUID, document_id: uuid.UUID) -> set[str]:
        return {
            card.question.strip().lower()
            for card in self.cards.values()
            if card.user_id == user_id and card.source_document_id == document_id
        }


class _TopicRepository:
    def __init__(self) -> None:
        self.detail: TopicDetailRecord | None = None

    async def get_detail_by_name(
        self,
        user_id: uuid.UUID,
        *,
        name: str,
        document_limit: int,
    ) -> TopicDetailRecord | None:
        return self.detail


def _document(
    *,
    user_id: uuid.UUID,
    suggested_questions: list[str],
    summary: str | None,
    collection_id: uuid.UUID | None = None,
) -> DocumentModel:
    return DocumentModel(
        id=uuid.uuid4(),
        user_id=user_id,
        collection_id=collection_id,
        title="Asyncio notes",
        type=DocumentType.TEXT,
        status=DocumentStatus.READY,
        source_url=None,
        file_path=None,
        file_size_bytes=None,
        raw_content="Asyncio content",
        summary=summary,
        word_count=20,
        language="en",
        doc_embedding=None,
        is_duplicate=False,
        duplicate_of_id=None,
        created_at=datetime.now(UTC),
        updated_at=None,
        suggested_questions=suggested_questions,
    )


def _chunk(document_id: uuid.UUID, content: str) -> ChunkModel:
    return ChunkModel.create(
        id=uuid.uuid4(),
        document_id=document_id,
        content=content,
        embedding=[0.1] * ChunkModel.EMBEDDING_DIMENSIONS,
        chunk_index=0,
    )


def _flashcard(
    *,
    user_id: uuid.UUID,
    interval_days: int = 0,
    ease_factor: float = 2.5,
) -> FlashcardRecord:
    now = datetime.now(UTC)
    return FlashcardRecord(
        id=uuid.uuid4(),
        user_id=user_id,
        scope_type="document",
        collection_id=None,
        topic=None,
        source_document_id=uuid.uuid4(),
        source_chunk_id=None,
        question="What is asyncio?",
        answer="Asyncio runs cooperative I/O.",
        citation_metadata={},
        due_at=now,
        interval_days=interval_days,
        ease_factor=ease_factor,
        review_count=0,
        source_title="Asyncio notes",
        created_at=now,
        updated_at=None,
    )
