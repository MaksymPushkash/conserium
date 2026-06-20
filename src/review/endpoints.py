from uuid import UUID

from fastapi import Depends, Query, status

from src.auth.auth import CurrentUser
from src.review.dependencies import get_review_service
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
from src.review.service import ReviewService
from src.routing import APIRouter

router = APIRouter(prefix="/review", tags=["review"])


@router.post("/flashcards/generate", response_model=GenerateFlashcardsResponse, status_code=status.HTTP_201_CREATED)
async def generate_flashcards(
    body: GenerateFlashcardsRequest,
    current_user: CurrentUser,
    service: ReviewService = Depends(get_review_service),
) -> GenerateFlashcardsResponse:
    return await service.generate_flashcards(current_user.id, body)


@router.get("/flashcards/due", response_model=FlashcardListResponse)
async def list_due_flashcards(
    current_user: CurrentUser,
    service: ReviewService = Depends(get_review_service),
    limit: int = Query(default=20, ge=1, le=100),
) -> FlashcardListResponse:
    return await service.list_due_flashcards(current_user.id, limit=limit)


@router.post("/flashcards/{flashcard_id}/review", response_model=FlashcardResponse)
async def review_flashcard(
    flashcard_id: UUID,
    body: ReviewFlashcardRequest,
    current_user: CurrentUser,
    service: ReviewService = Depends(get_review_service),
) -> FlashcardResponse:
    return await service.review_flashcard(current_user.id, flashcard_id, body)


@router.post("/learning-paths/generate", response_model=LearningPathResponse, status_code=status.HTTP_201_CREATED)
async def generate_learning_path(
    body: GenerateLearningPathRequest,
    current_user: CurrentUser,
    service: ReviewService = Depends(get_review_service),
) -> LearningPathResponse:
    return await service.generate_learning_path(current_user.id, body)


@router.get("/learning-paths", response_model=LearningPathListResponse)
async def list_learning_paths(
    current_user: CurrentUser,
    service: ReviewService = Depends(get_review_service),
    limit: int = Query(default=10, ge=1, le=50),
) -> LearningPathListResponse:
    return await service.list_learning_paths(current_user.id, limit=limit)


@router.patch("/learning-paths/{path_id}/steps/{step_id}", response_model=LearningPathResponse)
async def update_learning_path_step(
    path_id: UUID,
    step_id: str,
    body: UpdateLearningPathStepRequest,
    current_user: CurrentUser,
    service: ReviewService = Depends(get_review_service),
) -> LearningPathResponse:
    return await service.update_learning_path_step(current_user.id, path_id, step_id, body)


@router.post("/learning-paths/{path_id}/regenerate", response_model=LearningPathResponse, status_code=status.HTTP_201_CREATED)
async def regenerate_learning_path(
    path_id: UUID,
    current_user: CurrentUser,
    service: ReviewService = Depends(get_review_service),
    limit: int = Query(default=6, ge=1, le=12),
) -> LearningPathResponse:
    return await service.regenerate_learning_path(current_user.id, path_id, limit=limit)


@router.post("/quizzes/generate", response_model=QuizResponse, status_code=status.HTTP_201_CREATED)
async def generate_quiz(
    body: GenerateQuizRequest,
    current_user: CurrentUser,
    service: ReviewService = Depends(get_review_service),
) -> QuizResponse:
    return await service.generate_quiz(current_user.id, body)


@router.get("/quizzes/history", response_model=QuizListResponse)
async def list_quiz_history(
    current_user: CurrentUser,
    service: ReviewService = Depends(get_review_service),
    limit: int = Query(default=10, ge=1, le=50),
) -> QuizListResponse:
    return await service.list_quiz_history(current_user.id, limit=limit)


@router.get("/quizzes/attempts", response_model=QuizAttemptListResponse)
async def list_quiz_attempts(
    current_user: CurrentUser,
    service: ReviewService = Depends(get_review_service),
    limit: int = Query(default=10, ge=1, le=50),
) -> QuizAttemptListResponse:
    return await service.list_quiz_attempts(current_user.id, limit=limit)


@router.get("/quizzes/weak-areas", response_model=QuizWeakAreaListResponse)
async def list_quiz_weak_areas(
    current_user: CurrentUser,
    service: ReviewService = Depends(get_review_service),
    limit: int = Query(default=10, ge=1, le=50),
) -> QuizWeakAreaListResponse:
    return await service.list_quiz_weak_areas(current_user.id, limit=limit)


@router.post("/quizzes/{quiz_id}/submit", response_model=QuizAttemptResponse)
async def submit_quiz(
    quiz_id: UUID,
    body: SubmitQuizRequest,
    current_user: CurrentUser,
    service: ReviewService = Depends(get_review_service),
) -> QuizAttemptResponse:
    return await service.submit_quiz(current_user.id, quiz_id, body)


__all__ = ["router"]
