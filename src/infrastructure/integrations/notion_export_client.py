from typing import Any

import httpx

from src.application.ports.integrations.notion_export_client import INotionExportClient
from src.core.config import settings
from src.domain.exceptions import IntegrationConfigurationException, IntegrationRequestException

_NOTION_API_BASE_URL = "https://api.notion.com/v1"
_NOTION_VERSION = "2022-06-28"


class NotionExportClient(INotionExportClient):
    def __init__(self, token: str | None = None, parent_page_id: str | None = None) -> None:
        self._token = token if token is not None else settings.NOTION_API_TOKEN
        self._parent_page_id = parent_page_id if parent_page_id is not None else settings.NOTION_PARENT_PAGE_ID

    async def create_markdown_page(
        self,
        *,
        title: str,
        markdown: str,
        parent_page_id: str | None = None,
        access_token: str | None = None,
    ) -> tuple[str, str | None]:
        token = access_token or self._token
        parent_id = parent_page_id or self._parent_page_id
        if not token or not parent_id:
            raise IntegrationConfigurationException("notion export is not configured")

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    f"{_NOTION_API_BASE_URL}/pages",
                    headers=self._headers(token),
                    json={
                        "parent": {"page_id": parent_id},
                        "properties": {
                            "title": {
                                "title": [{"type": "text", "text": {"content": title[:2000]}}],
                            }
                        },
                        "children": markdown_to_notion_blocks(markdown),
                    },
                )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise IntegrationRequestException("notion rejected the export request") from exc
        except httpx.HTTPError as exc:
            raise IntegrationRequestException("notion export request failed") from exc
        payload = response.json()
        return str(payload["id"]), payload.get("url") if isinstance(payload.get("url"), str) else None

    def _headers(self, token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": _NOTION_VERSION,
        }


def markdown_to_notion_blocks(markdown: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        block_type, content = notion_block_type(line)
        blocks.append(
            {
                "object": "block",
                "type": block_type,
                block_type: {"rich_text": [{"type": "text", "text": {"content": content[:2000]}}]},
            }
        )
        if len(blocks) == 100:
            break
    return blocks or [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": " "}}]},
        }
    ]


def notion_block_type(line: str) -> tuple[str, str]:
    if line.startswith("# "):
        return "heading_1", line[2:].strip()
    if line.startswith("## "):
        return "heading_2", line[3:].strip()
    if line.startswith("### "):
        return "heading_3", line[4:].strip()
    if line.startswith("- "):
        return "bulleted_list_item", line[2:].strip()
    return "paragraph", line
