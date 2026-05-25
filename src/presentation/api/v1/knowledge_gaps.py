from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Query, status

from src.application.use_cases.knowledge_gaps import (
    CreateKnowledgeGapNoteUseCase,
    GetKnowledgeGapsUseCase,
    ListKnowledgeGapsUseCase,
)
from src.presentation.dependencies.auth import CurrentUser
from src.presentation.mappers.knowledge_gap_mapper import to_knowledge_gap_list_response, to_knowledge_gap_response
from src.presentation.mappers.note_mapper import to_note_response
from src.presentation.schemas.knowledge_gap import (
    KnowledgeGapListResponse,
    KnowledgeGapNoteRequest,
    KnowledgeGapResponse,
)
from src.presentation.schemas.note import NoteResponse

router = APIRouter(prefix="/knowledge-gaps", tags=["knowledge-gaps"])


@router.get("", response_model=KnowledgeGapListResponse)
@inject
async def get_knowledge_gaps(
    current_user: CurrentUser,
    use_case: FromDishka[ListKnowledgeGapsUseCase],
    collection_id: UUID | None = Query(default=None),
    limit: int = Query(default=12, ge=1, le=50),
) -> KnowledgeGapListResponse:
    result = await use_case(user_id=current_user.id, collection_id=collection_id, limit=limit)
    return to_knowledge_gap_list_response(result)


@router.get("/{topic}", response_model=KnowledgeGapResponse)
@inject
async def get_knowledge_gap_detail(
    topic: str,
    current_user: CurrentUser,
    use_case: FromDishka[GetKnowledgeGapsUseCase],
    collection_id: UUID | None = Query(default=None),
) -> KnowledgeGapResponse:
    result = await use_case(user_id=current_user.id, topic=topic, collection_id=collection_id)
    return to_knowledge_gap_response(result)


@router.post("/{gap_id}/note", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
@inject
async def create_knowledge_gap_note(
    gap_id: str,
    body: KnowledgeGapNoteRequest,
    current_user: CurrentUser,
    use_case: FromDishka[CreateKnowledgeGapNoteUseCase],
) -> NoteResponse:
    result = await use_case(
        user_id=current_user.id,
        gap_id=gap_id,
        topic=body.topic,
        area_name=body.area_name,
        collection_id=UUID(body.collection_id) if body.collection_id else None,
    )
    return to_note_response(result)
