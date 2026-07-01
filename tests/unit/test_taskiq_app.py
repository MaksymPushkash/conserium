import pytest

from src.worker.app import QUEUE_NAMES, TASK_QUEUES, TASK_SCHEDULES, taskiq_broker
from src.worker.task_names import (
    DOCUMENT_EMBED_AND_FINALIZE_TASK,
    DOCUMENT_ENRICH_TASK,
    DOCUMENT_PROCESS_IMAGE_TASK,
    DOCUMENT_PROCESS_TASK,
    REPO_SYNC_RUN_DUE_TASK,
)


def test_taskiq_declares_all_ingestion_queues() -> None:
    queue_names = {queue.name for queue in TASK_QUEUES}

    assert set(QUEUE_NAMES) == queue_names
    assert {
        "document_processing",
        "embeddings",
        "media_processing",
        "hf_processing",
        "notifications",
        "cleanup",
    } <= queue_names


def test_taskiq_routes_ingestion_tasks_to_expected_queues() -> None:
    import src.documents.tasks
    import src.repo_syncs.tasks  # noqa: F401

    tasks = taskiq_broker.get_all_tasks()

    assert tasks[DOCUMENT_PROCESS_TASK].labels["queue_name"] == "document_processing"
    assert tasks[DOCUMENT_EMBED_AND_FINALIZE_TASK].labels["queue_name"] == "embeddings"
    assert tasks[DOCUMENT_PROCESS_IMAGE_TASK].labels["queue_name"] == "media_processing"
    assert tasks[DOCUMENT_ENRICH_TASK].labels["queue_name"] == "media_processing"
    assert tasks[REPO_SYNC_RUN_DUE_TASK].labels["queue_name"] == "cleanup"


@pytest.mark.asyncio
async def test_proactive_notification_tasks_are_not_scheduled_by_default() -> None:
    from taskiq.schedule_sources import LabelScheduleSource

    import src.documents.tasks
    import src.notifications.tasks
    import src.repo_syncs.tasks  # noqa: F401

    source = LabelScheduleSource(taskiq_broker)
    await source.startup()
    schedule_ids = {task.schedule_id for task in await source.get_schedules()}

    assert set(TASK_SCHEDULES) <= schedule_ids
    assert "deliver-daily-digest-notifications" not in schedule_ids
    assert "deliver-weekly-report-notifications" not in schedule_ids
    assert "deliver-learning-goal-reminder-notifications" not in schedule_ids
