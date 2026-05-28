"""Import an Anytype Markdown export directory into Conserium through webhooks.

Usage:

    CONSERIUM_API_BASE_URL=https://api.conserium.app/api/v1 \
    CONSERIUM_API_KEY=ctx_... \
    uv run python scripts/import_anytype_export.py /path/to/anytype/export
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

import httpx


async def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: import_anytype_export.py /path/to/anytype/export")
    root = Path(sys.argv[1]).expanduser()
    if not root.is_dir():
        raise SystemExit(f"not a directory: {root}")

    api_base = os.environ["CONSERIUM_API_BASE_URL"].rstrip("/")
    api_key = os.environ["CONSERIUM_API_KEY"]
    markdown_files = sorted(path for path in root.rglob("*.md") if path.is_file())
    async with httpx.AsyncClient(timeout=30) as client:
        for path in markdown_files:
            payload = anytype_payload(root=root, path=path)
            response = await client.post(
                f"{api_base}/webhooks/ingest",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            response.raise_for_status()
            print(f"queued {path.relative_to(root)}")


def anytype_payload(*, root: Path, path: Path) -> dict[str, Any]:
    relative = path.relative_to(root).as_posix()
    return {
        "provider": "anytype",
        "external_id": relative,
        "idempotency_key": f"anytype:{relative}",
        "title": path.stem,
        "type": "MARKDOWN",
        "raw_content": path.read_text(encoding="utf-8"),
        "tags": ["anytype"],
        "metadata": {"relative_path": relative},
    }


if __name__ == "__main__":
    asyncio.run(main())
