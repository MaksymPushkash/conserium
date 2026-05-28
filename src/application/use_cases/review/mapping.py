from src.application.dtos.review_dtos import FlashcardDTO
from src.application.ports.persistence.flashcard_repository import FlashcardRecord


def flashcard_to_dto(record: FlashcardRecord) -> FlashcardDTO:
    return FlashcardDTO(
        id=record.id,
        user_id=record.user_id,
        scope_type=record.scope_type,
        collection_id=record.collection_id,
        topic=record.topic,
        source_document_id=record.source_document_id,
        source_chunk_id=record.source_chunk_id,
        question=record.question,
        answer=record.answer,
        citation_metadata=record.citation_metadata,
        due_at=record.due_at,
        interval_days=record.interval_days,
        ease_factor=record.ease_factor,
        review_count=record.review_count,
        source_title=record.source_title,
        created_at=record.created_at or record.due_at,
        updated_at=record.updated_at,
    )
