from dishka import Provider, Scope, provide

from src.application.ports.cache.document_status_cache import IDocumentStatusCache
from src.application.ports.ingestion.task_dispatcher import ITaskDispatcher
from src.application.ports.ingestion.text_chunker import ITextChunker
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.documents.create_document_use_case import CreateDocumentUseCase
from src.application.use_cases.documents.delete_document_use_case import DeleteDocumentUseCase
from src.application.use_cases.documents.get_document_status_use_case import GetDocumentStatusUseCase
from src.application.use_cases.documents.get_document_use_case import GetDocumentUseCase
from src.application.use_cases.documents.ingest_document_use_case import IngestDocumentUseCase
from src.application.use_cases.documents.ingest_text_document_use_case import IngestTextDocumentUseCase
from src.application.use_cases.documents.list_documents_use_case import ListDocumentsUseCase


class DocumentsProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_create_document_use_case(self, uow: IUnitOfWork) -> CreateDocumentUseCase:
        return CreateDocumentUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_list_documents_use_case(self, uow: IUnitOfWork) -> ListDocumentsUseCase:
        return ListDocumentsUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_get_document_use_case(self, uow: IUnitOfWork) -> GetDocumentUseCase:
        return GetDocumentUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_delete_document_use_case(self, uow: IUnitOfWork) -> DeleteDocumentUseCase:
        return DeleteDocumentUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_ingest_document_use_case(
        self,
        uow: IUnitOfWork,
        status_cache: IDocumentStatusCache,
        task_dispatcher: ITaskDispatcher,
    ) -> IngestDocumentUseCase:
        return IngestDocumentUseCase(uow, status_cache, task_dispatcher)

    @provide(scope=Scope.REQUEST)
    def get_document_status_use_case(
        self,
        uow: IUnitOfWork,
        status_cache: IDocumentStatusCache,
    ) -> GetDocumentStatusUseCase:
        return GetDocumentStatusUseCase(uow, status_cache)

    @provide(scope=Scope.REQUEST)
    def get_ingest_text_document_use_case(
        self,
        uow: IUnitOfWork,
        text_chunker: ITextChunker,
    ) -> IngestTextDocumentUseCase:
        return IngestTextDocumentUseCase(uow, text_chunker)
