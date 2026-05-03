from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.application.services.enrichment.enrichment_service import EnrichmentService
from src.domain.entities.document_entity import DocumentEntity
from src.domain.value_objects.document_type import DocumentType


@pytest.mark.asyncio
async def test_enrichment_service_with_ner_and_classification():
    """Test enrichment service extracts entities and categories."""
    doc_id = uuid4()
    user_id = uuid4()
    doc = DocumentEntity.create(
        id=doc_id,
        user_id=user_id,
        title="Test Document",
        type=DocumentType.TEXT,
        raw_content="John Smith works at Acme Corp in New York.",
    )

    # Mock providers
    uow = AsyncMock()
    uow.document_repo.get_by_id.return_value = doc
    uow.document_repo.get_by_user_id.return_value = []

    embedding_provider = AsyncMock()
    embedding_provider.embed_text.return_value = [0.1] * 1536

    ner_provider = AsyncMock()
    ner_provider.extract_entities.return_value = [
        {"text": "John Smith", "label": "PERSON"},
        {"text": "Acme Corp", "label": "ORG"},
        {"text": "New York", "label": "GPE"},
    ]

    classifier_provider = AsyncMock()
    classifier_provider.classify.return_value = [
        {"label": "business", "score": 0.92},
        {"label": "professional", "score": 0.87},
    ]

    service = EnrichmentService(
        uow, embedding_provider, ner_provider=ner_provider, classifier_provider=classifier_provider
    )

    result = await service.enrich_document(doc_id)

    assert len(result["entities"]) == 3
    assert result["entities"][0]["label"] == "PERSON"
    assert len(result["categories"]) == 2
    assert result["categories"][0]["label"] == "business"
    assert result["is_duplicate"] is False
    ner_provider.extract_entities.assert_called_once()
    classifier_provider.classify.assert_called_once()


@pytest.mark.asyncio
async def test_enrichment_service_deduplication():
    """Test enrichment service detects duplicates."""
    doc_id = uuid4()
    user_id = uuid4()
    original_id = uuid4()

    doc = DocumentEntity.create(
        id=doc_id,
        user_id=user_id,
        title="Document A",
        type=DocumentType.TEXT,
        raw_content="Duplicate content here.",
    )

    original = DocumentEntity.create(
        id=original_id,
        user_id=user_id,
        title="Document B",
        type=DocumentType.TEXT,
        raw_content="Original content.",
    )
    # Set same embedding to trigger deduplication
    original._doc_embedding = [0.1] * 1536

    uow = AsyncMock()
    uow.document_repo.get_by_id.return_value = doc
    uow.document_repo.get_by_user_id.return_value = [original]

    embedding_provider = AsyncMock()
    embedding_provider.embed_text.return_value = [0.1] * 1536

    service = EnrichmentService(uow, embedding_provider)
    result = await service.enrich_document(doc_id)

    assert result["is_duplicate"] is True
    uow.document_repo.update.assert_called_once()
