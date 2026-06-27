from __future__ import annotations

from typing import TYPE_CHECKING

from src.documents.chunk_repository import ChunkRepository
from src.documents.document_repository import DocumentRepository
from src.review.flashcards import FlashcardGenerator, FlashcardReviewer, list_due_flashcards
from src.review.learning_paths import (
    LearningPathGenerator,
    LearningPathRegenerator,
    LearningPathStepUpdater,
    list_learning_paths,
)
from src.review.quizzes import (
    QuizGenerator,
    QuizSubmitter,
    list_quiz_attempts,
    list_quiz_history,
    list_quiz_weak_areas,
)
from src.review.repository import FlashcardRepository, LearningPathRepository, QuizRepository
from src.topics.repository import TopicRepository

if TYPE_CHECKING:
    from uuid import UUID

    from src.postgres import AsyncSession
    from src.review.schemas import (
        FlashcardListResponse,
        FlashcardResponse,
        GenerateFlashcardsRequest,
        GenerateFlashcardsResponse,
        GenerateLearningPathRequest,
        GenerateQuizRequest,
        LearningPathListResponse,
        LearningPathResponse,
        QuizAttemptListResponse,
        QuizAttemptResponse,
        QuizListResponse,
        QuizResponse,
        QuizWeakAreaListResponse,
        ReviewFlashcardRequest,
        SubmitQuizRequest,
        UpdateLearningPathStepRequest,
    )


class ReviewService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.document_repo = DocumentRepository.from_session(session)
        self.chunk_repo = ChunkRepository.from_session(session)
        self.topic_repo = TopicRepository.from_session(session)
        self.flashcard_repo = FlashcardRepository.from_session(session)
        self.quiz_repo = QuizRepository.from_session(session)
        self.learning_path_repo = LearningPathRepository.from_session(session)

    async def generate_flashcards(self, user_id: UUID, body: GenerateFlashcardsRequest) -> GenerateFlashcardsResponse:
        return await FlashcardGenerator(
            self.session,
            self.document_repo,
            self.chunk_repo,
            self.topic_repo,
            self.flashcard_repo,
        )(
            user_id=user_id,
            document_id=body.document_id,
            collection_id=body.collection_id,
            topic=body.topic,
            limit=body.limit,
        )

    async def list_due_flashcards(self, user_id: UUID, *, limit: int) -> FlashcardListResponse:
        return await list_due_flashcards(self.flashcard_repo, user_id=user_id, limit=limit)

    async def review_flashcard(
        self,
        user_id: UUID,
        flashcard_id: UUID,
        body: ReviewFlashcardRequest,
    ) -> FlashcardResponse:
        return await FlashcardReviewer(self.session, self.flashcard_repo)(
            user_id=user_id,
            flashcard_id=flashcard_id,
            grade=body.grade,
        )

    async def generate_quiz(self, user_id: UUID, body: GenerateQuizRequest) -> QuizResponse:
        return await QuizGenerator(
            self.session,
            self.document_repo,
            self.chunk_repo,
            self.topic_repo,
            self.quiz_repo,
        )(
            user_id=user_id,
            document_id=body.document_id,
            collection_id=body.collection_id,
            topic=body.topic,
            limit=body.limit,
        )

    async def list_quiz_history(self, user_id: UUID, *, limit: int) -> QuizListResponse:
        return await list_quiz_history(self.quiz_repo, user_id=user_id, limit=limit)

    async def list_quiz_attempts(self, user_id: UUID, *, limit: int) -> QuizAttemptListResponse:
        return await list_quiz_attempts(self.quiz_repo, user_id=user_id, limit=limit)

    async def list_quiz_weak_areas(self, user_id: UUID, *, limit: int) -> QuizWeakAreaListResponse:
        return await list_quiz_weak_areas(self.quiz_repo, user_id=user_id, limit=limit)

    async def submit_quiz(self, user_id: UUID, quiz_id: UUID, body: SubmitQuizRequest) -> QuizAttemptResponse:
        return await QuizSubmitter(self.session, self.quiz_repo)(
            user_id=user_id,
            quiz_id=quiz_id,
            answers=[answer.model_dump() for answer in body.answers],
        )

    async def generate_learning_path(self, user_id: UUID, body: GenerateLearningPathRequest) -> LearningPathResponse:
        return await LearningPathGenerator(
            self.session,
            self.document_repo,
            self.topic_repo,
            self.learning_path_repo,
        )(
            user_id=user_id,
            document_id=body.document_id,
            collection_id=body.collection_id,
            topic=body.topic,
            limit=body.limit,
        )

    async def list_learning_paths(self, user_id: UUID, *, limit: int) -> LearningPathListResponse:
        return await list_learning_paths(self.learning_path_repo, user_id=user_id, limit=limit)

    async def update_learning_path_step(
        self,
        user_id: UUID,
        path_id: UUID,
        step_id: str,
        body: UpdateLearningPathStepRequest,
    ) -> LearningPathResponse:
        return await LearningPathStepUpdater(self.session, self.learning_path_repo)(
            user_id=user_id,
            path_id=path_id,
            step_id=step_id,
            status=body.status,
        )

    async def regenerate_learning_path(self, user_id: UUID, path_id: UUID, *, limit: int) -> LearningPathResponse:
        generator = LearningPathGenerator(
            self.session,
            self.document_repo,
            self.topic_repo,
            self.learning_path_repo,
        )
        return await LearningPathRegenerator(generator, self.learning_path_repo)(
            user_id=user_id,
            path_id=path_id,
            limit=limit,
        )


__all__ = ["ReviewService"]
