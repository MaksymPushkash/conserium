from src.infrastructure.celery.app import celery_app


def test_celery_declares_all_ingestion_queues() -> None:
    queue_names = {queue.name for queue in celery_app.conf.task_queues}

    assert {
        "document_processing",
        "embeddings",
        "media_processing",
        "hf_processing",
        "notifications",
        "cleanup",
    } <= queue_names


def test_celery_routes_ingestion_tasks_to_expected_queues() -> None:
    routes = celery_app.conf.task_routes

    assert routes["src.infrastructure.celery.tasks.document_ingestion_task.*"]["queue"] == "document_processing"
    assert routes["src.infrastructure.celery.tasks.embedding_tasks.*"]["queue"] == "embeddings"
    assert routes["src.infrastructure.celery.tasks.media_processing_tasks.*"]["queue"] == "media_processing"
    assert routes["src.infrastructure.celery.tasks.enrichment_tasks.*"]["queue"] == "media_processing"
