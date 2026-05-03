
from src.infrastructure.celery.tasks.enrichment import enrich_document_task


def test_enrich_document_task_structure() -> None:
    assert enrich_document_task.name == "src.infrastructure.celery.tasks.enrichment.enrich_document_task"
    assert enrich_document_task.queue == "hf_processing"
