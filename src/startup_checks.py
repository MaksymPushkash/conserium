from src.models.chunk import ChunkModel
from src.settings import settings


def validate_startup_settings() -> None:
    if settings.OPENAI_EMBEDDING_DIMENSIONS != ChunkModel.EMBEDDING_DIMENSIONS:
        raise RuntimeError(
            "OPENAI_EMBEDDING_DIMENSIONS must match "
            f"ChunkModel.EMBEDDING_DIMENSIONS ({ChunkModel.EMBEDDING_DIMENSIONS})"
        )
    if not settings.DEBUG and not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY must be set when DEBUG is false")
    storage_type = settings.FILE_STORAGE_TYPE.casefold()
    if storage_type not in {"local", "s3"}:
        raise RuntimeError("FILE_STORAGE_TYPE must be either 'local' or 's3'")
    if storage_type == "s3" and not settings.AWS_S3_BUCKET:
        raise RuntimeError("AWS_S3_BUCKET must be set when FILE_STORAGE_TYPE=s3")
    if not settings.TASKIQ_BROKER_URL.startswith(("amqp://", "amqps://")):
        raise RuntimeError("TASKIQ_BROKER_URL must be an amqp:// or amqps:// RabbitMQ URL")
    if not settings.TASKIQ_RESULT_BACKEND_URL.startswith(("redis://", "rediss://", "unix://")):
        raise RuntimeError("TASKIQ_RESULT_BACKEND_URL must be a Redis URL")
    if (settings.NOTION_CLIENT_ID or settings.NOTION_CLIENT_SECRET) and not settings.TOKEN_ENCRYPTION_KEY:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY must be set when Notion OAuth is configured")
    if settings.TOKEN_ENCRYPTION_KEY and not settings.TOKEN_ENCRYPTION_KEY_VERSION.strip():
        raise RuntimeError("TOKEN_ENCRYPTION_KEY_VERSION must be set when TOKEN_ENCRYPTION_KEY is set")
