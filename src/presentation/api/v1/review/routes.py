from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Query, status

from src.application.dtos.review_dtos import GenerateFlashcardsDTO, ReviewFlashcardDTO
from src.application.use_cases.review import GenerateFlashcardsUseCase, ListDueFlashcardsUseCase, ReviewFlashcardUseCase
from src.presentation.api.v1.review.mappers import (
    to_flashcard_list_response,
    to_flashcard_response,
    to_generate_flashcards_response,
)
from src.presentation.api.v1.review.schemas import (
    FlashcardListResponse,
    FlashcardResponse,
    GenerateFlashcardsRequest,
    GenerateFlashcardsResponse,
    ReviewFlashcardRequest,
)
from src.presentation.dependencies.auth import CurrentUser

router = APIRouter(prefix="/review", tags=["review"])


@router.post("/flashcards/generate", response_model=GenerateFlashcardsResponse, status_code=status.HTTP_201_CREATED)
@inject
async def generate_flashcards(
    body: GenerateFlashcardsRequest,
    current_user: CurrentUser,
    use_case: FromDishka[GenerateFlashcardsUseCase],
) -> GenerateFlashcardsResponse:
    result = await use_case(
        GenerateFlashcardsDTO(
            user_id=current_user.id,
            document_id=body.document_id,
            collection_id=body.collection_id,
            topic=body.topic,
            limit=body.limit,
        )
    )
    return to_generate_flashcards_response(result)


@router.get("/flashcards/due", response_model=FlashcardListResponse)
@inject
async def list_due_flashcards(
    current_user: CurrentUser,
    use_case: FromDishka[ListDueFlashcardsUseCase],
    limit: int = Query(default=20, ge=1, le=100),
) -> FlashcardListResponse:
    result = await use_case(user_id=current_user.id, limit=limit)
    return to_flashcard_list_response(result)


@router.post("/flashcards/{flashcard_id}/review", response_model=FlashcardResponse)
@inject
async def review_flashcard(
    flashcard_id: UUID,
    body: ReviewFlashcardRequest,
    current_user: CurrentUser,
    use_case: FromDishka[ReviewFlashcardUseCase],
) -> FlashcardResponse:
    result = await use_case(ReviewFlashcardDTO(user_id=current_user.id, flashcard_id=flashcard_id, grade=body.grade))
    return to_flashcard_response(result)
