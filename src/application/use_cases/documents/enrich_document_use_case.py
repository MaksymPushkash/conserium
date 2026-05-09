from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.services.enrichment.enrichment_service import EnrichmentService


class EnrichDocumentUseCase:
    def __init__(self, enrichment_service: EnrichmentService) -> None:
        self._enrichment_service = enrichment_service

    async def execute(self, document_id: UUID) -> dict[str, object]:
        result = await self._enrichment_service.enrich_document(document_id)
        return {**result, "document_id": str(document_id)}
