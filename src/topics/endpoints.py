from fastapi import Depends, Query

from src.auth.auth import CurrentUser
from src.postgres import AsyncReadSession, AsyncSession, get_db_read_session, get_db_session
from src.routing import APIRouter
from src.topics.schemas import (
    TopicDetailResponse,
    TopicIgnoreRequest,
    TopicListResponse,
    TopicMergeRequest,
    TopicPinRequest,
    TopicRenameRequest,
    TopicResponse,
)
from src.topics.service import topics

router = APIRouter(prefix="/topics", tags=["topics"])


@router.get("", response_model=TopicListResponse)
async def list_topics(
    current_user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncReadSession = Depends(get_db_read_session),
) -> TopicListResponse:
    return await topics.list_topics(session, user_id=current_user.id, limit=limit, offset=offset)


@router.get("/{name}", response_model=TopicDetailResponse)
async def get_topic_detail(
    name: str,
    current_user: CurrentUser,
    document_limit: int = Query(default=10, ge=1, le=50),
    session: AsyncReadSession = Depends(get_db_read_session),
) -> TopicDetailResponse:
    return await topics.get_detail(session, user_id=current_user.id, name=name, document_limit=document_limit)


@router.patch("/{name}", response_model=TopicResponse)
async def rename_topic(
    name: str,
    body: TopicRenameRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> TopicResponse:
    return await topics.rename(session, user_id=current_user.id, name=name, display_name=body.display_name)


@router.post("/{name}/merge", response_model=TopicResponse)
async def merge_topics(
    name: str,
    body: TopicMergeRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> TopicResponse:
    return await topics.merge(session, user_id=current_user.id, name=name, source_names=body.source_names)


@router.post("/{name}/pin", response_model=TopicResponse)
async def pin_topic(
    name: str,
    body: TopicPinRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> TopicResponse:
    return await topics.pin(session, user_id=current_user.id, name=name, pinned=body.pinned)


@router.post("/{name}/ignore", response_model=TopicResponse)
async def ignore_topic(
    name: str,
    body: TopicIgnoreRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> TopicResponse:
    return await topics.ignore(session, user_id=current_user.id, name=name, ignored=body.ignored)

__all__ = ["router"]
