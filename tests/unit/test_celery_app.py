from src.worker.app import celery_app
from src.worker.task_names import (
    DOCUMENT_EMBED_AND_FINALIZE_TASK,
    DOCUMENT_ENRICH_TASK,
    DOCUMENT_PROCESS_IMAGE_TASK,
    DOCUMENT_PROCESS_TASK,
    REPO_SYNC_RUN_DUE_TASK,
)


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

    assert routes[DOCUMENT_PROCESS_TASK]["queue"] == "document_processing"
    assert routes[DOCUMENT_EMBED_AND_FINALIZE_TASK]["queue"] == "embeddings"
    assert routes[DOCUMENT_PROCESS_IMAGE_TASK]["queue"] == "media_processing"
    assert routes[DOCUMENT_ENRICH_TASK]["queue"] == "media_processing"
    assert routes[REPO_SYNC_RUN_DUE_TASK]["queue"] == "cleanup"


def test_proactive_notification_tasks_are_not_scheduled_by_default() -> None:
    schedule = celery_app.conf.beat_schedule

    assert "deliver-daily-digest-notifications" not in schedule
    assert "deliver-weekly-report-notifications" not in schedule
    assert "deliver-learning-goal-reminder-notifications" not in schedule
