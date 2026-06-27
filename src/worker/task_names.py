DOCUMENT_PROCESS_TASK = "src.documents.tasks.process_document"
DOCUMENT_ENRICH_TASK = "src.documents.tasks.enrich_document_task"
DOCUMENT_EMBED_AND_FINALIZE_TASK = "src.documents.tasks.embed_and_finalize_document"
DOCUMENT_PROCESS_IMAGE_TASK = "src.documents.tasks.process_image_document"
DOCUMENT_PROCESSING_OUTBOX_DRAIN_TASK = "src.documents.tasks.drain_document_processing_outbox_task"

REPO_SYNC_RUN_DUE_TASK = "src.repo_syncs.tasks.run_due_repo_syncs_task"
REPO_SYNC_RUN_TASK = "src.repo_syncs.tasks.run_repo_sync_task"
REPO_SYNC_OUTBOX_DRAIN_TASK = "src.repo_syncs.tasks.drain_repo_sync_outbox_task"

NOTIFICATION_DAILY_DIGEST_TASK = "src.notifications.tasks.deliver_daily_digest_notifications_task"
NOTIFICATION_WEEKLY_REPORT_TASK = "src.notifications.tasks.deliver_weekly_report_notifications_task"
NOTIFICATION_LEARNING_GOAL_REMINDER_TASK = "src.notifications.tasks.deliver_learning_goal_reminder_notifications_task"
