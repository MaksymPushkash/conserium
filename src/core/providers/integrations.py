from dishka import Provider, Scope, provide

from src.application.ports.integrations.notion_oauth_client import INotionOAuthClient
from src.application.ports.integrations.notion_workspace_client import INotionWorkspaceClient
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.ports.security.token_cipher import ITokenCipher
from src.application.use_cases.external_intake import IngestExternalItemUseCase
from src.application.use_cases.integrations import (
    CompleteNotionConnectionUseCase,
    CreateNotionConnectUrlUseCase,
    DisconnectNotionUseCase,
    GetNotionConnectionUseCase,
    ImportNotionPageUseCase,
    SearchNotionPagesUseCase,
    UpdateNotionConnectionSettingsUseCase,
)
from src.core.config import settings
from src.infrastructure.integrations.notion_oauth_client import NotionOAuthClient
from src.infrastructure.integrations.notion_workspace_client import NotionWorkspaceClient
from src.infrastructure.security.fernet_token_cipher import FernetTokenCipher
from src.infrastructure.security.signed_state import SignedState


class IntegrationsProvider(Provider):
    @provide(scope=Scope.APP)
    def get_token_cipher(self) -> ITokenCipher:
        return FernetTokenCipher(settings.TOKEN_ENCRYPTION_KEY, key_version=settings.TOKEN_ENCRYPTION_KEY_VERSION)

    @provide(scope=Scope.APP)
    def get_signed_state(self) -> SignedState:
        return SignedState(settings.JWT_SECRET)

    @provide(scope=Scope.APP)
    def get_notion_oauth_client(self) -> INotionOAuthClient:
        return NotionOAuthClient()

    @provide(scope=Scope.APP)
    def get_notion_workspace_client(self) -> INotionWorkspaceClient:
        return NotionWorkspaceClient()

    @provide(scope=Scope.REQUEST)
    def get_get_notion_connection_use_case(self, uow: IUnitOfWork) -> GetNotionConnectionUseCase:
        return GetNotionConnectionUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_create_notion_connect_url_use_case(
        self,
        oauth_client: INotionOAuthClient,
        signed_state: SignedState,
    ) -> CreateNotionConnectUrlUseCase:
        return CreateNotionConnectUrlUseCase(oauth_client, signed_state)

    @provide(scope=Scope.REQUEST)
    def get_complete_notion_connection_use_case(
        self,
        uow: IUnitOfWork,
        oauth_client: INotionOAuthClient,
        token_cipher: ITokenCipher,
        signed_state: SignedState,
    ) -> CompleteNotionConnectionUseCase:
        return CompleteNotionConnectionUseCase(uow, oauth_client, token_cipher, signed_state)

    @provide(scope=Scope.REQUEST)
    def get_disconnect_notion_use_case(self, uow: IUnitOfWork) -> DisconnectNotionUseCase:
        return DisconnectNotionUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_update_notion_connection_settings_use_case(self, uow: IUnitOfWork) -> UpdateNotionConnectionSettingsUseCase:
        return UpdateNotionConnectionSettingsUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_search_notion_pages_use_case(
        self,
        uow: IUnitOfWork,
        workspace_client: INotionWorkspaceClient,
        token_cipher: ITokenCipher,
    ) -> SearchNotionPagesUseCase:
        return SearchNotionPagesUseCase(uow, workspace_client, token_cipher)

    @provide(scope=Scope.REQUEST)
    def get_import_notion_page_use_case(
        self,
        uow: IUnitOfWork,
        workspace_client: INotionWorkspaceClient,
        token_cipher: ITokenCipher,
        ingest_external_item: IngestExternalItemUseCase,
    ) -> ImportNotionPageUseCase:
        return ImportNotionPageUseCase(uow, workspace_client, token_cipher, ingest_external_item)
