from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.use_cases.documents.notes.helpers import get_note, note_to_dto

if TYPE_CHECKING:
    from src.application.dtos.note_dtos import GetNoteDTO, NoteDTO
    from src.application.ports.persistence.unit_of_work import IUnitOfWork


class GetNoteUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, dto: GetNoteDTO) -> NoteDTO:
        document = await get_note(self._uow, user_id=dto.user_id, note_id=dto.note_id)
        return note_to_dto(document)
