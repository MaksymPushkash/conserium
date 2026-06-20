from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from src.auth.auth import CurrentUser
from src.auth.oauth_redirects import build_callback_uri
from src.documents.schemas import ExternalIngestDTO
from src.integrations.dependencies import (
    get_notion_connection_service,
    get_notion_workspace_service,
    get_telegram_ingestion_service,
    get_telegram_pairing_service,
)
from src.integrations.schemas import (
    IntegrationConnectUrlResponse,
    NotionConnectionResponse,
    NotionConnectionSettingsRequest,
    NotionImportRequest,
    NotionImportResponse,
    NotionPageResponse,
    TelegramConsumePairingRequest,
    TelegramIngestRequest,
    TelegramIngestResponse,
    TelegramPairingCodeResponse,
    TelegramStatusResponse,
)
from src.integrations.service import (
    ConsumeTelegramPairingCodeDTO,
    NotionConnectionService,
    NotionWorkspaceService,
    TelegramIngestionService,
    TelegramPairingService,
    notion_settings_redirect,
    to_notion_connection_response,
    to_notion_page_response,
    to_telegram_pairing_code_response,
    to_telegram_status_response,
)
from src.kit.exceptions import DomainException
from src.routing import APIRouter
from src.settings import settings
from src.webhooks.endpoints import to_external_ingest_response

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("/notion", response_model=NotionConnectionResponse)
async def get_notion_connection(
    current_user: CurrentUser,
    service: NotionConnectionService = Depends(get_notion_connection_service),
) -> NotionConnectionResponse:
    return to_notion_connection_response(await service.get(user_id=current_user.id))


@router.patch("/notion", response_model=NotionConnectionResponse)
async def update_notion_connection_settings(
    body: NotionConnectionSettingsRequest,
    current_user: CurrentUser,
    service: NotionConnectionService = Depends(get_notion_connection_service),
) -> NotionConnectionResponse:
    result = await service.update_settings(
        user_id=current_user.id,
        default_parent_page_id=body.default_parent_page_id,
        default_parent_page_title=body.default_parent_page_title,
    )
    return to_notion_connection_response(result)


@router.get("/notion/pages", response_model=list[NotionPageResponse])
async def search_notion_pages(
    current_user: CurrentUser,
    query: str | None = None,
    limit: int = 10,
    service: NotionWorkspaceService = Depends(get_notion_workspace_service),
) -> list[NotionPageResponse]:
    result = await service.search_pages(user_id=current_user.id, query=query, limit=limit)
    return [to_notion_page_response(page) for page in result]


@router.post("/notion/import", response_model=NotionImportResponse, status_code=status.HTTP_202_ACCEPTED)
async def import_notion_page(
    body: NotionImportRequest,
    current_user: CurrentUser,
    service: NotionWorkspaceService = Depends(get_notion_workspace_service),
) -> NotionImportResponse:
    response = to_external_ingest_response(
        await service.import_page(
            user_id=current_user.id,
            page_id=body.page_id,
            collection_id=body.collection_id,
            tags=body.tags,
        )
    )
    return NotionImportResponse(intake_item=response.intake_item, document=response.document)


@router.post("/notion/connect-url", response_model=IntegrationConnectUrlResponse)
async def create_notion_connect_url(
    request: Request,
    current_user: CurrentUser,
    service: NotionConnectionService = Depends(get_notion_connection_service),
) -> IntegrationConnectUrlResponse:
    url = await service.create_connect_url(
        user_id=current_user.id,
        redirect_uri=build_callback_uri(request, "/api/v1/integrations/notion/callback"),
    )
    return IntegrationConnectUrlResponse(url=url)


@router.get("/notion/callback")
async def notion_callback(
    request: Request,
    service: NotionConnectionService = Depends(get_notion_connection_service),
) -> RedirectResponse:
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if not code or not state:
        return RedirectResponse(notion_settings_redirect("missing_code"), status_code=302)
    try:
        await service.complete(
            code=code,
            state=state,
            redirect_uri=build_callback_uri(request, "/api/v1/integrations/notion/callback"),
        )
    except DomainException:
        return RedirectResponse(notion_settings_redirect("error"), status_code=302)
    return RedirectResponse(notion_settings_redirect("connected"), status_code=302)


@router.delete("/notion", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_notion(
    current_user: CurrentUser,
    service: NotionConnectionService = Depends(get_notion_connection_service),
) -> Response:
    await service.disconnect(user_id=current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/telegram", response_model=TelegramStatusResponse)
async def get_telegram_status(
    current_user: CurrentUser,
    service: TelegramPairingService = Depends(get_telegram_pairing_service),
) -> TelegramStatusResponse:
    return to_telegram_status_response(await service.get_status(user_id=current_user.id))


@router.post("/telegram/pairing-code", response_model=TelegramPairingCodeResponse, status_code=status.HTTP_201_CREATED)
async def create_telegram_pairing_code(
    current_user: CurrentUser,
    service: TelegramPairingService = Depends(get_telegram_pairing_service),
) -> TelegramPairingCodeResponse:
    return to_telegram_pairing_code_response(await service.create_pairing_code(user_id=current_user.id))


@router.delete("/telegram/bindings/{binding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_telegram_binding(
    binding_id: UUID,
    current_user: CurrentUser,
    service: TelegramPairingService = Depends(get_telegram_pairing_service),
) -> Response:
    await service.revoke_binding(user_id=current_user.id, binding_id=binding_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/telegram/bot/consume-pairing")
async def telegram_bot_consume_pairing(
    body: TelegramConsumePairingRequest,
    x_conserium_telegram_secret: str | None = Header(default=None),
    service: TelegramPairingService = Depends(get_telegram_pairing_service),
) -> dict[str, object]:
    _ensure_telegram_secret(x_conserium_telegram_secret)
    binding = await service.consume_pairing_code(
        ConsumeTelegramPairingCodeDTO(
            code=body.code,
            chat_id=body.chat_id,
            chat_username=body.chat_username,
            chat_title=body.chat_title,
        )
    )
    return {"status": "paired", "binding_id": str(binding.id)}


@router.post("/telegram/bot/ingest", response_model=TelegramIngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def telegram_bot_ingest(
    body: TelegramIngestRequest,
    x_conserium_telegram_secret: str | None = Header(default=None),
    service: TelegramIngestionService = Depends(get_telegram_ingestion_service),
) -> TelegramIngestResponse:
    _ensure_telegram_secret(x_conserium_telegram_secret)
    response = to_external_ingest_response(
        await service.ingest(
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


__all__ = ["router"]
