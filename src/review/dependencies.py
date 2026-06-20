from __future__ import annotations

from fastapi import Depends

from src.documents.chunk_repository import ChunkRepository
from src.documents.document_repository import DocumentRepository
from src.postgres import AsyncSession, get_db_session
from src.review.repository import FlashcardRepository, LearningPathRepository, QuizRepository
from src.review.service import ReviewService
from src.topics.repository import TopicRepository


def get_review_service(session: AsyncSession = Depends(get_db_session)) -> ReviewService:
    return ReviewService(
        session=session,
        document_repo=DocumentRepository.from_session(session),
        chunk_repo=ChunkRepository.from_session(session),
        topic_repo=TopicRepository.from_session(session),
        flashcard_repo=FlashcardRepository.from_session(session),
        quiz_repo=QuizRepository.from_session(session),
        learning_path_repo=LearningPathRepository.from_session(session),
    )


__all__ = ["get_review_service"]
