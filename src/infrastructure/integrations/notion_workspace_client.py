from typing import Any

import httpx

from src.application.dtos.external_connection_dtos import NotionPageDTO
from src.application.ports.integrations.notion_workspace_client import INotionWorkspaceClient
from src.domain.exceptions import IntegrationRequestException

_NOTION_API_BASE_URL = "https://api.notion.com/v1"
_NOTION_VERSION = "2022-06-28"


class NotionWorkspaceClient(INotionWorkspaceClient):
    async def search_pages(self, *, access_token: str, query: str | None, limit: int) -> list[NotionPageDTO]:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    f"{_NOTION_API_BASE_URL}/search",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                        "Notion-Version": _NOTION_VERSION,
                    },
                    json={
                        "query": query or "",
                        "filter": {"property": "object", "value": "page"},
                        "page_size": max(1, min(limit, 25)),
                    },
                )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise IntegrationRequestException("notion rejected the page search request") from exc
        except httpx.HTTPError as exc:
            raise IntegrationRequestException("notion page search request failed") from exc

        payload = response.json()
        results = payload.get("results")
        if not isinstance(results, list):
            return []
        return [page for item in results if (page := notion_page_from_payload(item)) is not None]


def notion_page_from_payload(payload: Any) -> NotionPageDTO | None:
    if not isinstance(payload, dict) or payload.get("object") != "page":
        return None
    page_id = payload.get("id")
    if not isinstance(page_id, str):
        return None
    return NotionPageDTO(id=page_id, title=notion_page_title(payload) or "Untitled")


def notion_page_title(payload: dict[str, Any]) -> str | None:
    properties = payload.get("properties")
    if not isinstance(properties, dict):
        return None
    for value in properties.values():
        if not isinstance(value, dict) or value.get("type") != "title":
            continue
        title_items = value.get("title")
        if not isinstance(title_items, list):
            continue
        title = "".join(
            item.get("plain_text", "")
            for item in title_items
            if isinstance(item, dict) and isinstance(item.get("plain_text"), str)
        ).strip()
        if title:
            return title[:200]
    return None
