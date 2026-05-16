from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Query

from src.application.use_cases.topics import GetTopicDetailUseCase, ListTopicsUseCase
from src.presentation.dependencies.auth import CurrentUser
from src.presentation.mappers.topic_mapper import to_topic_detail_response, to_topic_list_response
from src.presentation.schemas.topic import TopicDetailResponse, TopicListResponse

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
