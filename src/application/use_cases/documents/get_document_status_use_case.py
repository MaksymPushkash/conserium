from uuid import UUID

from src.application.ports.cache.document_status_cache import (
    DocumentProcessingStepDTO,
    DocumentStatusDTO,
    IDocumentStatusCache,
)
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

        status = document.status.value
        progress = 100 if status == "READY" else 0
        message = f"Document status is {status}."
        return DocumentStatusDTO(
            document_id=document.id,
            status=status,
            progress=progress,
            message=message,
            failure_reason=message if status == "FAILED" else None,
            timeline=_fallback_timeline(status, progress, message),
        )


def _fallback_timeline(status: str, progress: int, message: str) -> list[DocumentProcessingStepDTO]:
    steps = [
        ("uploaded", "Uploaded", 0),
        ("extracted", "Extracted", 40),
        ("embedded", "Embedded", 90),
        ("enriched", "Enriched", 95),
        ("ready", "Ready", 100),
    ]
    return [
        DocumentProcessingStepDTO(
            key=key,
            label=label,
            state=_fallback_step_state(status, progress, threshold),
            progress=threshold,
            message=message if status == "FAILED" and progress < threshold else None,
        )
        for key, label, threshold in steps
    ]


def _fallback_step_state(status: str, progress: int, threshold: int) -> str:
    if status == "FAILED" and progress < threshold:
        return "failed"
    if status == "READY" or progress >= threshold:
        return "complete"
    return "pending"
