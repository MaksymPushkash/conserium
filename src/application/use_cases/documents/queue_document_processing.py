from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.ports.cache.document_status_cache import IDocumentStatusCache
    from src.application.ports.ingestion.task_dispatcher import ITaskDispatcher
    from src.application.ports.persistence.unit_of_work import IUnitOfWork
    from src.domain.entities.document_entity import DocumentEntity


async def queue_document_processing(
    *,
    document: DocumentEntity,
    uow: IUnitOfWork,
    status_cache: IDocumentStatusCache,
    task_dispatcher: ITaskDispatcher,
    message: str,
) -> None:
    document.mark_queued()
    async with uow:
        await uow.document_repo.update(document)
        await uow.commit()

    await status_cache.set_status(
        document.id,
        status="QUEUED",
        progress=0,
        message=message,
    )

    try:
        await task_dispatcher.dispatch_process_document(str(document.id))
    except Exception:
        document.mark_failed()
        try:
            async with uow:
                await uow.document_repo.update(document)
                await uow.commit()
        finally:
            with suppress(Exception):
                await status_cache.set_status(
                    document.id,
                    status="FAILED",
                    progress=0,
                    message="Failed to queue document for processing.",
                )
        raise
