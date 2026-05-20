from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.use_cases.documents.notes.helpers import get_note, note_version_to_dto

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.dtos.note_version_dtos import NoteVersionDTO
    from src.application.ports.persistence.unit_of_work import IUnitOfWork


class ListNoteVersionsUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: UUID, note_id: UUID) -> list[NoteVersionDTO]:
        await get_note(self._uow, user_id=user_id, note_id=note_id)
        async with self._uow:
            versions = await self._uow.note_version_repo.list_by_note_id(note_id=note_id, user_id=user_id)
        return [note_version_to_dto(version) for version in versions]
