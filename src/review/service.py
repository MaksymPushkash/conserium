from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from src.documents.status import DocumentStatus
from src.kit.exceptions import (
    DocumentAccessDeniedException,
    DocumentNotFoundException,
    ResourceNotFoundException,
)
from src.review.grade import ReviewGrade
from src.review.helpers import (
    build_flashcards_for_document,
    build_learning_steps,
    build_quiz_questions_for_document,
    flashcard_scope_collection_id,
    flashcard_scope_type,
    flashcard_to_dto,
    learning_path_scope_collection_id,
    learning_path_scope_type,
    learning_path_title,
    learning_path_to_dto,
    normalize_step_status,
    quiz_scope_collection_id,
    quiz_scope_type,
    quiz_title,
    quiz_to_dto,
    score_quiz_answers,
    to_flashcard_list_response,
    to_flashcard_response,
    to_generate_flashcards_response,
    to_learning_path_list_response,
    to_learning_path_response,
    to_quiz_attempt_list_response,
    to_quiz_attempt_response,
    to_quiz_list_response,
    to_quiz_response,
    to_quiz_weak_area_list_response,
    update_step_status,
)
from src.review.repository import (
    FlashcardReviewRecord,
    LearningPathRecord,
    QuizAttemptRecord,
    QuizRecord,
)
from src.review.schedule import next_review_schedule
from src.review.schemas import (
    FlashcardListResponse,
    FlashcardResponse,
    GenerateFlashcardsDTO,
    GenerateFlashcardsRequest,
    GenerateFlashcardsResponse,
    GenerateLearningPathDTO,
    GenerateLearningPathRequest,
    GenerateQuizDTO,
    GenerateQuizRequest,
    LearningPathListResponse,
    LearningPathResponse,
    QuizAttemptListResponse,
    QuizAttemptResponse,
    QuizListResponse,
    QuizResponse,
    QuizWeakAreaListResponse,
    QuizWeakAreaResponse,
    RegenerateLearningPathDTO,
    ReviewFlashcardDTO,
    ReviewFlashcardRequest,
    SubmitQuizDTO,
    SubmitQuizRequest,
    UpdateLearningPathStepDTO,
    UpdateLearningPathStepRequest,
)

if TYPE_CHECKING:
    from uuid import UUID

    from src.documents.chunk_repository import ChunkRepository as ChunkStore
    from src.documents.document_repository import DocumentRepository as DocumentStore
    from src.models.document import DocumentModel
    from src.postgres import AsyncSession
    from src.review.repository import FlashcardRecord
    from src.review.repository import FlashcardRepository as FlashcardStore
    from src.review.repository import LearningPathRepository as LearningPathStore
    from src.review.repository import QuizRepository as QuizStore
    from src.topics.repository import TopicRepository


class ReviewService:
    def __init__(
        self,
        session: AsyncSession,
        document_repo: DocumentStore,
        chunk_repo: ChunkStore,
        topic_repo: TopicRepository,
        flashcard_repo: FlashcardStore,
        quiz_repo: QuizStore,
        learning_path_repo: LearningPathStore,
    ) -> None:
        self.session = session
        self.document_repo = document_repo
        self.chunk_repo = chunk_repo
        self.topic_repo = topic_repo
        self.flashcard_repo = flashcard_repo
        self.quiz_repo = quiz_repo
        self.learning_path_repo = learning_path_repo

    async def generate_flashcards(self, user_id: UUID, body: GenerateFlashcardsRequest) -> GenerateFlashcardsResponse:
        result = await FlashcardGenerator(
            self.session,
            self.document_repo,
            self.chunk_repo,
            self.topic_repo,
            self.flashcard_repo,
        )(
            GenerateFlashcardsDTO(
                user_id=user_id,
                document_id=body.document_id,
                collection_id=body.collection_id,
                topic=body.topic,
                limit=body.limit,
            )
        )
        return to_generate_flashcards_response(result)

    async def list_due_flashcards(self, user_id: UUID, *, limit: int) -> FlashcardListResponse:
        result = await list_due_flashcards(self.flashcard_repo, user_id=user_id, limit=limit)
        return to_flashcard_list_response(result)

    async def review_flashcard(
        self,
        user_id: UUID,
        flashcard_id: UUID,
        body: ReviewFlashcardRequest,
    ) -> FlashcardResponse:
        result = await FlashcardReviewer(self.session, self.flashcard_repo)(
            ReviewFlashcardDTO(user_id=user_id, flashcard_id=flashcard_id, grade=body.grade)
        )
        return to_flashcard_response(result)

    async def generate_learning_path(self, user_id: UUID, body: GenerateLearningPathRequest) -> LearningPathResponse:
        result = await LearningPathGenerator(
            self.session,
            self.document_repo,
            self.topic_repo,
            self.learning_path_repo,
        )(
            GenerateLearningPathDTO(
                user_id=user_id,
                document_id=body.document_id,
                collection_id=body.collection_id,
                topic=body.topic,
                limit=body.limit,
            )
        )
        return to_learning_path_response(result)

    async def list_learning_paths(self, user_id: UUID, *, limit: int) -> LearningPathListResponse:
        result = await list_learning_paths(self.learning_path_repo, user_id=user_id, limit=limit)
        return to_learning_path_list_response(result)

    async def update_learning_path_step(
        self,
        user_id: UUID,
        path_id: UUID,
        step_id: str,
        body: UpdateLearningPathStepRequest,
    ) -> LearningPathResponse:
        result = await LearningPathStepUpdater(self.session, self.learning_path_repo)(
            UpdateLearningPathStepDTO(user_id=user_id, path_id=path_id, step_id=step_id, status=body.status)
        )
        return to_learning_path_response(result)

    async def regenerate_learning_path(self, user_id: UUID, path_id: UUID, *, limit: int) -> LearningPathResponse:
        generator = LearningPathGenerator(
            self.session,
            self.document_repo,
            self.topic_repo,
            self.learning_path_repo,
        )
        result = await LearningPathRegenerator(generator, self.learning_path_repo)(
            RegenerateLearningPathDTO(user_id=user_id, path_id=path_id, limit=limit)
        )
        return to_learning_path_response(result)

    async def generate_quiz(self, user_id: UUID, body: GenerateQuizRequest) -> QuizResponse:
        result = await QuizGenerator(
            self.session,
            self.document_repo,
            self.chunk_repo,
            self.topic_repo,
            self.quiz_repo,
        )(
            GenerateQuizDTO(
                user_id=user_id,
                document_id=body.document_id,
                collection_id=body.collection_id,
                topic=body.topic,
                limit=body.limit,
            )
        )
        return to_quiz_response(result)

    async def list_quiz_history(self, user_id: UUID, *, limit: int) -> QuizListResponse:
        result = await list_quiz_history(self.quiz_repo, user_id=user_id, limit=limit)
        return to_quiz_list_response(result)

    async def list_quiz_attempts(self, user_id: UUID, *, limit: int) -> QuizAttemptListResponse:
        result = await list_quiz_attempts(self.quiz_repo, user_id=user_id, limit=limit)
        return to_quiz_attempt_list_response(result)

    async def list_quiz_weak_areas(self, user_id: UUID, *, limit: int) -> QuizWeakAreaListResponse:
        result = await list_quiz_weak_areas(self.quiz_repo, user_id=user_id, limit=limit)
        return to_quiz_weak_area_list_response(result)

    async def submit_quiz(self, user_id: UUID, quiz_id: UUID, body: SubmitQuizRequest) -> QuizAttemptResponse:
        result = await QuizSubmitter(self.session, self.quiz_repo)(
            SubmitQuizDTO(user_id=user_id, quiz_id=quiz_id, answers=body.answers)
        )
        return to_quiz_attempt_response(result)


class FlashcardGenerator:
    def __init__(
        self,
        session: AsyncSession,
        document_repo: DocumentStore,
        chunk_repo: ChunkStore,
        topic_repo: TopicRepository,
        flashcard_repo: FlashcardStore,
    ) -> None:
        self._session = session
        self._document_repo = document_repo
        self._chunk_repo = chunk_repo
        self._topic_repo = topic_repo
        self._flashcard_repo = flashcard_repo

    async def __call__(self, dto: GenerateFlashcardsDTO) -> GenerateFlashcardsResponse:
        now = datetime.now(UTC)
        documents = await self._load_documents(dto)
        records: list[FlashcardRecord] = []
        remaining = max(1, min(dto.limit, 20))
        for document in documents:
            existing = await self._flashcard_repo.existing_questions_for_document(
                user_id=dto.user_id,
                document_id=document.id,
            )
            chunks = await self._chunk_repo.get_by_document_id(document.id)
            for record in build_flashcards_for_document(
                document,
                chunks,
                now=now,
                existing_questions=existing,
                scope_type=flashcard_scope_type(dto),
                scope_collection_id=flashcard_scope_collection_id(dto, document),
                scope_topic=dto.topic.strip() if dto.topic and dto.topic.strip() else None,
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
            items=[flashcard_to_dto(record) for record in created],
            created_count=len(created),
        )

    async def _load_documents(self, dto: GenerateFlashcardsDTO) -> list[DocumentModel]:
        if dto.document_id is not None:
            document = await self._document_repo.get_by_id(dto.document_id)
            if document is None:
                raise DocumentNotFoundException("document not found")
            if document.user_id != dto.user_id:
                raise DocumentAccessDeniedException("document access denied")
            if document.status != DocumentStatus.READY:
                return []
            return [document]
        if dto.topic:
            detail = await self._topic_repo.get_detail_by_name(
                dto.user_id,
                name=dto.topic,
                document_limit=max(1, min(dto.limit * 3, 60)),
            )
            if detail is None:
                return []
            documents: list[DocumentModel] = []
            for topic_document in detail.documents:
                document = await self._document_repo.get_by_id(topic_document.id)
                if document and document.user_id == dto.user_id and document.status == DocumentStatus.READY:
                    documents.append(document)
            return documents
        return await self._document_repo.get_by_user_id(
            dto.user_id,
            limit=max(1, min(dto.limit * 3, 60)),
            collection_id=dto.collection_id,
            status=DocumentStatus.READY,
        )


async def list_due_flashcards(
    flashcard_repo: FlashcardStore,
    *,
    user_id: UUID,
    limit: int = 20,
) -> FlashcardListResponse:
    now = datetime.now(UTC)
    items = await flashcard_repo.list_due(user_id=user_id, now=now, limit=limit)
    total = await flashcard_repo.count_due(user_id=user_id, now=now)
    return FlashcardListResponse(
        items=[flashcard_to_dto(item) for item in items],
        total=total,
        limit=limit,
    )


class FlashcardReviewer:
    def __init__(self, session: AsyncSession, flashcard_repo: FlashcardStore) -> None:
        self._session = session
        self._flashcard_repo = flashcard_repo

    async def __call__(self, dto: ReviewFlashcardDTO) -> FlashcardResponse:
        grade = ReviewGrade.from_raw(dto.grade)
        now = datetime.now(UTC)
        flashcard = await self._flashcard_repo.get_by_id(dto.flashcard_id)
        if flashcard is None:
            raise ResourceNotFoundException("flashcard not found")
        if flashcard.user_id != dto.user_id:
            raise ResourceNotFoundException("flashcard not found")
        next_schedule = next_review_schedule(
            grade=grade,
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
                user_id=dto.user_id,
                grade=grade.value,
                previous_interval_days=flashcard.interval_days,
                next_interval_days=next_schedule.interval_days,
                previous_ease_factor=flashcard.ease_factor,
                next_ease_factor=next_schedule.ease_factor,
                reviewed_at=now,
            )
        )
        await self._session.flush()
        return flashcard_to_dto(replace(reviewed, source_title=flashcard.source_title))


class QuizGenerator:
    def __init__(
        self,
        session: AsyncSession,
        document_repo: DocumentStore,
        chunk_repo: ChunkStore,
        topic_repo: TopicRepository,
        quiz_repo: QuizStore,
    ) -> None:
        self._session = session
        self._document_repo = document_repo
        self._chunk_repo = chunk_repo
        self._topic_repo = topic_repo
        self._quiz_repo = quiz_repo

    async def __call__(self, dto: GenerateQuizDTO) -> QuizResponse:
        now = datetime.now(UTC)
        documents = await self._load_documents(dto)
        if not documents:
            raise DocumentNotFoundException("no ready documents found for quiz")
        questions: list[dict[str, object]] = []
        source_document = documents[0]
        for document in documents:
            chunks = await self._chunk_repo.get_by_document_id(document.id)
            questions.extend(build_quiz_questions_for_document(document, chunks, remaining=max(0, dto.limit - len(questions))))
            if len(questions) >= dto.limit:
                break
        record = QuizRecord(
            id=uuid.uuid4(),
            user_id=dto.user_id,
            scope_type=quiz_scope_type(dto),
            collection_id=quiz_scope_collection_id(dto, source_document),
            topic=dto.topic.strip() if dto.topic and dto.topic.strip() else None,
            source_document_id=source_document.id,
            title=quiz_title(dto, source_document),
            questions=questions[: max(1, min(dto.limit, 20))],
            source_title=source_document.title,
            created_at=now,
            updated_at=None,
        )
        created = await self._quiz_repo.create(record)
        await self._session.flush()
        return quiz_to_dto(created)

    async def _load_documents(self, dto: GenerateQuizDTO) -> list[DocumentModel]:
        if dto.document_id is not None:
            document = await self._document_repo.get_by_id(dto.document_id)
            if document is None:
                raise DocumentNotFoundException("document not found")
            if document.user_id != dto.user_id:
                raise DocumentAccessDeniedException("document access denied")
            if document.status != DocumentStatus.READY:
                return []
            return [document]
        if dto.topic:
            detail = await self._topic_repo.get_detail_by_name(
                dto.user_id,
                name=dto.topic,
                document_limit=max(1, min(dto.limit * 3, 60)),
            )
            if detail is None:
                return []
            documents: list[DocumentModel] = []
            for topic_document in detail.documents:
                document = await self._document_repo.get_by_id(topic_document.id)
                if document and document.user_id == dto.user_id and document.status == DocumentStatus.READY:
                    documents.append(document)
            return documents
        return await self._document_repo.get_by_user_id(
            dto.user_id,
            limit=max(1, min(dto.limit * 3, 60)),
            collection_id=dto.collection_id,
            status=DocumentStatus.READY,
        )


async def list_quiz_history(quiz_repo: QuizStore, *, user_id: UUID, limit: int = 20) -> QuizListResponse:
    items = await quiz_repo.list_by_user(user_id=user_id, limit=limit)
    return QuizListResponse(items=[quiz_to_dto(item) for item in items], total=len(items), limit=limit)


async def list_quiz_attempts(quiz_repo: QuizStore, *, user_id: UUID, limit: int = 20) -> QuizAttemptListResponse:
    items = await quiz_repo.list_attempts_by_user(user_id=user_id, limit=limit)
    return QuizAttemptListResponse(
        items=[
            QuizAttemptResponse(
                id=item.id,
                quiz_id=item.quiz_id,
                user_id=item.user_id,
                answers=item.answers,
                score=item.score,
                total=item.total,
                weak_areas=item.weak_areas,
                created_at=item.created_at,
                quiz_title=item.quiz_title,
            )
            for item in items
        ],
        total=len(items),
        limit=limit,
    )


async def list_quiz_weak_areas(quiz_repo: QuizStore, *, user_id: UUID, limit: int = 10) -> QuizWeakAreaListResponse:
    items = await quiz_repo.list_weak_areas(user_id=user_id, limit=limit)
    return QuizWeakAreaListResponse(
        items=[QuizWeakAreaResponse(name=item.name, count=item.count, last_seen_at=item.last_seen_at) for item in items],
        total=len(items),
        limit=limit,
    )


class QuizSubmitter:
    def __init__(self, session: AsyncSession, quiz_repo: QuizStore) -> None:
        self._session = session
        self._quiz_repo = quiz_repo

    async def __call__(self, dto: SubmitQuizDTO) -> QuizAttemptResponse:
        quiz = await self._quiz_repo.get_by_id(dto.quiz_id)
        if quiz is None:
            raise DocumentNotFoundException("quiz not found")
        if quiz.user_id != dto.user_id:
            raise DocumentAccessDeniedException("quiz access denied")
        score, total, answers, weak_areas = score_quiz_answers(quiz.questions, dto.answers)
        record = QuizAttemptRecord(
            id=uuid.uuid4(),
            quiz_id=quiz.id,
            user_id=dto.user_id,
            answers=answers,
            score=score,
            total=total,
            weak_areas=weak_areas,
            created_at=datetime.now(UTC),
        )
        created = await self._quiz_repo.create_attempt(record)
        await self._session.flush()
        return QuizAttemptResponse(
            id=created.id,
            quiz_id=created.quiz_id,
            user_id=created.user_id,
            answers=created.answers,
            score=created.score,
            total=created.total,
            weak_areas=created.weak_areas,
            created_at=created.created_at,
        )


class LearningPathGenerator:
    def __init__(
        self,
        session: AsyncSession,
        document_repo: DocumentStore,
        topic_repo: TopicRepository,
        learning_path_repo: LearningPathStore,
    ) -> None:
        self._session = session
        self._document_repo = document_repo
        self._topic_repo = topic_repo
        self._learning_path_repo = learning_path_repo

    async def __call__(self, dto: GenerateLearningPathDTO) -> LearningPathResponse:
        documents = await self._load_documents(dto)
        if not documents:
            raise DocumentNotFoundException("no ready documents found for learning path")
        source_document = documents[0]
        record = LearningPathRecord(
            id=uuid.uuid4(),
            user_id=dto.user_id,
            scope_type=learning_path_scope_type(dto),
            collection_id=learning_path_scope_collection_id(dto, source_document),
            topic=dto.topic.strip() if dto.topic and dto.topic.strip() else None,
            source_document_id=source_document.id,
            title=learning_path_title(dto, source_document),
            steps=build_learning_steps(documents, limit=dto.limit),
            created_at=datetime.now(UTC),
            updated_at=None,
        )
        created = await self._learning_path_repo.create(record)
        await self._session.flush()
        return learning_path_to_dto(created)

    async def _load_documents(self, dto: GenerateLearningPathDTO) -> list[DocumentModel]:
        if dto.document_id is not None:
            document = await self._document_repo.get_by_id(dto.document_id)
            if document is None:
                raise DocumentNotFoundException("document not found")
            if document.user_id != dto.user_id:
                raise DocumentAccessDeniedException("document access denied")
            if document.status != DocumentStatus.READY:
                return []
            return [document]
        if dto.topic:
            detail = await self._topic_repo.get_detail_by_name(
                dto.user_id,
                name=dto.topic,
                document_limit=max(1, min(dto.limit * 3, 60)),
            )
            if detail is None:
                return []
            documents: list[DocumentModel] = []
            for topic_document in detail.documents:
                document = await self._document_repo.get_by_id(topic_document.id)
                if document and document.user_id == dto.user_id and document.status == DocumentStatus.READY:
                    documents.append(document)
            return documents
        return await self._document_repo.get_by_user_id(
            dto.user_id,
            limit=max(1, min(dto.limit * 3, 60)),
            collection_id=dto.collection_id,
            status=DocumentStatus.READY,
        )


class LearningPathStepUpdater:
    def __init__(self, session: AsyncSession, learning_path_repo: LearningPathStore) -> None:
        self._session = session
        self._learning_path_repo = learning_path_repo

    async def __call__(self, dto: UpdateLearningPathStepDTO) -> LearningPathResponse:
        status = normalize_step_status(dto.status)
        record = await self._learning_path_repo.get_by_id(dto.path_id)
        if record is None or record.user_id != dto.user_id:
            raise ResourceNotFoundException("learning path not found")
        steps = update_step_status(record.steps, step_id=dto.step_id, status=status)
        updated = await self._learning_path_repo.update_steps(record.id, steps)
        await self._session.flush()
        return learning_path_to_dto(updated)


class LearningPathRegenerator:
    def __init__(
        self,
        generate_learning_path: LearningPathGenerator,
        learning_path_repo: LearningPathStore,
    ) -> None:
        self._generate_learning_path = generate_learning_path
        self._learning_path_repo = learning_path_repo

    async def __call__(self, dto: RegenerateLearningPathDTO) -> LearningPathResponse:
        record = await self._learning_path_repo.get_by_id(dto.path_id)
        if record is None or record.user_id != dto.user_id:
            raise ResourceNotFoundException("learning path not found")
        return await self._generate_learning_path(
            GenerateLearningPathDTO(
                user_id=dto.user_id,
                document_id=record.source_document_id if record.scope_type == "document" else None,
                collection_id=record.collection_id if record.scope_type == "collection" else None,
                topic=record.topic if record.scope_type == "topic" else None,
                limit=dto.limit,
            )
        )


async def list_learning_paths(
    learning_path_repo: LearningPathStore,
    *,
    user_id: UUID,
    limit: int = 10,
) -> LearningPathListResponse:
    items = await learning_path_repo.list_by_user(user_id=user_id, limit=limit)
    return LearningPathListResponse(items=[learning_path_to_dto(item) for item in items], total=len(items), limit=limit)




__all__ = [
    "FlashcardGenerator",
    "FlashcardReviewer",
    "LearningPathGenerator",
    "LearningPathRegenerator",
    "LearningPathStepUpdater",
    "QuizGenerator",
    "QuizSubmitter",
    "ReviewService",
    "list_due_flashcards",
    "list_learning_paths",
    "list_quiz_attempts",
    "list_quiz_history",
    "list_quiz_weak_areas",
    "to_flashcard_list_response",
    "to_flashcard_response",
    "to_generate_flashcards_response",
    "to_learning_path_list_response",
    "to_learning_path_response",
    "to_quiz_attempt_list_response",
    "to_quiz_attempt_response",
    "to_quiz_list_response",
    "to_quiz_response",
    "to_quiz_weak_area_list_response",
]
