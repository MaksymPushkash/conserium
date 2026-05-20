from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter

from src.application.use_cases.compare import CompareDocumentsUseCase
from src.presentation.dependencies.auth import CurrentUser
from src.presentation.mappers.compare_mapper import to_compare_documents_dto, to_compare_documents_response
from src.presentation.schemas.compare import CompareDocumentsRequest, CompareDocumentsResponse

router = APIRouter(prefix="/compare", tags=["compare"])


@router.post("/documents", response_model=CompareDocumentsResponse)
@inject
async def compare_documents(
    current_user: CurrentUser,
    body: CompareDocumentsRequest,
    use_case: FromDishka[CompareDocumentsUseCase],
) -> CompareDocumentsResponse:
    result = await use_case(to_compare_documents_dto(body, current_user.id))
    return to_compare_documents_response(result)
