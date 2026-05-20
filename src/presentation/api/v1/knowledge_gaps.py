from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Query

from src.application.use_cases.knowledge_gaps import GetKnowledgeGapsUseCase
from src.presentation.dependencies.auth import CurrentUser
from src.presentation.mappers.knowledge_gap_mapper import to_knowledge_gap_response
from src.presentation.schemas.knowledge_gap import KnowledgeGapResponse

router = APIRouter(prefix="/knowledge-gaps", tags=["knowledge-gaps"])


@router.get("", response_model=KnowledgeGapResponse)
@inject
async def get_knowledge_gaps(
    current_user: CurrentUser,
    use_case: FromDishka[GetKnowledgeGapsUseCase],
    topic: str = Query(min_length=1, max_length=100),
) -> KnowledgeGapResponse:
    result = await use_case(user_id=current_user.id, topic=topic)
    return to_knowledge_gap_response(result)
