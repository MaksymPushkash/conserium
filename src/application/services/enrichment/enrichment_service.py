from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict, cast

from src.application.services.enrichment.document_embedding_service import DocumentEmbeddingService
from src.application.services.enrichment.duplicate_detector import DuplicateDetector
from src.application.services.enrichment.suggested_questions import build_suggested_questions
from src.application.services.enrichment.tag_builder import build_auto_tags
from src.domain.exceptions import DocumentNotFoundException

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.dtos.ingestion_dtos import CategoryDTO, EntityDTO
    from src.application.ports.ai.classifier_provider import IClassifierProvider
    from src.application.ports.ai.embedding_provider import IEmbeddingProvider
    from src.application.ports.ai.ner_provider import INERProvider
    from src.application.ports.persistence.document_tag_sync import IDocumentTagSync
    from src.application.ports.persistence.unit_of_work import IUnitOfWork


class EnrichmentResult(TypedDict):
    entities: list[EntityDTO]
    categories: list[CategoryDTO]
    tags: list[str]
    suggested_questions: list[str]
    is_duplicate: bool
    duplicate_of_id: UUID | None


class EnrichmentService:
    def __init__(
        self,
        uow: IUnitOfWork,
        embedding_provider: IEmbeddingProvider,
        ner_provider: INERProvider | None = None,
        classifier_provider: IClassifierProvider | None = None,
        tag_sync: IDocumentTagSync | None = None,
    ) -> None:
        self._uow = uow
        self._document_embedding = DocumentEmbeddingService(uow, embedding_provider)
        self._duplicate_detector = DuplicateDetector(uow)
        self._ner = ner_provider
        self._clf = classifier_provider
        self._tag_sync = tag_sync

    async def enrich_document(self, document_id: UUID) -> EnrichmentResult:
        async with self._uow:
            doc = await self._uow.document_repo.get_by_id(document_id)
            if doc is None:
                raise DocumentNotFoundException("document not found")

        result: EnrichmentResult = {
            "entities": [],
            "categories": [],
            "tags": [],
            "suggested_questions": [],
            "is_duplicate": False,
            "duplicate_of_id": None,
        }

        text = doc.raw_content or ""

        if self._ner and text:
            entities: list[EntityDTO] = await self._ner.extract_entities(text)
            result["entities"] = entities

        if self._clf and text:
            cats: list[CategoryDTO] = await self._clf.classify(text)
            result["categories"] = cats

        await self._document_embedding.ensure_embedding(doc)

        duplicate_id = await self._duplicate_detector.find_duplicate(doc)
        if duplicate_id is not None:
            doc.mark_duplicate(duplicate_id)
            result["is_duplicate"] = True
            result["duplicate_of_id"] = duplicate_id

        tag_names = build_auto_tags(result["entities"], result["categories"])
        if self._tag_sync is not None:
            result["tags"] = await self._tag_sync.sync_auto_tags(
                user_id=doc.user_id,
                document_id=doc.id,
                tag_names=tag_names,
            )
        else:
            result["tags"] = tag_names

        result["suggested_questions"] = build_suggested_questions(
            title=doc.title,
            text=text,
            tags=result["tags"],
            categories=result["categories"],
        )
        visual_metadata = doc.visual_metadata or {}
        visual_metadata["suggested_questions"] = result["suggested_questions"]
        doc.update_visual_metadata(visual_metadata)

        doc.update_enrichment(
            entities=cast("list[dict[str, object]]", result["entities"]),
            categories=cast("list[dict[str, object]]", result["categories"]),
            tags=result["tags"],
        )

        async with self._uow:
            await self._uow.document_repo.update(doc)
            await self._uow.commit()

        return result
