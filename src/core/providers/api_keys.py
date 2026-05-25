from dishka import Provider, Scope, provide

from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.api_keys import (
    AuthenticateApiKeyUseCase,
    CreateApiKeyUseCase,
    ListApiKeysUseCase,
    RevokeApiKeyUseCase,
)
from src.application.use_cases.documents.ingest_document_use_case import IngestDocumentUseCase
from src.application.use_cases.external_intake import IngestExternalItemUseCase


class ApiKeysProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_create_api_key_use_case(self, uow: IUnitOfWork) -> CreateApiKeyUseCase:
        return CreateApiKeyUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_list_api_keys_use_case(self, uow: IUnitOfWork) -> ListApiKeysUseCase:
        return ListApiKeysUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_revoke_api_key_use_case(self, uow: IUnitOfWork) -> RevokeApiKeyUseCase:
        return RevokeApiKeyUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_authenticate_api_key_use_case(self, uow: IUnitOfWork) -> AuthenticateApiKeyUseCase:
        return AuthenticateApiKeyUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_ingest_external_item_use_case(
        self,
        uow: IUnitOfWork,
        ingest_document: IngestDocumentUseCase,
    ) -> IngestExternalItemUseCase:
        return IngestExternalItemUseCase(uow, ingest_document)
