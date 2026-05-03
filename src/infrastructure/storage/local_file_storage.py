from __future__ import annotations

import asyncio
import re
import uuid
from pathlib import Path
from uuid import UUID

from src.application.ports.ingestion.file_storage import IFileStorage, StoredFile
from src.core.config import settings

_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


class LocalFileStorage(IFileStorage):
    def __init__(self, root_path: str | Path = settings.LOCAL_STORAGE_PATH) -> None:
        self._root_path = Path(root_path).expanduser().resolve()

    async def save_document_file(
        self,
        *,
        user_id: UUID,
        filename: str,
        content: bytes,
    ) -> StoredFile:
        if not content:
            raise ValueError("uploaded file cannot be empty")

        safe_name = self._safe_filename(filename)
        relative_path = Path(str(user_id)) / f"{uuid.uuid4()}-{safe_name}"
        absolute_path = self._root_path / relative_path

        await asyncio.to_thread(self._write_file, absolute_path, content)
        return StoredFile(path=str(absolute_path), size_bytes=len(content))

    async def read_document_file(self, path: str) -> bytes:
        return await asyncio.to_thread(Path(path).read_bytes)

    async def delete_document_file(self, path: str) -> None:
        await asyncio.to_thread(Path(path).unlink, missing_ok=True)

    @staticmethod
    def _write_file(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    @staticmethod
    def _safe_filename(filename: str) -> str:
        name = Path(filename).name.strip() or "upload.bin"
        return _SAFE_FILENAME_RE.sub("_", name)
