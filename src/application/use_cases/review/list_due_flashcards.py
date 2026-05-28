import uuid
from datetime import UTC, datetime

from src.application.dtos.review_dtos import FlashcardListDTO
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.review.mapping import flashcard_to_dto


class ListDueFlashcardsUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: uuid.UUID, limit: int = 20) -> FlashcardListDTO:
        now = datetime.now(UTC)
        async with self._uow:
            items = await self._uow.flashcard_repo.list_due(user_id=user_id, now=now, limit=limit)
            total = await self._uow.flashcard_repo.count_due(user_id=user_id, now=now)
        return FlashcardListDTO(
            items=[flashcard_to_dto(item) for item in items],
            total=total,
            limit=limit,
        )
