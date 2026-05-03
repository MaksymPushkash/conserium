from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID


class IDocumentTagSync(ABC):
    @abstractmethod
    async def sync_auto_tags(
        self,
        *,
        user_id: UUID,
        document_id: UUID,
        tag_names: list[str],
    ) -> list[str]:
        """Replace auto-generated tags for a document while preserving manual tags."""
