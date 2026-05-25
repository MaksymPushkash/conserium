from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Request, Response, status
from fastapi.responses import RedirectResponse

from src.application.use_cases.integrations import (
    CompleteNotionConnectionUseCase,
    CreateNotionConnectUrlUseCase,
    DisconnectNotionUseCase,
    GetNotionConnectionUseCase,
    ImportNotionPageUseCase,
    SearchNotionPagesUseCase,
    UpdateNotionConnectionSettingsUseCase,
    notion_settings_redirect,
)
from src.domain.exceptions import DomainException
from src.presentation.dependencies.auth import CurrentUser
from src.presentation.mappers.external_intake_mapper import to_external_ingest_response
from src.presentation.mappers.integration_mapper import to_notion_connection_response, to_notion_page_response
from src.presentation.oauth_redirects import build_callback_uri
from src.presentation.schemas.integration import (
    IntegrationConnectUrlResponse,
    NotionConnectionResponse,
    NotionConnectionSettingsRequest,
    NotionImportRequest,
    NotionImportResponse,
    NotionPageResponse,
)

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("/notion", response_model=NotionConnectionResponse)
@inject
async def get_notion_connection(
    current_user: CurrentUser,
    use_case: FromDishka[GetNotionConnectionUseCase],
) -> NotionConnectionResponse:
    return to_notion_connection_response(await use_case(user_id=current_user.id))


@router.patch("/notion", response_model=NotionConnectionResponse)
@inject
async def update_notion_connection_settings(
    body: NotionConnectionSettingsRequest,
    current_user: CurrentUser,
    use_case: FromDishka[UpdateNotionConnectionSettingsUseCase],
) -> NotionConnectionResponse:
    result = await use_case(
        user_id=current_user.id,
        default_parent_page_id=body.default_parent_page_id,
        default_parent_page_title=body.default_parent_page_title,
    )
    return to_notion_connection_response(result)


@router.get("/notion/pages", response_model=list[NotionPageResponse])
@inject
async def search_notion_pages(
    current_user: CurrentUser,
    use_case: FromDishka[SearchNotionPagesUseCase],
    query: str | None = None,
    limit: int = 10,
) -> list[NotionPageResponse]:
    result = await use_case(user_id=current_user.id, query=query, limit=limit)
    return [to_notion_page_response(page) for page in result]


@router.post("/notion/import", response_model=NotionImportResponse, status_code=status.HTTP_202_ACCEPTED)
@inject
async def import_notion_page(
    body: NotionImportRequest,
    current_user: CurrentUser,
    use_case: FromDishka[ImportNotionPageUseCase],
) -> NotionImportResponse:
    response = to_external_ingest_response(
        await use_case(
            user_id=current_user.id,
            page_id=body.page_id,
            collection_id=body.collection_id,
            tags=body.tags,
        )
    )
    return NotionImportResponse(intake_item=response.intake_item, document=response.document)


@router.post("/notion/connect-url", response_model=IntegrationConnectUrlResponse)
@inject
async def create_notion_connect_url(
    request: Request,
    current_user: CurrentUser,
    use_case: FromDishka[CreateNotionConnectUrlUseCase],
) -> IntegrationConnectUrlResponse:
    url = await use_case(
        user_id=current_user.id,
        redirect_uri=build_callback_uri(request, "/api/v1/integrations/notion/callback"),
    )
    return IntegrationConnectUrlResponse(url=url)


@router.get("/notion/callback")
@inject
async def notion_callback(
    request: Request,
    use_case: FromDishka[CompleteNotionConnectionUseCase],
) -> RedirectResponse:
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if not code or not state:
        return RedirectResponse(notion_settings_redirect("missing_code"), status_code=302)
    try:
        await use_case(
            code=code,
            state=state,
            redirect_uri=build_callback_uri(request, "/api/v1/integrations/notion/callback"),
        )
    except DomainException:
        return RedirectResponse(notion_settings_redirect("error"), status_code=302)
    return RedirectResponse(notion_settings_redirect("connected"), status_code=302)


@router.delete("/notion", status_code=status.HTTP_204_NO_CONTENT)
@inject
async def disconnect_notion(
    current_user: CurrentUser,
    use_case: FromDishka[DisconnectNotionUseCase],
) -> Response:
    await use_case(user_id=current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
