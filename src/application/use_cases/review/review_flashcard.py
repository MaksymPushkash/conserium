import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from src.application.dtos.review_dtos import FlashcardDTO, ReviewFlashcardDTO
from src.application.ports.persistence.flashcard_repository import FlashcardReviewRecord
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.review.mapping import flashcard_to_dto
from src.domain.exceptions import ResourceNotFoundException
from src.domain.services.review_schedule import next_review_schedule
from src.domain.value_objects.review_grade import ReviewGrade


class ReviewFlashcardUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, dto: ReviewFlashcardDTO) -> FlashcardDTO:
        grade = ReviewGrade.from_raw(dto.grade)
        now = datetime.now(UTC)
        async with self._uow:
            flashcard = await self._uow.flashcard_repo.get_by_id(dto.flashcard_id)
            if flashcard is None:
                raise ResourceNotFoundException("flashcard not found")
            if flashcard.user_id != dto.user_id:
                raise ResourceNotFoundException("flashcard not found")
            next_schedule = next_review_schedule(
                grade=grade,
                interval_days=flashcard.interval_days,
                ease_factor=flashcard.ease_factor,
            )
            reviewed = await self._uow.flashcard_repo.update_schedule(
                flashcard_id=flashcard.id,
                due_at=now + timedelta(days=next_schedule.interval_days),
                interval_days=next_schedule.interval_days,
                ease_factor=next_schedule.ease_factor,
                review_count=flashcard.review_count + 1,
            )
            await self._uow.flashcard_repo.create_review(
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
            await self._uow.commit()
        return flashcard_to_dto(replace(reviewed, source_title=flashcard.source_title))
