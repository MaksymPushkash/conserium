from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.documents.status import DocumentStatus
from src.kit.exceptions import DocumentAccessDeniedException, DocumentNotFoundException
from src.review.helpers import (
    build_quiz_questions_for_document,
    quiz_attempt_response,
    quiz_response,
    quiz_title,
    review_scope_collection_id,
    review_scope_type,
    score_quiz_answers,
)
from src.review.repository import QuizAttemptRecord, QuizRecord
from src.review.schemas import (
    QuizAttemptListResponse,
    QuizListResponse,
    QuizResponse,
    QuizWeakAreaListResponse,
    QuizWeakAreaResponse,
)

if TYPE_CHECKING:
    from uuid import UUID

    from src.documents.chunk_repository import ChunkRepository
    from src.documents.document_repository import DocumentRepository
    from src.models.document import DocumentModel
    from src.postgres import AsyncSession
    from src.review.repository import QuizRepository
    from src.review.schemas import QuizAttemptResponse
    from src.topics.repository import TopicRepository


class QuizGenerator:
    def __init__(
        self,
        session: AsyncSession,
        document_repo: DocumentRepository,
        chunk_repo: ChunkRepository,
        topic_repo: TopicRepository,
        quiz_repo: QuizRepository,
    ) -> None:
        self._session = session
        self._document_repo = document_repo
        self._chunk_repo = chunk_repo
        self._topic_repo = topic_repo
        self._quiz_repo = quiz_repo

    async def __call__(
        self,
        *,
        user_id: UUID,
        document_id: UUID | None = None,
        collection_id: UUID | None = None,
        topic: str | None = None,
        limit: int = 5,
    ) -> QuizResponse:
        now = datetime.now(UTC)
        documents = await self._load_documents(
            user_id=user_id,
            document_id=document_id,
            collection_id=collection_id,
            topic=topic,
            limit=limit,
        )
        if not documents:
            raise DocumentNotFoundException("no ready documents found for quiz")
        questions: list[dict[str, object]] = []
        source_document = documents[0]
        for document in documents:
            chunks = await self._chunk_repo.get_by_document_id(document.id)
            questions.extend(build_quiz_questions_for_document(document, chunks, remaining=max(0, limit - len(questions))))
            if len(questions) >= limit:
                break
        record = QuizRecord(
            id=uuid.uuid4(),
            user_id=user_id,
            scope_type=review_scope_type(document_id=document_id, collection_id=collection_id, topic=topic),
            collection_id=review_scope_collection_id(
                document_id=document_id,
                collection_id=collection_id,
                document=source_document,
            ),
            topic=topic.strip() if topic and topic.strip() else None,
            source_document_id=source_document.id,
            title=quiz_title(topic=topic, collection_id=collection_id, source_document=source_document),
            questions=questions[: max(1, min(limit, 20))],
            source_title=source_document.title,
            created_at=now,
            updated_at=None,
        )
        created = await self._quiz_repo.create(record)
        await self._session.flush()
        return quiz_response(created)

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


async def list_quiz_history(quiz_repo: QuizRepository, *, user_id: UUID, limit: int = 20) -> QuizListResponse:
    items = await quiz_repo.list_by_user(user_id=user_id, limit=limit)
    return QuizListResponse(items=[quiz_response(item) for item in items], total=len(items), limit=limit)


async def list_quiz_attempts(quiz_repo: QuizRepository, *, user_id: UUID, limit: int = 20) -> QuizAttemptListResponse:
    items = await quiz_repo.list_attempts_by_user(user_id=user_id, limit=limit)
    return QuizAttemptListResponse(
        items=[quiz_attempt_response(item) for item in items],
        total=len(items),
        limit=limit,
    )


async def list_quiz_weak_areas(quiz_repo: QuizRepository, *, user_id: UUID, limit: int = 10) -> QuizWeakAreaListResponse:
    items = await quiz_repo.list_weak_areas(user_id=user_id, limit=limit)
    return QuizWeakAreaListResponse(
        items=[QuizWeakAreaResponse(name=item.name, count=item.count, last_seen_at=item.last_seen_at) for item in items],
        total=len(items),
        limit=limit,
    )


class QuizSubmitter:
    def __init__(self, session: AsyncSession, quiz_repo: QuizRepository) -> None:
        self._session = session
        self._quiz_repo = quiz_repo

    async def __call__(self, *, user_id: UUID, quiz_id: UUID, answers: list[dict[str, object]]) -> QuizAttemptResponse:
        quiz = await self._quiz_repo.get_by_id(quiz_id)
        if quiz is None:
            raise DocumentNotFoundException("quiz not found")
        if quiz.user_id != user_id:
            raise DocumentAccessDeniedException("quiz access denied")
        score, total, scored_answers, weak_areas = score_quiz_answers(quiz.questions, answers)
        record = QuizAttemptRecord(
            id=uuid.uuid4(),
            quiz_id=quiz.id,
            user_id=user_id,
            answers=scored_answers,
            score=score,
            total=total,
            weak_areas=weak_areas,
            created_at=datetime.now(UTC),
        )
        created = await self._quiz_repo.create_attempt(record)
        await self._session.flush()
        return quiz_attempt_response(created)


__all__ = [
    "QuizGenerator",
    "QuizSubmitter",
    "list_quiz_attempts",
    "list_quiz_history",
    "list_quiz_weak_areas",
]
