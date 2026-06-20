
from src.documents.tasks import enrich_document_task
from src.worker.task_names import DOCUMENT_ENRICH_TASK


def test_enrich_document_task_structure() -> None:
    assert enrich_document_task.name == DOCUMENT_ENRICH_TASK
    assert enrich_document_task.queue == "media_processing"
