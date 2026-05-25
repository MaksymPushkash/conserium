from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, final

if TYPE_CHECKING:
    from uuid import UUID


@final
@dataclass(frozen=True, slots=True)
class ExternalConnectionDTO:
    id: UUID
    user_id: UUID
    provider: str
    workspace_id: str | None
    workspace_name: str | None
    access_token_encrypted: str
    bot_id: str | None
    owner: dict[str, Any] | None
    default_parent_page_id: str | None
    default_parent_page_title: str | None


@final
@dataclass(frozen=True, slots=True)
class NotionConnectionDTO:
    connected: bool
    workspace_id: str | None = None
    workspace_name: str | None = None
    bot_id: str | None = None
    default_parent_page_id: str | None = None
    default_parent_page_title: str | None = None


@dataclass(frozen=True, slots=True)
class NotionPageDTO:
    id: str
    title: str


@dataclass(frozen=True, slots=True)
class NotionPageContentDTO:
    id: str
    title: str
    markdown: str
