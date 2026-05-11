from src.application.dtos.document_dtos import DocumentDTO, RetryDocumentDTO
from src.application.ports.cache.document_status_cache import IDocumentStatusCache
from src.application.ports.ingestion.task_dispatcher import ITaskDispatcher
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.documents.base import document_to_dto, ensure_document_owner
from src.application.use_cases.documents.queue_document_processing import queue_document_processing
from src.domain.exceptions import DocumentNotFoundException, DocumentValidationException
from src.domain.value_objects.document_status import DocumentStatus


class RetryDocumentUseCase:
    def __init__(
        self,
        uow: IUnitOfWork,
        status_cache: IDocumentStatusCache,
        task_dispatcher: ITaskDispatcher,
    ) -> None:
        self._uow = uow
        self._status_cache = status_cache
        self._task_dispatcher = task_dispatcher

    async def __call__(self, dto: RetryDocumentDTO) -> DocumentDTO:
        async with self._uow:
            document = await self._uow.document_repo.get_by_id(dto.document_id)

        if document is None:
            raise DocumentNotFoundException("document not found")
        ensure_document_owner(document, dto.user_id)
        if document.status != DocumentStatus.FAILED:
            raise DocumentValidationException("only failed documents can be retried")

        await queue_document_processing(
            document=document,
            uow=self._uow,
            status_cache=self._status_cache,
            task_dispatcher=self._task_dispatcher,
            message="Queued retry for failed document.",
        )
        return document_to_dto(document)
