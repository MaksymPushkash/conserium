import uuid
from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

import pytest

from src.application.dtos.review_dtos import GenerateFlashcardsDTO, ReviewFlashcardDTO
from src.application.ports.persistence.flashcard_repository import FlashcardRecord, FlashcardReviewRecord
from src.application.ports.persistence.topic_repository import TopicDetailRecord, TopicDocumentRecord, TopicRecord
from src.application.use_cases.review import (
    GenerateFlashcardsUseCase,
    ListDueFlashcardsUseCase,
    ReviewFlashcardUseCase,
)
from src.domain.entities.chunk_entity import ChunkEntity
from src.domain.entities.document_entity import DocumentEntity
from src.domain.exceptions import ResourceNotFoundException
from src.domain.services.review_schedule import next_review_schedule
from src.domain.value_objects.document_status import DocumentStatus
from src.domain.value_objects.document_type import DocumentType
from src.domain.value_objects.review_grade import ReviewGrade

if TYPE_CHECKING:
    from src.application.ports.persistence.unit_of_work import IUnitOfWork


async def test_generate_flashcards_uses_document_summary_and_suggested_questions() -> None:
    user_id = uuid.uuid4()
    document = _document(user_id=user_id, suggested_questions=["What is asyncio?"], summary="Asyncio runs cooperative I/O.")
    uow = _UnitOfWork([document], [_chunk(document.id, "Asyncio uses one event loop.")])
    use_case = GenerateFlashcardsUseCase(cast("IUnitOfWork", uow))

    result = await use_case(GenerateFlashcardsDTO(user_id=user_id, document_id=document.id, limit=3))

    assert result.created_count == 3
    assert result.items[0].question == "What is asyncio?"
    assert result.items[0].answer == "Asyncio runs cooperative I/O."
    assert uow.committed is True


async def test_generate_flashcards_preserves_collection_scope() -> None:
    user_id = uuid.uuid4()
    collection_id = uuid.uuid4()
    document = _document(
        user_id=user_id,
        suggested_questions=["What is collection scope?"],
        summary="Collection scoped cards stay attached.",
        collection_id=collection_id,
    )
    uow = _UnitOfWork([document], [])
    use_case = GenerateFlashcardsUseCase(cast("IUnitOfWork", uow))

    result = await use_case(GenerateFlashcardsDTO(user_id=user_id, collection_id=collection_id, limit=1))

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
    uow = _UnitOfWork([document], [])
    uow.topic_repo.detail = TopicDetailRecord(
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
    use_case = GenerateFlashcardsUseCase(cast("IUnitOfWork", uow))

    result = await use_case(GenerateFlashcardsDTO(user_id=user_id, topic="python", limit=1))

    assert result.items[0].scope_type == "topic"
    assert result.items[0].collection_id is None
    assert result.items[0].topic == "python"


async def test_due_flashcards_return_total() -> None:
    user_id = uuid.uuid4()
    card = _flashcard(user_id=user_id)
    uow = _UnitOfWork([], [])
    uow.flashcard_repo.cards[card.id] = card
    use_case = ListDueFlashcardsUseCase(cast("IUnitOfWork", uow))

    result = await use_case(user_id=user_id, limit=10)

    assert result.total == 1
    assert result.items[0].id == card.id


async def test_review_flashcard_updates_schedule_and_records_review() -> None:
    user_id = uuid.uuid4()
    card = _flashcard(user_id=user_id, interval_days=1, ease_factor=2.5)
    uow = _UnitOfWork([], [])
    uow.flashcard_repo.cards[card.id] = card
    use_case = ReviewFlashcardUseCase(cast("IUnitOfWork", uow))

    result = await use_case(ReviewFlashcardDTO(user_id=user_id, flashcard_id=card.id, grade="good"))

    assert result.interval_days == 3
    assert result.review_count == 1
    assert uow.flashcard_repo.reviews[0].grade == "good"
    assert uow.committed is True


async def test_review_flashcard_hides_foreign_cards() -> None:
    card = _flashcard(user_id=uuid.uuid4())
    uow = _UnitOfWork([], [])
    uow.flashcard_repo.cards[card.id] = card
    use_case = ReviewFlashcardUseCase(cast("IUnitOfWork", uow))

    with pytest.raises(ResourceNotFoundException):
        await use_case(ReviewFlashcardDTO(user_id=uuid.uuid4(), flashcard_id=card.id, grade="good"))


def test_schedule_next_review_handles_grades() -> None:
    assert next_review_schedule(grade=ReviewGrade.from_raw("again"), interval_days=10, ease_factor=2.5).interval_days == 1
    assert next_review_schedule(grade=ReviewGrade.from_raw("hard"), interval_days=5, ease_factor=2.5).interval_days == 6
    assert next_review_schedule(grade=ReviewGrade.from_raw("good"), interval_days=2, ease_factor=2.5).interval_days == 5
    assert next_review_schedule(grade=ReviewGrade.from_raw("easy"), interval_days=2, ease_factor=2.5).interval_days == 5


class _UnitOfWork:
    def __init__(self, documents: list[DocumentEntity], chunks: list[ChunkEntity]) -> None:
        self.document_repo = _DocumentRepository(documents)
        self.chunk_repo = _ChunkRepository(chunks)
        self.flashcard_repo = _FlashcardRepository()
        self.topic_repo = _TopicRepository()
        self.committed = False

    async def __aenter__(self) -> "_UnitOfWork":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True


class _DocumentRepository:
    def __init__(self, documents: list[DocumentEntity]) -> None:
        self.documents = {document.id: document for document in documents}

    async def get_by_id(self, document_id: uuid.UUID) -> DocumentEntity | None:
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
    ) -> list[DocumentEntity]:
        return [document for document in self.documents.values() if document.user_id == user_id and (status is None or document.status == status)][:limit]


class _ChunkRepository:
    def __init__(self, chunks: list[ChunkEntity]) -> None:
        self.chunks = chunks

    async def get_by_document_id(self, document_id: uuid.UUID) -> list[ChunkEntity]:
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
        updated = replace(record, due_at=due_at, interval_days=interval_days, ease_factor=ease_factor, review_count=review_count)
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
) -> DocumentEntity:
    return DocumentEntity(
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


def _chunk(document_id: uuid.UUID, content: str) -> ChunkEntity:
    return ChunkEntity.create(
        id=uuid.uuid4(),
        document_id=document_id,
        content=content,
        embedding=[0.1] * ChunkEntity.EMBEDDING_DIMENSIONS,
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
