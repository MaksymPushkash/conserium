from typing import Any

import httpx

from src.application.dtos.external_connection_dtos import NotionPageContentDTO, NotionPageDTO
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

    async def get_page_markdown(self, *, access_token: str, page_id: str) -> NotionPageContentDTO:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                page_response = await client.get(
                    f"{_NOTION_API_BASE_URL}/pages/{page_id}",
                    headers=notion_headers(access_token),
                )
                page_response.raise_for_status()
                blocks = await fetch_block_children(client=client, access_token=access_token, block_id=page_id)
        except httpx.HTTPStatusError as exc:
            raise IntegrationRequestException("notion rejected the page import request") from exc
        except httpx.HTTPError as exc:
            raise IntegrationRequestException("notion page import request failed") from exc

        page_payload = page_response.json()
        title = notion_page_title(page_payload) or "Untitled"
        markdown = notion_blocks_to_markdown(blocks)
        return NotionPageContentDTO(id=page_id, title=title, markdown=markdown or f"# {title}\n")


def notion_page_from_payload(payload: Any) -> NotionPageDTO | None:
    if not isinstance(payload, dict) or payload.get("object") != "page":
        return None
    page_id = payload.get("id")
    if not isinstance(page_id, str):
        return None
    return NotionPageDTO(id=page_id, title=notion_page_title(payload) or "Untitled")


def notion_headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Notion-Version": _NOTION_VERSION,
    }


async def fetch_block_children(*, client: httpx.AsyncClient, access_token: str, block_id: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        params: dict[str, str | int] = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor
        response = await client.get(
            f"{_NOTION_API_BASE_URL}/blocks/{block_id}/children",
            headers=notion_headers(access_token),
            params=params,
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results")
        if isinstance(results, list):
            blocks.extend(item for item in results if isinstance(item, dict))
        if not payload.get("has_more") or not isinstance(payload.get("next_cursor"), str):
            return blocks
        cursor = payload["next_cursor"]


def notion_blocks_to_markdown(blocks: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for block in blocks:
        text = block_plain_text(block)
        if not text:
            continue
        block_type = block.get("type")
        if block_type == "heading_1":
            lines.append(f"# {text}")
        elif block_type == "heading_2":
            lines.append(f"## {text}")
        elif block_type == "heading_3":
            lines.append(f"### {text}")
        elif block_type == "bulleted_list_item":
            lines.append(f"- {text}")
        elif block_type == "numbered_list_item":
            lines.append(f"1. {text}")
        elif block_type == "quote":
            lines.append(f"> {text}")
        elif block_type == "code":
            language = block.get("code", {}).get("language", "") if isinstance(block.get("code"), dict) else ""
            lines.append(f"```{language}\n{text}\n```")
        else:
            lines.append(text)
    return "\n\n".join(lines).strip()


def block_plain_text(block: dict[str, Any]) -> str:
    block_type = block.get("type")
    value = block.get(block_type) if isinstance(block_type, str) else None
    if not isinstance(value, dict):
        return ""
    rich_text = value.get("rich_text")
    if not isinstance(rich_text, list):
        return ""
    return "".join(
        item.get("plain_text", "")
        for item in rich_text
        if isinstance(item, dict) and isinstance(item.get("plain_text"), str)
    ).strip()


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
