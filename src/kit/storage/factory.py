from src.kit.ports.ingestion.file_storage import IFileStorage
from src.kit.storage.local_file_storage import LocalFileStorage
from src.kit.storage.s3_file_storage import S3FileStorage
from src.settings import settings


def build_file_storage() -> IFileStorage:
    storage_type = settings.FILE_STORAGE_TYPE.casefold()
    if storage_type == "s3":
        return S3FileStorage()
    if storage_type == "local":
        return LocalFileStorage()
    raise ValueError(f"Unsupported FILE_STORAGE_TYPE: {settings.FILE_STORAGE_TYPE!r}")
