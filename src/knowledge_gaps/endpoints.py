from uuid import UUID

from fastapi import Depends, Query, status

from src.auth.auth import CurrentUser
from src.documents.notes import NoteService, get_note_service
from src.knowledge_gaps.schemas import (
    KnowledgeGapListResponse,
    KnowledgeGapNoteRequest,
    KnowledgeGapResponse,
    NoteResponse,
)
from src.knowledge_gaps.service import KnowledgeGapService, get_knowledge_gap_service
from src.postgres import AsyncSession, get_db_read_session
from src.routing import APIRouter

router = APIRouter(prefix="/knowledge-gaps", tags=["knowledge-gaps"])


@router.get("", response_model=KnowledgeGapListResponse)
async def get_knowledge_gaps(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_read_session),
    service: KnowledgeGapService = Depends(get_knowledge_gap_service),
    collection_id: UUID | None = Query(default=None),
    limit: int = Query(default=12, ge=1, le=50),
) -> KnowledgeGapListResponse:
    return await service.list(session, user_id=current_user.id, collection_id=collection_id, limit=limit)


@router.get("/{topic}", response_model=KnowledgeGapResponse)
async def get_knowledge_gap_detail(
    topic: str,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_read_session),
    service: KnowledgeGapService = Depends(get_knowledge_gap_service),
    collection_id: UUID | None = Query(default=None),
) -> KnowledgeGapResponse:
    return await service.get(session, user_id=current_user.id, topic=topic, collection_id=collection_id)


@router.post("/{gap_id}/note", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
async def create_knowledge_gap_note(
    gap_id: str,
    body: KnowledgeGapNoteRequest,
    current_user: CurrentUser,
    service: KnowledgeGapService = Depends(get_knowledge_gap_service),
    note_service: NoteService = Depends(get_note_service),
) -> NoteResponse:
    return await service.create_note(
        note_service=note_service,
        user_id=current_user.id,
        gap_id=gap_id,
        topic=body.topic,
        area_name=body.area_name,
        collection_id=UUID(body.collection_id) if body.collection_id else None,
    )


__all__ = ["router"]
