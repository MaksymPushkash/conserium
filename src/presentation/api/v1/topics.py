from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Query

from src.application.use_cases.topics import (
    GetTopicDetailUseCase,
    IgnoreTopicUseCase,
    ListTopicsUseCase,
    MergeTopicsUseCase,
    PinTopicUseCase,
    RenameTopicUseCase,
)
from src.presentation.dependencies.auth import CurrentUser
from src.presentation.mappers.topic_mapper import to_topic_detail_response, to_topic_list_response, to_topic_response
from src.presentation.schemas.topic import (
    TopicDetailResponse,
    TopicIgnoreRequest,
    TopicListResponse,
    TopicMergeRequest,
    TopicPinRequest,
    TopicRenameRequest,
    TopicResponse,
)

router = APIRouter(prefix="/topics", tags=["topics"])


@router.get("", response_model=TopicListResponse)
@inject
async def list_topics(
    current_user: CurrentUser,
    use_case: FromDishka[ListTopicsUseCase],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> TopicListResponse:
    result = await use_case(user_id=current_user.id, limit=limit, offset=offset)
    return to_topic_list_response(result)


@router.get("/{name}", response_model=TopicDetailResponse)
@inject
async def get_topic_detail(
    name: str,
    current_user: CurrentUser,
    use_case: FromDishka[GetTopicDetailUseCase],
    document_limit: int = Query(default=10, ge=1, le=50),
) -> TopicDetailResponse:
    result = await use_case(user_id=current_user.id, name=name, document_limit=document_limit)
    return to_topic_detail_response(result)


@router.patch("/{name}", response_model=TopicResponse)
@inject
async def rename_topic(
    name: str,
    body: TopicRenameRequest,
    current_user: CurrentUser,
    use_case: FromDishka[RenameTopicUseCase],
) -> TopicResponse:
    result = await use_case(user_id=current_user.id, name=name, display_name=body.display_name)
    return to_topic_response(result)


@router.post("/{name}/merge", response_model=TopicResponse)
@inject
async def merge_topics(
    name: str,
    body: TopicMergeRequest,
    current_user: CurrentUser,
    use_case: FromDishka[MergeTopicsUseCase],
) -> TopicResponse:
    result = await use_case(user_id=current_user.id, name=name, source_names=body.source_names)
    return to_topic_response(result)


@router.post("/{name}/pin", response_model=TopicResponse)
@inject
async def pin_topic(
    name: str,
    body: TopicPinRequest,
    current_user: CurrentUser,
    use_case: FromDishka[PinTopicUseCase],
) -> TopicResponse:
    result = await use_case(user_id=current_user.id, name=name, pinned=body.pinned)
    return to_topic_response(result)


@router.post("/{name}/ignore", response_model=TopicResponse)
@inject
async def ignore_topic(
    name: str,
    body: TopicIgnoreRequest,
    current_user: CurrentUser,
    use_case: FromDishka[IgnoreTopicUseCase],
) -> TopicResponse:
    result = await use_case(user_id=current_user.id, name=name, ignored=body.ignored)
    return to_topic_response(result)
