from src.application.dtos.note_dtos import NoteDTO, NoteListDTO, NoteListItemDTO
from src.presentation.schemas.note import NoteListItemResponse, NoteListResponse, NoteResponse


def to_note_response(dto: NoteDTO) -> NoteResponse:
    return NoteResponse(
        id=dto.id,
        collection_id=dto.collection_id,
        title=dto.title,
        content=dto.content,
        status=dto.status,
        word_count=dto.word_count,
        language=dto.language,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
    )


def to_note_list_item_response(dto: NoteListItemDTO) -> NoteListItemResponse:
    return NoteListItemResponse(
        id=dto.id,
        collection_id=dto.collection_id,
        title=dto.title,
        status=dto.status,
        word_count=dto.word_count,
        language=dto.language,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
    )


def to_note_list_response(dto: NoteListDTO) -> NoteListResponse:
    return NoteListResponse(
        items=[to_note_list_item_response(item) for item in dto.items],
        total=dto.total,
        limit=dto.limit,
        offset=dto.offset,
    )
