from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from src.application.dtos.external_intake_dtos import ExternalIngestDTO
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
from src.application.use_cases.telegram import (
    ConsumeTelegramPairingCodeDTO,
    ConsumeTelegramPairingCodeUseCase,
    CreateTelegramPairingCodeUseCase,
    GetTelegramStatusUseCase,
    IngestTelegramItemUseCase,
    RevokeTelegramBindingUseCase,
)
from src.core.config import settings
from src.domain.exceptions import DomainException
from src.presentation.dependencies.auth import CurrentUser
from src.presentation.mappers.external_intake_mapper import to_external_ingest_response
from src.presentation.mappers.integration_mapper import to_notion_connection_response, to_notion_page_response
from src.presentation.mappers.telegram_mapper import (
    to_telegram_pairing_code_response,
    to_telegram_status_response,
)
from src.presentation.oauth_redirects import build_callback_uri
from src.presentation.schemas.integration import (
    IntegrationConnectUrlResponse,
    NotionConnectionResponse,
    NotionConnectionSettingsRequest,
    NotionImportRequest,
    NotionImportResponse,
    NotionPageResponse,
)
from src.presentation.schemas.telegram import (
    TelegramConsumePairingRequest,
    TelegramIngestRequest,
    TelegramIngestResponse,
    TelegramPairingCodeResponse,
    TelegramStatusResponse,
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


@router.get("/telegram", response_model=TelegramStatusResponse)
@inject
async def get_telegram_status(
    current_user: CurrentUser,
    use_case: FromDishka[GetTelegramStatusUseCase],
) -> TelegramStatusResponse:
    return to_telegram_status_response(await use_case(user_id=current_user.id))


@router.post("/telegram/pairing-code", response_model=TelegramPairingCodeResponse, status_code=status.HTTP_201_CREATED)
@inject
async def create_telegram_pairing_code(
    current_user: CurrentUser,
    use_case: FromDishka[CreateTelegramPairingCodeUseCase],
) -> TelegramPairingCodeResponse:
    return to_telegram_pairing_code_response(await use_case(user_id=current_user.id))


@router.delete("/telegram/bindings/{binding_id}", status_code=status.HTTP_204_NO_CONTENT)
@inject
async def revoke_telegram_binding(
    binding_id: UUID,
    current_user: CurrentUser,
    use_case: FromDishka[RevokeTelegramBindingUseCase],
) -> Response:
    await use_case(user_id=current_user.id, binding_id=binding_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/telegram/bot/consume-pairing")
@inject
async def telegram_bot_consume_pairing(
    body: TelegramConsumePairingRequest,
    use_case: FromDishka[ConsumeTelegramPairingCodeUseCase],
    x_conserium_telegram_secret: str | None = Header(default=None),
) -> dict[str, object]:
    _ensure_telegram_secret(x_conserium_telegram_secret)
    binding = await use_case(
        ConsumeTelegramPairingCodeDTO(
            code=body.code,
            chat_id=body.chat_id,
            chat_username=body.chat_username,
            chat_title=body.chat_title,
        )
    )
    return {"status": "paired", "binding_id": str(binding.id)}


@router.post("/telegram/bot/ingest", response_model=TelegramIngestResponse, status_code=status.HTTP_202_ACCEPTED)
@inject
async def telegram_bot_ingest(
    body: TelegramIngestRequest,
    use_case: FromDishka[IngestTelegramItemUseCase],
    x_conserium_telegram_secret: str | None = Header(default=None),
) -> TelegramIngestResponse:
    _ensure_telegram_secret(x_conserium_telegram_secret)
    response = to_external_ingest_response(
        await use_case(
            chat_id=body.chat_id,
            dto=ExternalIngestDTO(
                user_id=UUID(int=0),
                api_key_id=None,
                provider=body.provider or "telegram",
                title=body.title,
                type=body.type,
                collection_id=body.collection_id,
                tags=body.tags,
                source_url=body.source_url,
                raw_content=body.raw_content,
                language=body.language,
                external_id=body.external_id,
                idempotency_key=body.idempotency_key,
                payload_metadata=body.metadata,
            ),
        )
    )
    return TelegramIngestResponse(intake_item=response.intake_item, document=response.document)


def _ensure_telegram_secret(value: str | None) -> None:
    if not settings.TELEGRAM_BOT_SECRET or value != settings.TELEGRAM_BOT_SECRET:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid telegram bot secret")
