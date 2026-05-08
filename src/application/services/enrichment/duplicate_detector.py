from __future__ import annotations

from math import sqrt
from typing import TYPE_CHECKING

from src.core.config import settings

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.ports.persistence.unit_of_work import IUnitOfWork
    from src.domain.entities.document_entity import DocumentEntity


class DuplicateDetector:
    def __init__(self, uow: IUnitOfWork, *, similarity_threshold: float | None = None) -> None:
        self._uow = uow
        self._similarity_threshold = (
            settings.DEDUPLICATION_SIMILARITY_THRESHOLD
            if similarity_threshold is None
            else similarity_threshold
        )

    async def find_duplicate(self, document: DocumentEntity) -> UUID | None:
        if document.doc_embedding is None:
            return None

        async with self._uow:
            others = await self._uow.document_repo.get_by_user_id(document.user_id, limit=50)

        for other in others:
            if other.id == document.id or other.doc_embedding is None:
                continue
            similarity = _cosine(document.doc_embedding, other.doc_embedding)
            if similarity >= self._similarity_threshold:
                return other.id

        return None


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sqrt(sum(x * x for x in a))
    norm_b = sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
