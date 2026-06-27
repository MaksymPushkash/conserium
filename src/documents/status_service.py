from __future__ import annotations

from typing import TYPE_CHECKING

from src.documents.schemas import DocumentProcessingStepResponse, DocumentStatusResponse
from src.documents.status_cache import DocumentProcessingStep, DocumentStatusSnapshot
from src.kit.exceptions import DocumentNotFoundException

if TYPE_CHECKING:
    from uuid import UUID

    from src.documents.document_repository import DocumentRepository
    from src.documents.status_cache import RedisDocumentStatusCache


class DocumentStatusService:
    def __init__(self, document_repo: DocumentRepository, status_cache: RedisDocumentStatusCache) -> None:
        self._document_repo = document_repo
        self._status_cache = status_cache

    async def get(self, document_id: UUID, user_id: UUID) -> DocumentStatusSnapshot:
        document = await self._document_repo.get_by_id(document_id)

        if document is None or document.user_id != user_id:
            raise DocumentNotFoundException("document not found")

        cached = await self._status_cache.get_status(document.id)
        if cached is not None:
            return cached

        status = document.status.value
        progress = 100 if status == "READY" else 0
        message = f"Document status is {status}."
        return DocumentStatusSnapshot(
            document_id=document.id,
            status=status,
            progress=progress,
            message=message,
            failure_reason=message if status == "FAILED" else None,
            timeline=_fallback_timeline(status, progress, message),
        )


def to_document_status_response(dto: DocumentStatusSnapshot) -> DocumentStatusResponse:
    return DocumentStatusResponse(
        document_id=dto.document_id,
        status=dto.status,
        progress=dto.progress,
        message=dto.message,
        failure_reason=dto.failure_reason,
        timeline=[
            DocumentProcessingStepResponse(
                key=step.key,
                label=step.label,
                state=step.state,
                progress=step.progress,
                message=step.message,
            )
            for step in dto.timeline or []
        ],
    )


def _fallback_timeline(status: str, progress: int, message: str) -> list[DocumentProcessingStep]:
    steps = [
        ("uploaded", "Uploaded", 0),
        ("extracted", "Extracted", 40),
        ("embedded", "Embedded", 90),
        ("enriched", "Enriched", 95),
        ("ready", "Ready", 100),
    ]
    return [
        DocumentProcessingStep(
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


__all__ = ["DocumentStatusService", "to_document_status_response"]
