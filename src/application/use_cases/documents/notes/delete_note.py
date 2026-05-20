from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.use_cases.documents.notes.helpers import get_note

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.ports.persistence.unit_of_work import IUnitOfWork


class DeleteNoteUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: UUID, note_id: UUID) -> None:
        document = await get_note(self._uow, user_id=user_id, note_id=note_id)
        async with self._uow:
            await self._uow.document_repo.delete(document.id)
            await self._uow.commit()
