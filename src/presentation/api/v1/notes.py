from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Query, Response, status

from src.application.use_cases.documents.note_use_cases import (
    CreateNoteUseCase,
    DeleteNoteUseCase,
    GetNoteUseCase,
    ListNotesUseCase,
    UpdateNoteUseCase,
)
from src.presentation.dependencies.auth import CurrentUser
from src.presentation.mappers.note_mapper import to_note_list_response, to_note_response
from src.presentation.mappers.note_request_mapper import (
    to_create_note_dto,
    to_get_note_dto,
    to_list_notes_dto,
    to_update_note_dto,
)
from src.presentation.schemas.note import CreateNoteRequest, NoteListResponse, NoteResponse, UpdateNoteRequest

router = APIRouter(prefix="/notes", tags=["notes"])


@router.post("", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
@inject
async def create_note(
    body: CreateNoteRequest,
    current_user: CurrentUser,
    use_case: FromDishka[CreateNoteUseCase],
) -> NoteResponse:
    result = await use_case(to_create_note_dto(body, current_user.id))
    return to_note_response(result)


@router.get("", response_model=NoteListResponse)
@inject
async def list_notes(
    current_user: CurrentUser,
    use_case: FromDishka[ListNotesUseCase],
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    collection_id: UUID | None = Query(default=None),
) -> NoteListResponse:
    result = await use_case(to_list_notes_dto(current_user.id, limit, offset, collection_id))
    return to_note_list_response(result)


@router.get("/{note_id}", response_model=NoteResponse)
@inject
async def get_note(
    note_id: UUID,
    current_user: CurrentUser,
    use_case: FromDishka[GetNoteUseCase],
) -> NoteResponse:
    result = await use_case(to_get_note_dto(note_id, current_user.id))
    return to_note_response(result)


@router.patch("/{note_id}", response_model=NoteResponse)
@inject
async def update_note(
    note_id: UUID,
    body: UpdateNoteRequest,
    current_user: CurrentUser,
    use_case: FromDishka[UpdateNoteUseCase],
) -> NoteResponse:
    result = await use_case(to_update_note_dto(note_id, body, current_user.id))
    return to_note_response(result)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
@inject
async def delete_note(
    note_id: UUID,
    current_user: CurrentUser,
    use_case: FromDishka[DeleteNoteUseCase],
) -> Response:
    await use_case(user_id=current_user.id, note_id=note_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
