from src.core.config import settings
from src.domain.entities.chunk_entity import ChunkEntity


def validate_startup_settings() -> None:
    if settings.OPENAI_EMBEDDING_DIMENSIONS != ChunkEntity.EMBEDDING_DIMENSIONS:
        raise RuntimeError(
            "OPENAI_EMBEDDING_DIMENSIONS must match "
            f"ChunkEntity.EMBEDDING_DIMENSIONS ({ChunkEntity.EMBEDDING_DIMENSIONS})"
        )
    if not settings.DEBUG and not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY must be set when DEBUG is false")
    storage_type = settings.FILE_STORAGE_TYPE.casefold()
    if storage_type not in {"local", "s3"}:
        raise RuntimeError("FILE_STORAGE_TYPE must be either 'local' or 's3'")
    if storage_type == "s3" and not settings.AWS_S3_BUCKET:
        raise RuntimeError("AWS_S3_BUCKET must be set when FILE_STORAGE_TYPE=s3")
