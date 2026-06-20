from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from src.kit.storage.s3_file_storage import S3FileStorage


class _Body:
    def __init__(self, content: bytes) -> None:
        self._content = content
        self.closed = False

    def read(self) -> bytes:
        return self._content

    def close(self) -> None:
        self.closed = True


class _FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []
        self.last_put: dict[str, Any] | None = None

    def put_object(self, **kwargs: Any) -> None:
        key = str(kwargs["Key"])
        body = kwargs["Body"]
        assert isinstance(body, bytes)
        self.objects[key] = body
        self.last_put = kwargs

    def get_object(self, **kwargs: Any) -> dict[str, object]:
        key = str(kwargs["Key"])
        return {"Body": _Body(self.objects[key])}

    def delete_object(self, **kwargs: Any) -> None:
        self.deleted.append(str(kwargs["Key"]))


@pytest.mark.asyncio
async def test_save_document_file_stores_s3_key_only() -> None:
    client = _FakeS3Client()
    storage = S3FileStorage(bucket="conserium-documents", prefix="uploads", client=client)
    user_id = uuid4()

    stored_file = await storage.save_document_file(
        user_id=user_id,
        filename="SQL Basics Advanced.pdf",
        content=b"%PDF-1.4",
    )

    assert stored_file.size_bytes == 8
    assert stored_file.path.startswith(f"uploads/{user_id}/")
    assert stored_file.path.endswith("-SQL_Basics_Advanced.pdf")
    assert not stored_file.path.startswith("s3://")
    assert client.objects[stored_file.path] == b"%PDF-1.4"
    assert client.last_put is not None
    assert client.last_put["Bucket"] == "conserium-documents"


@pytest.mark.asyncio
async def test_read_document_file_reads_s3_key() -> None:
    client = _FakeS3Client()
    storage = S3FileStorage(bucket="conserium-documents", prefix="uploads", client=client)
    client.objects["uploads/user/file.pdf"] = b"pdf"

    assert await storage.read_document_file("uploads/user/file.pdf") == b"pdf"


@pytest.mark.asyncio
async def test_read_document_file_accepts_s3_uri_for_compatibility() -> None:
    client = _FakeS3Client()
    storage = S3FileStorage(bucket="conserium-documents", prefix="uploads", client=client)
    client.objects["uploads/user/file.pdf"] = b"pdf"

    assert await storage.read_document_file("s3://conserium-documents/uploads/user/file.pdf") == b"pdf"


@pytest.mark.asyncio
async def test_delete_document_file_deletes_s3_key() -> None:
    client = _FakeS3Client()
    storage = S3FileStorage(bucket="conserium-documents", prefix="uploads", client=client)

    await storage.delete_document_file("uploads/user/file.pdf")

    assert client.deleted == ["uploads/user/file.pdf"]


def test_s3_file_storage_requires_bucket() -> None:
    with pytest.raises(ValueError, match="AWS_S3_BUCKET"):
        S3FileStorage(bucket="", client=_FakeS3Client())
