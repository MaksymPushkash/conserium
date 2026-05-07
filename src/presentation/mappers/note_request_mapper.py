from uuid import UUID

from src.application.dtos.note_dtos import CreateNoteDTO, GetNoteDTO, ListNotesDTO, UpdateNoteDTO
from src.presentation.schemas.note import CreateNoteRequest, UpdateNoteRequest


def to_create_note_dto(body: CreateNoteRequest, user_id: UUID) -> CreateNoteDTO:
    return CreateNoteDTO(
        user_id=user_id,
        title=body.title,
        content=body.content,
        language=body.language,
    )


def to_list_notes_dto(user_id: UUID, limit: int, offset: int) -> ListNotesDTO:
    return ListNotesDTO(user_id=user_id, limit=limit, offset=offset)


def to_get_note_dto(note_id: UUID, user_id: UUID) -> GetNoteDTO:
    return GetNoteDTO(user_id=user_id, note_id=note_id)


def to_update_note_dto(note_id: UUID, body: UpdateNoteRequest, user_id: UUID) -> UpdateNoteDTO:
    return UpdateNoteDTO(
        user_id=user_id,
        note_id=note_id,
        title=body.title,
        content=body.content,
        language=body.language,
    )
