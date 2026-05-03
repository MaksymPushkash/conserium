from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Query, Response, status

from src.application.dtos.note_dtos import CreateNoteDTO, GetNoteDTO, ListNotesDTO, UpdateNoteDTO
from src.application.use_cases.documents.note_use_cases import (
    CreateNoteUseCase,
    DeleteNoteUseCase,
    GetNoteUseCase,
    ListNotesUseCase,
    UpdateNoteUseCase,
)
from src.presentation.dependencies.auth import CurrentUser
from src.presentation.schemas.note import CreateNoteRequest, NoteListResponse, NoteResponse, UpdateNoteRequest

router = APIRouter(prefix="/notes", tags=["notes"])


@router.post("", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
@inject
async def create_note(
    body: CreateNoteRequest,
    current_user: CurrentUser,
    use_case: FromDishka[CreateNoteUseCase],
) -> NoteResponse:
    result = await use_case(
        CreateNoteDTO(
            user_id=current_user.id,
            title=body.title,
            content=body.content,
            language=body.language,
        )
    )
    return NoteResponse.from_dto(result)


@router.get("", response_model=NoteListResponse)
@inject
async def list_notes(
    current_user: CurrentUser,
    use_case: FromDishka[ListNotesUseCase],
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> NoteListResponse:
    result = await use_case(ListNotesDTO(user_id=current_user.id, limit=limit, offset=offset))
    return NoteListResponse.from_dto(result)


@router.get("/{note_id}", response_model=NoteResponse)
@inject
async def get_note(
    note_id: UUID,
    current_user: CurrentUser,
    use_case: FromDishka[GetNoteUseCase],
) -> NoteResponse:
    result = await use_case(GetNoteDTO(user_id=current_user.id, note_id=note_id))
    return NoteResponse.from_dto(result)


@router.patch("/{note_id}", response_model=NoteResponse)
@inject
async def update_note(
    note_id: UUID,
    body: UpdateNoteRequest,
    current_user: CurrentUser,
    use_case: FromDishka[UpdateNoteUseCase],
) -> NoteResponse:
    result = await use_case(
        UpdateNoteDTO(
            user_id=current_user.id,
            note_id=note_id,
            title=body.title,
            content=body.content,
            language=body.language,
        )
    )
    return NoteResponse.from_dto(result)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
@inject
async def delete_note(
    note_id: UUID,
    current_user: CurrentUser,
    use_case: FromDishka[DeleteNoteUseCase],
) -> Response:
    await use_case(user_id=current_user.id, note_id=note_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
