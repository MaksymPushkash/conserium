from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict, cast

from src.documents.services.enrichment.document_embedding_service import DocumentEmbeddingService
from src.documents.services.enrichment.duplicate_detector import DuplicateDetector
from src.documents.services.enrichment.suggested_questions import build_suggested_questions
from src.documents.services.enrichment.tag_builder import build_auto_tags
from src.documents.types import DocumentType
from src.kit.exceptions import DocumentNotFoundException
from src.topics.services.topic_builder import topic_names_from_tags

if TYPE_CHECKING:
    from uuid import UUID

    from src.documents.chunk_repository import ChunkRepository
    from src.documents.document_repository import DocumentRepository
    from src.documents.schemas import CategoryDTO, EntityDTO
    from src.documents.tag_sync import DocumentTagSync
    from src.documents.topic_sync import DocumentTopicSync
    from src.kit.ports.ai.classifier_provider import IClassifierProvider
    from src.kit.ports.ai.document_summary_service import IDocumentSummaryService
    from src.kit.ports.ai.embedding_provider import IEmbeddingProvider
    from src.kit.ports.ai.ner_provider import INERProvider
    from src.postgres import AsyncSession


class EnrichmentResult(TypedDict):
    summary: str | None
    entities: list[EntityDTO]
    categories: list[CategoryDTO]
    tags: list[str]
    suggested_questions: list[str]
    is_duplicate: bool
    duplicate_of_id: UUID | None


class EnrichmentService:
    def __init__(
        self,
        session: AsyncSession,
        document_repo: DocumentRepository,
        embedding_provider: IEmbeddingProvider,
        chunk_repo: ChunkRepository,
        ner_provider: INERProvider | None = None,
        classifier_provider: IClassifierProvider | None = None,
        tag_sync: DocumentTagSync | None = None,
        topic_sync: DocumentTopicSync | None = None,
        summary_service: IDocumentSummaryService | None = None,
    ) -> None:
        self._session = session
        self._document_repo = document_repo
        self._document_embedding = DocumentEmbeddingService(chunk_repo, embedding_provider)
        self._duplicate_detector = DuplicateDetector(document_repo)
        self._ner = ner_provider
        self._clf = classifier_provider
        self._tag_sync = tag_sync
        self._topic_sync = topic_sync
        self._summary_service = summary_service

    async def enrich_document(self, document_id: UUID) -> EnrichmentResult:
        doc = await self._document_repo.get_by_id(document_id)
        if doc is None:
            raise DocumentNotFoundException("document not found")

        result: EnrichmentResult = {
            "summary": None,
            "entities": [],
            "categories": [],
            "tags": [],
            "suggested_questions": [],
            "is_duplicate": False,
            "duplicate_of_id": None,
        }

        text = doc.raw_content or ""

        if self._summary_service is not None and _supports_auto_summary(doc.type) and text:
            result["summary"] = await self._summary_service.summarize_document(title=doc.title, text=text)
            if result["summary"]:
                doc.update_summary(result["summary"])

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

        if self._topic_sync is not None:
            await self._topic_sync.sync_topics(
                user_id=doc.user_id,
                document_id=doc.id,
                topic_names=topic_names_from_tags(result["tags"]),
            )

        result["suggested_questions"] = build_suggested_questions(
            title=doc.title,
            text=text,
            tags=result["tags"],
            categories=result["categories"],
        )
        doc.update_suggested_questions(result["suggested_questions"])

        doc.update_enrichment(
            entities=cast("list[dict[str, object]]", result["entities"]),
            categories=cast("list[dict[str, object]]", result["categories"]),
            tags=result["tags"],
        )

        await self._document_repo.update(doc)
        await self._session.commit()

        return result


def _supports_auto_summary(document_type: DocumentType) -> bool:
    return document_type in {DocumentType.TEXT, DocumentType.URL, DocumentType.PDF, DocumentType.MARKDOWN}
