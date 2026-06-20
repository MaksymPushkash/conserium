from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI

from src.auth.jwt_service import JWTServiceProtocol
from src.auth.service import (
    AuthSessionService,
    OAuthLoginCompleter,
    RefreshTokenRotator,
    UserAuthenticator,
    UserRegistrar,
    get_auth_session_service,
    get_jwt_service,
    get_oauth_login_completer,
    get_refresh_token_rotator,
    get_user_authenticator,
    get_user_registrar,
    get_user_repository,
)
from src.collections.endpoints import get_collection_service as get_collection_endpoint_service
from src.collections.service import CollectionService
from src.documents.exports import DocumentExporter, NotionMarkdownExporter, get_document_exporter
from src.documents.ingestion import (
    DocumentIngester,
    DocumentReprocessor,
    DocumentRetryer,
    ExternalIntakeService,
    ExternalItemIngester,
    get_document_ingester,
    get_document_reprocessor,
    get_document_retryer,
    get_external_intake_service,
    get_external_item_ingester,
)
from src.documents.notes import (
    NoteService,
    get_note_service,
)
from src.documents.service import DocumentStatusService
from src.exports.dependencies import get_notion_markdown_exporter
from src.ingestion.service import get_document_ingester as get_ingestion_document_ingester
from src.ingestion.service import get_document_status_service as get_ingestion_document_status_service
from src.ingestion.service import get_file_storage
from src.integrations.dependencies import get_api_key_authenticator, get_notion_workspace_service
from src.integrations.service import ApiKeyAuthenticator, NotionWorkspaceService
from src.kit.ports.ingestion.file_storage import IFileStorage
from src.public_api.endpoints import get_collection_service as get_public_api_collection_service
from src.query.service import QueryExecutor, StreamQueryExecutor, get_query_executor, get_stream_query_executor
from src.users.repository import UserRepository

_DEPENDENCY_BY_TYPE: dict[type[object], Any] = {
    JWTServiceProtocol: get_jwt_service,
    UserRepository: get_user_repository,
    IFileStorage: get_file_storage,
    UserRegistrar: get_user_registrar,
    UserAuthenticator: get_user_authenticator,
    RefreshTokenRotator: get_refresh_token_rotator,
    AuthSessionService: get_auth_session_service,
    OAuthLoginCompleter: get_oauth_login_completer,
    DocumentExporter: get_document_exporter,
    DocumentRetryer: get_document_retryer,
    DocumentReprocessor: get_document_reprocessor,
    NoteService: get_note_service,
    DocumentIngester: get_document_ingester,
    DocumentStatusService: get_ingestion_document_status_service,
    ApiKeyAuthenticator: get_api_key_authenticator,
    ExternalItemIngester: get_external_item_ingester,
    ExternalIntakeService: get_external_intake_service,
    CollectionService: get_collection_endpoint_service,
    QueryExecutor: get_query_executor,
    StreamQueryExecutor: get_stream_query_executor,
    NotionMarkdownExporter: get_notion_markdown_exporter,
    NotionWorkspaceService: get_notion_workspace_service,
}

_ADDITIONAL_DEPENDENCIES_BY_TYPE: dict[type[object], tuple[Any, ...]] = {
    DocumentIngester: (get_ingestion_document_ingester,),
    DocumentStatusService: (get_ingestion_document_status_service,),
    CollectionService: (get_public_api_collection_service,),
}


def apply_dependency_overrides(app: FastAPI, dependencies: Mapping[type[object], object]) -> None:
    for dependency_type, dependency in dependencies.items():
        dependency_factory = _DEPENDENCY_BY_TYPE.get(dependency_type)
        if dependency_factory is not None:
            if dependency_type is UserRepository and hasattr(dependency, "user_repo"):
                dependency = dependency.user_repo
            app.dependency_overrides[dependency_factory] = _dependency_override(dependency)
        for additional_factory in _ADDITIONAL_DEPENDENCIES_BY_TYPE.get(dependency_type, ()):
            app.dependency_overrides[additional_factory] = _dependency_override(dependency)


def _dependency_override(dependency: object) -> Any:
    def override() -> object:
        return dependency

    return override
