from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter

from src.application.use_cases.drafts import GenerateDraftUseCase
from src.presentation.dependencies.auth import CurrentUser
from src.presentation.mappers.draft_mapper import to_draft_generate_dto, to_draft_response
from src.presentation.schemas.draft import DraftGenerateRequest, DraftResponse

router = APIRouter(prefix="/drafts", tags=["drafts"])


@router.post("/generate", response_model=DraftResponse)
@inject
async def generate_draft(
    current_user: CurrentUser,
    body: DraftGenerateRequest,
    use_case: FromDishka[GenerateDraftUseCase],
) -> DraftResponse:
    result = await use_case(to_draft_generate_dto(body, current_user.id))
    return to_draft_response(result)
