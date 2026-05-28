from src.application.dtos.review_dtos import FlashcardDTO, FlashcardListDTO, GenerateFlashcardsResultDTO
from src.presentation.api.v1.review.schemas import FlashcardListResponse, FlashcardResponse, GenerateFlashcardsResponse


def to_flashcard_response(dto: FlashcardDTO) -> FlashcardResponse:
    return FlashcardResponse(
        id=dto.id,
        user_id=dto.user_id,
        scope_type=dto.scope_type,
        collection_id=dto.collection_id,
        topic=dto.topic,
        source_document_id=dto.source_document_id,
        source_chunk_id=dto.source_chunk_id,
        question=dto.question,
        answer=dto.answer,
        citation_metadata=dto.citation_metadata,
        due_at=dto.due_at,
        interval_days=dto.interval_days,
        ease_factor=dto.ease_factor,
        review_count=dto.review_count,
        source_title=dto.source_title,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
    )


def to_flashcard_list_response(dto: FlashcardListDTO) -> FlashcardListResponse:
    return FlashcardListResponse(
        items=[to_flashcard_response(item) for item in dto.items],
        total=dto.total,
        limit=dto.limit,
    )


def to_generate_flashcards_response(dto: GenerateFlashcardsResultDTO) -> GenerateFlashcardsResponse:
    return GenerateFlashcardsResponse(
        items=[to_flashcard_response(item) for item in dto.items],
        created_count=dto.created_count,
    )
