from uuid import UUID

from src.application.ports.cache.document_status_cache import DocumentStatusDTO, IDocumentStatusCache
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.domain.exceptions import DocumentNotFoundException


class GetDocumentStatusUseCase:
    def __init__(self, uow: IUnitOfWork, status_cache: IDocumentStatusCache) -> None:
        self._uow = uow
        self._status_cache = status_cache

    async def __call__(self, document_id: UUID, user_id: UUID) -> DocumentStatusDTO:
        async with self._uow:
            document = await self._uow.document_repo.get_by_id(document_id)

        if document is None or document.user_id != user_id:
            raise DocumentNotFoundException("document not found")

        cached = await self._status_cache.get_status(document.id)
        if cached is not None:
            return cached

        return DocumentStatusDTO(
            document_id=document.id,
            status=document.status.value,
            progress=100 if document.status.value == "READY" else 0,
            message=f"Document status is {document.status.value}.",
        )
