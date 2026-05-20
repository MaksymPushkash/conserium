from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class NotionOAuthToken:
    access_token: str
    workspace_id: str | None
    workspace_name: str | None
    bot_id: str | None
    owner: dict[str, Any] | None


class INotionOAuthClient(ABC):
    @abstractmethod
    def authorization_url(self, *, redirect_uri: str, state: str) -> str: ...

    @abstractmethod
    async def exchange_code(self, *, code: str, redirect_uri: str) -> NotionOAuthToken: ...
