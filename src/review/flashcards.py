from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from src.documents.status import DocumentStatus
from src.kit.exceptions import DocumentAccessDeniedException, DocumentNotFoundException, ResourceNotFoundException
from src.review.grade import ReviewGrade
from src.review.helpers import (
    build_flashcards_for_document,
    flashcard_response,
    review_scope_collection_id,
    review_scope_type,
)
from src.review.repository import FlashcardReviewRecord
from src.review.schedule import next_review_schedule
from src.review.schemas import FlashcardListResponse, FlashcardResponse, GenerateFlashcardsResponse

if TYPE_CHECKING:
    from uuid import UUID

    from src.documents.chunk_repository import ChunkRepository
    from src.documents.document_repository import DocumentRepository
    from src.models.document import DocumentModel
    from src.postgres import AsyncSession
    from src.review.repository import FlashcardRecord, FlashcardRepository
    from src.topics.repository import TopicRepository


class FlashcardGenerator:
    def __init__(
        self,
        session: AsyncSession,
        document_repo: DocumentRepository,
        chunk_repo: ChunkRepository,
        topic_repo: TopicRepository,
        flashcard_repo: FlashcardRepository,
    ) -> None:
        self._session = session
        self._document_repo = document_repo
        self._chunk_repo = chunk_repo
        self._topic_repo = topic_repo
        self._flashcard_repo = flashcard_repo

    async def __call__(
        self,
        *,
        user_id: UUID,
        document_id: UUID | None = None,
        collection_id: UUID | None = None,
        topic: str | None = None,
        limit: int = 5,
    ) -> GenerateFlashcardsResponse:
        now = datetime.now(UTC)
        documents = await self._load_documents(
            user_id=user_id,
            document_id=document_id,
            collection_id=collection_id,
            topic=topic,
            limit=limit,
        )
        records: list[FlashcardRecord] = []
        remaining = max(1, min(limit, 20))
        for document in documents:
            existing = await self._flashcard_repo.existing_questions_for_document(
                user_id=user_id,
                document_id=document.id,
            )
            chunks = await self._chunk_repo.get_by_document_id(document.id)
            for record in build_flashcards_for_document(
                document,
                chunks,
                now=now,
                existing_questions=existing,
                scope_type=review_scope_type(document_id=document_id, collection_id=collection_id, topic=topic),
                scope_collection_id=review_scope_collection_id(
                    document_id=document_id,
                    collection_id=collection_id,
                    document=document,
                ),
                scope_topic=topic.strip() if topic and topic.strip() else None,
            ):
                records.append(record)
                remaining -= 1
                if remaining <= 0:
                    break
            if remaining <= 0:
                break
        created = await self._flashcard_repo.create_many(records) if records else []
        await self._session.flush()

        return GenerateFlashcardsResponse(
            items=[flashcard_response(record) for record in created],
            created_count=len(created),
        )

    async def _load_documents(
        self,
        *,
        user_id: UUID,
        document_id: UUID | None,
        collection_id: UUID | None,
        topic: str | None,
        limit: int,
    ) -> list[DocumentModel]:
        if document_id is not None:
            document = await self._document_repo.get_by_id(document_id)
            if document is None:
                raise DocumentNotFoundException("document not found")
            if document.user_id != user_id:
                raise DocumentAccessDeniedException("document access denied")
            if document.status != DocumentStatus.READY:
                return []
            return [document]
        if topic:
            detail = await self._topic_repo.get_detail_by_name(
                user_id,
                name=topic,
                document_limit=max(1, min(limit * 3, 60)),
            )
            if detail is None:
                return []
            documents: list[DocumentModel] = []
            for topic_document in detail.documents:
                document = await self._document_repo.get_by_id(topic_document.id)
                if document and document.user_id == user_id and document.status == DocumentStatus.READY:
                    documents.append(document)
            return documents
        return await self._document_repo.get_by_user_id(
            user_id,
            limit=max(1, min(limit * 3, 60)),
            collection_id=collection_id,
            status=DocumentStatus.READY,
        )


async def list_due_flashcards(
    flashcard_repo: FlashcardRepository,
    *,
    user_id: UUID,
    limit: int = 20,
) -> FlashcardListResponse:
    now = datetime.now(UTC)
    items = await flashcard_repo.list_due(user_id=user_id, now=now, limit=limit)
    total = await flashcard_repo.count_due(user_id=user_id, now=now)
    return FlashcardListResponse(
        items=[flashcard_response(item) for item in items],
        total=total,
        limit=limit,
    )


class FlashcardReviewer:
    def __init__(self, session: AsyncSession, flashcard_repo: FlashcardRepository) -> None:
        self._session = session
        self._flashcard_repo = flashcard_repo

    async def __call__(self, *, user_id: UUID, flashcard_id: UUID, grade: str) -> FlashcardResponse:
        grade_value = ReviewGrade.from_raw(grade)
        now = datetime.now(UTC)
        flashcard = await self._flashcard_repo.get_by_id(flashcard_id)
        if flashcard is None:
            raise ResourceNotFoundException("flashcard not found")
        if flashcard.user_id != user_id:
            raise ResourceNotFoundException("flashcard not found")
        next_schedule = next_review_schedule(
            grade=grade_value,
            interval_days=flashcard.interval_days,
            ease_factor=flashcard.ease_factor,
        )
        reviewed = await self._flashcard_repo.update_schedule(
            flashcard_id=flashcard.id,
            due_at=now + timedelta(days=next_schedule.interval_days),
            interval_days=next_schedule.interval_days,
            ease_factor=next_schedule.ease_factor,
            review_count=flashcard.review_count + 1,
        )
        await self._flashcard_repo.create_review(
            FlashcardReviewRecord(
                id=uuid.uuid4(),
                flashcard_id=flashcard.id,
                user_id=user_id,
                grade=grade_value.value,
                previous_interval_days=flashcard.interval_days,
                next_interval_days=next_schedule.interval_days,
                previous_ease_factor=flashcard.ease_factor,
                next_ease_factor=next_schedule.ease_factor,
                reviewed_at=now,
            )
        )
        await self._session.flush()
        return flashcard_response(replace(reviewed, source_title=flashcard.source_title))


__all__ = ["FlashcardGenerator", "FlashcardReviewer", "list_due_flashcards"]
