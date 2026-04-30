from src.application.ports.ingestion.task_dispatcher import ITaskDispatcher
from src.infrastructure.celery.app import celery_app

_PROCESS_DOCUMENT_TASK = "src.infrastructure.celery.tasks.document_processing.process_document"


class CeleryTaskDispatcher(ITaskDispatcher):
    async def dispatch_process_document(self, document_id: str) -> None:
        celery_app.send_task(
            _PROCESS_DOCUMENT_TASK,
            args=[document_id],
            queue="document_processing",
            routing_key="document_processing",
        )
