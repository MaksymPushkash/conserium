from dishka import Provider, Scope, provide

from src.application.ports.cache.document_status_cache import IDocumentStatusCache
from src.application.ports.ingestion.file_storage import IFileStorage
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
from src.application.use_cases.documents.note_use_cases import (
    CreateNoteUseCase,
    DeleteNoteUseCase,
    GetNoteUseCase,
    ListNotesUseCase,
    UpdateNoteUseCase,
)


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
    def get_delete_document_use_case(self, uow: IUnitOfWork, file_storage: IFileStorage) -> DeleteDocumentUseCase:
        return DeleteDocumentUseCase(uow, file_storage)

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

    @provide(scope=Scope.REQUEST)
    def get_create_note_use_case(
        self,
        uow: IUnitOfWork,
        status_cache: IDocumentStatusCache,
        task_dispatcher: ITaskDispatcher,
    ) -> CreateNoteUseCase:
        return CreateNoteUseCase(uow, status_cache, task_dispatcher)

    @provide(scope=Scope.REQUEST)
    def get_list_notes_use_case(self, uow: IUnitOfWork) -> ListNotesUseCase:
        return ListNotesUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_get_note_use_case(self, uow: IUnitOfWork) -> GetNoteUseCase:
        return GetNoteUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_update_note_use_case(
        self,
        uow: IUnitOfWork,
        status_cache: IDocumentStatusCache,
        task_dispatcher: ITaskDispatcher,
    ) -> UpdateNoteUseCase:
        return UpdateNoteUseCase(uow, status_cache, task_dispatcher)

    @provide(scope=Scope.REQUEST)
    def get_delete_note_use_case(self, uow: IUnitOfWork) -> DeleteNoteUseCase:
        return DeleteNoteUseCase(uow)
