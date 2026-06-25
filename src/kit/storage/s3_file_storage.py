from __future__ import annotations

import asyncio
import re
import uuid
from pathlib import Path
from typing import Any
from uuid import UUID

from src.kit.storage.file_storage import FileStorage, StoredFile
from src.settings import settings

_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


class S3FileStorage(FileStorage):
    def __init__(
        self,
        *,
        bucket: str = settings.AWS_S3_BUCKET,
        prefix: str = settings.AWS_S3_PREFIX,
        region_name: str = settings.AWS_REGION,
        client: Any | None = None,
    ) -> None:
        if not bucket:
            raise ValueError("AWS_S3_BUCKET is required when FILE_STORAGE_TYPE=s3")

        self._bucket = bucket
        self._prefix = _normalize_prefix(prefix)
        self._client = client or _build_s3_client(region_name)

    async def save_document_file(
        self,
        *,
        user_id: UUID,
        filename: str,
        content: bytes,
    ) -> StoredFile:
        if not content:
            raise ValueError("uploaded file cannot be empty")

        key = self._build_key(user_id=user_id, filename=filename)
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=content,
            ContentType="application/octet-stream",
        )
        return StoredFile(path=key, size_bytes=len(content))

    async def read_document_file(self, path: str) -> bytes:
        key = self._normalize_key(path)
        response = await asyncio.to_thread(self._client.get_object, Bucket=self._bucket, Key=key)
        body = response["Body"]
        try:
            return await asyncio.to_thread(body.read)
        finally:
            close = getattr(body, "close", None)
            if callable(close):
                close()

    async def delete_document_file(self, path: str) -> None:
        key = self._normalize_key(path)
        await asyncio.to_thread(self._client.delete_object, Bucket=self._bucket, Key=key)

    def _build_key(self, *, user_id: UUID, filename: str) -> str:
        safe_name = self._safe_filename(filename)
        relative_key = f"{user_id}/{uuid.uuid4()}-{safe_name}"
        if self._prefix:
            return f"{self._prefix}/{relative_key}"
        return relative_key

    def _normalize_key(self, path: str) -> str:
        if path.startswith(f"s3://{self._bucket}/"):
            return path.removeprefix(f"s3://{self._bucket}/")
        return path.lstrip("/")

    @staticmethod
    def _safe_filename(filename: str) -> str:
        name = Path(filename).name.strip() or "upload.bin"
        return _SAFE_FILENAME_RE.sub("_", name)


def _normalize_prefix(prefix: str) -> str:
    return prefix.strip().strip("/")


def _build_s3_client(region_name: str) -> Any:
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("boto3 is required when FILE_STORAGE_TYPE=s3") from exc

    return boto3.client("s3", region_name=region_name)
