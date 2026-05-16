from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID


class IDocumentTopicSync(ABC):
    @abstractmethod
    async def sync_topics(
        self,
        *,
        user_id: UUID,
        document_id: UUID,
        topic_names: list[str],
    ) -> list[str]: ...
