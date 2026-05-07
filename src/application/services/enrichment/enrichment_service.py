from __future__ import annotations

from math import sqrt
from typing import TYPE_CHECKING, TypedDict, cast

from src.core.config import settings
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
    is_duplicate: bool
    duplicate_of_id: UUID | None


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sqrt(sum(x * x for x in a))
    norm_b = sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


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
        self._emb = embedding_provider
        self._ner = ner_provider
        self._clf = classifier_provider
        self._tag_sync = tag_sync

    async def enrich_document(self, document_id: UUID) -> EnrichmentResult:
        # Load document
        async with self._uow:
            doc = await self._uow.document_repo.get_by_id(document_id)
            if doc is None:
                raise DocumentNotFoundException("document not found")

        result: EnrichmentResult = {
            "entities": [],
            "categories": [],
            "tags": [],
            "is_duplicate": False,
            "duplicate_of_id": None,
        }

        text = doc.raw_content or ""

        # NER
        if self._ner and text:
            entities: list[EntityDTO] = await self._ner.extract_entities(text)
            result["entities"] = entities

        # classification
        if self._clf and text:
            cats: list[CategoryDTO] = await self._clf.classify(text)
            result["categories"] = cats

        # update document embedding only when it was not already computed in the ingestion pipeline
        if text and doc.doc_embedding is None:
            emb = await self._emb.embed_text(text)
            doc.update_embedding(emb)

        # deduplication
        if doc.doc_embedding is not None:
            async with self._uow:
                others = await self._uow.document_repo.get_by_user_id(doc.user_id, limit=50)
                for other in others:
                    if other.id == doc.id or other.doc_embedding is None:
                        continue
                    sim = _cosine(doc.doc_embedding, other.doc_embedding)
                    if sim >= getattr(settings, "DEDUPLICATION_SIMILARITY_THRESHOLD", 0.95):
                        doc.mark_duplicate(other.id)
                        result["is_duplicate"] = True
                        result["duplicate_of_id"] = other.id
                        break

        tag_names = _build_auto_tags(result["entities"], result["categories"])
        if self._tag_sync is not None:
            result["tags"] = await self._tag_sync.sync_auto_tags(
                user_id=doc.user_id,
                document_id=doc.id,
                tag_names=tag_names,
            )
        else:
            result["tags"] = tag_names

        doc.update_enrichment(
            entities=cast("list[dict[str, object]]", result["entities"]),
            categories=cast("list[dict[str, object]]", result["categories"]),
            tags=result["tags"],
        )

        async with self._uow:
            await self._uow.document_repo.update(doc)
            await self._uow.commit()

        return result


def _build_auto_tags(
    entities: list[EntityDTO],
    categories: list[CategoryDTO],
) -> list[str]:
    entity_tags: list[str] = []
    for entity in entities:
        entity_text = str(entity.get("text", "")).strip().lower()
        if 2 <= len(entity_text) <= 40:
            entity_tags.append(entity_text)

    category_tags = [
        str(category.get("label", "")).strip().lower()
        for category in categories
        if float(category.get("score", 0.0)) >= 0.5 and str(category.get("label", "")).strip()
    ]

    return list(dict.fromkeys([*category_tags[:3], *entity_tags[:5]]))
