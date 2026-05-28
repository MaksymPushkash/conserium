from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

from src.application.use_cases.documents.document_processing_outbox import (
    DOCUMENT_PROCESSING_TASK_NAME,
    kick_document_processing_outbox_item,
)

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
        outbox = await uow.document_processing_outbox_repo.create_outbox(
            document_id=document.id,
            task_name=DOCUMENT_PROCESSING_TASK_NAME,
        )
        await uow.commit()

    with suppress(Exception):
        await status_cache.set_status(
            document.id,
            status="QUEUED",
            progress=0,
            message=message,
        )

    with suppress(Exception):
        await kick_document_processing_outbox_item(
            outbox_id=outbox.id,
            document_id=document.id,
            uow=uow,
            task_dispatcher=task_dispatcher,
        )
