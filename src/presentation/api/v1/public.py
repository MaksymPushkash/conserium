from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter

from src.application.use_cases.collection_shares import GetPublicCollectionUseCase
from src.presentation.mappers.collection_share_mapper import to_public_collection_response
from src.presentation.schemas.collection_share import PublicCollectionResponse

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/collections/{slug}", response_model=PublicCollectionResponse)
@inject
async def get_public_collection(
    slug: str,
    use_case: FromDishka[GetPublicCollectionUseCase],
) -> PublicCollectionResponse:
    result = await use_case(slug=slug)
    return to_public_collection_response(result)
