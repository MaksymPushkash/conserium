from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.dtos.note_dtos import ListNotesDTO, NoteListDTO
from src.application.use_cases.documents.notes.helpers import note_to_list_item_dto
from src.domain.value_objects.document_type import DocumentType

if TYPE_CHECKING:
    from src.application.ports.persistence.unit_of_work import IUnitOfWork


class ListNotesUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, dto: ListNotesDTO) -> NoteListDTO:
        async with self._uow:
            paged_notes = await self._uow.document_repo.get_by_user_id(
                dto.user_id,
                limit=dto.limit,
                offset=dto.offset,
                document_type=DocumentType.MARKDOWN,
                collection_id=dto.collection_id,
            )
            total = await self._uow.document_repo.count_by_user_id(
                dto.user_id,
                document_type=DocumentType.MARKDOWN,
                collection_id=dto.collection_id,
            )
        return NoteListDTO(
            items=[note_to_list_item_dto(document) for document in paged_notes],
            total=total,
            limit=dto.limit,
            offset=dto.offset,
        )
