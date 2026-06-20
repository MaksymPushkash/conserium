from pathlib import Path
from uuid import uuid4

import pytest

from src.kit.storage.local_file_storage import LocalFileStorage


@pytest.mark.asyncio
async def test_save_document_file_returns_absolute_path(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path / "storage")

    stored_file = await storage.save_document_file(
        user_id=uuid4(),
        filename="SQL Basics Advanced.pdf",
        content=b"%PDF-1.4",
    )

    assert stored_file.size_bytes == 8
    assert stored_file.path.startswith(str(tmp_path))
    assert await storage.read_document_file(stored_file.path) == b"%PDF-1.4"


@pytest.mark.asyncio
async def test_save_document_file_sanitizes_filename(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path / "storage")

    stored_file = await storage.save_document_file(
        user_id=uuid4(),
        filename="../bad name.pdf",
        content=b"content",
    )

    assert ".." not in stored_file.path
    assert "bad_name.pdf" in stored_file.path
