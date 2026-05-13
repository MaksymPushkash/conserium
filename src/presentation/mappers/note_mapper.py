from src.application.dtos.note_dtos import NoteDTO, NoteListDTO, NoteListItemDTO
from src.application.dtos.note_version_dtos import NoteVersionDTO
from src.presentation.schemas.note import NoteListItemResponse, NoteListResponse, NoteResponse, NoteVersionResponse


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


def to_note_version_response(dto: NoteVersionDTO) -> NoteVersionResponse:
    return NoteVersionResponse(
        id=dto.id,
        note_id=dto.note_id,
        version_number=dto.version_number,
        title=dto.title,
        content=dto.content,
        created_at=dto.created_at,
    )
