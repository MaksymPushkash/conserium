from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.documents.services.enrichment.enrichment_service import EnrichmentService
from src.documents.types import DocumentType
from src.models.chunk import ChunkModel
from src.models.document import DocumentModel


@pytest.mark.asyncio
async def test_enrichment_service_with_ner_and_classification():
    """Test enrichment service extracts entities and categories."""
    doc_id = uuid4()
    user_id = uuid4()
    doc = DocumentModel.create(
        id=doc_id,
        user_id=user_id,
        title="Test Document",
        type=DocumentType.TEXT,
        raw_content="John Smith works at Acme Corp in New York.",
    )

    # Mock providers
    repository_session = AsyncMock()
    repository_session.document_repo.get_by_id.return_value = doc
    repository_session.document_repo.get_by_user_id.return_value = []
    repository_session.chunk_repo.get_by_document_id.return_value = []

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
        repository_session,
        repository_session.document_repo,
        embedding_provider,
        repository_session.chunk_repo,
        ner_provider=ner_provider,
        classifier_provider=classifier_provider,
    )

    result = await service.enrich_document(doc_id)

    assert len(result["entities"]) == 3
    assert result["entities"][0]["label"] == "PERSON"
    assert len(result["categories"]) == 2
    assert result["categories"][0]["label"] == "business"
    assert result["is_duplicate"] is False
    assert result["summary"] is None
    ner_provider.extract_entities.assert_called_once()
    classifier_provider.classify.assert_called_once()


@pytest.mark.asyncio
async def test_enrichment_service_syncs_topics_from_tags():
    doc_id = uuid4()
    user_id = uuid4()
    doc = DocumentModel.create(
        id=doc_id,
        user_id=user_id,
        title="Async Python",
        type=DocumentType.TEXT,
        raw_content="Async Python uses coroutines.",
    )

    repository_session = AsyncMock()
    repository_session.document_repo.get_by_id.return_value = doc
    repository_session.document_repo.get_by_user_id.return_value = []
    repository_session.chunk_repo.get_by_document_id.return_value = []
    embedding_provider = AsyncMock()
    embedding_provider.embed_text.return_value = [0.1] * 1536
    classifier_provider = AsyncMock()
    classifier_provider.classify.return_value = [{"label": "python", "score": 0.9}]
    tag_sync = AsyncMock()
    tag_sync.sync_auto_tags.return_value = ["python"]
    topic_sync = AsyncMock()
    topic_sync.sync_topics.return_value = ["python"]

    service = EnrichmentService(
        repository_session,
        repository_session.document_repo,
        embedding_provider,
        repository_session.chunk_repo,
        classifier_provider=classifier_provider,
        tag_sync=tag_sync,
        topic_sync=topic_sync,
    )

    result = await service.enrich_document(doc_id)

    assert result["tags"] == ["python"]
    topic_sync.sync_topics.assert_awaited_once_with(
        user_id=user_id,
        document_id=doc_id,
        topic_names=["python"],
    )


@pytest.mark.asyncio
async def test_enrichment_service_generates_summary_for_supported_documents():
    doc_id = uuid4()
    user_id = uuid4()
    doc = DocumentModel.create(
        id=doc_id,
        user_id=user_id,
        title="Async Python",
        type=DocumentType.URL,
        raw_content="Async Python lets programs overlap I/O work. It uses coroutines and an event loop.",
    )

    repository_session = AsyncMock()
    repository_session.document_repo.get_by_id.return_value = doc
    repository_session.document_repo.get_by_user_id.return_value = []
    repository_session.chunk_repo.get_by_document_id.return_value = []
    embedding_provider = AsyncMock()
    embedding_provider.embed_text.return_value = [0.1] * 1536
    summary_service = AsyncMock()
    summary_service.summarize_document.return_value = "Async Python overlaps I/O work with coroutines and an event loop."

    service = EnrichmentService(
        repository_session,
        repository_session.document_repo,
        embedding_provider,
        repository_session.chunk_repo,
        summary_service=summary_service,
    )
    result = await service.enrich_document(doc_id)

    assert result["summary"] == "Async Python overlaps I/O work with coroutines and an event loop."
    assert doc.summary == "Async Python overlaps I/O work with coroutines and an event loop."
    summary_service.summarize_document.assert_awaited_once_with(
        title="Async Python",
        text="Async Python lets programs overlap I/O work. It uses coroutines and an event loop.",
    )


@pytest.mark.asyncio
async def test_enrichment_service_skips_summary_for_empty_text():
    doc_id = uuid4()
    user_id = uuid4()
    doc = DocumentModel.create(
        id=doc_id,
        user_id=user_id,
        title="Empty",
        type=DocumentType.TEXT,
        raw_content=None,
    )

    repository_session = AsyncMock()
    repository_session.document_repo.get_by_id.return_value = doc
    repository_session.document_repo.get_by_user_id.return_value = []
    repository_session.chunk_repo.get_by_document_id.return_value = []
    embedding_provider = AsyncMock()
    summary_service = AsyncMock()

    service = EnrichmentService(
        repository_session,
        repository_session.document_repo,
        embedding_provider,
        repository_session.chunk_repo,
        summary_service=summary_service,
    )
    result = await service.enrich_document(doc_id)

    assert result["summary"] is None
    assert doc.summary is None
    summary_service.summarize_document.assert_not_awaited()


@pytest.mark.asyncio
async def test_enrichment_service_deduplication():
    """Test enrichment service detects duplicates."""
    doc_id = uuid4()
    user_id = uuid4()
    original_id = uuid4()

    doc = DocumentModel.create(
        id=doc_id,
        user_id=user_id,
        title="Document A",
        type=DocumentType.TEXT,
        raw_content="Duplicate content here.",
    )

    original = DocumentModel.create(
        id=original_id,
        user_id=user_id,
        title="Document B",
        type=DocumentType.TEXT,
        raw_content="Original content.",
    )
    # Set same embedding to trigger deduplication
    original.doc_embedding = [0.1] * 1536

    repository_session = AsyncMock()
    repository_session.document_repo.get_by_id.return_value = doc
    repository_session.document_repo.get_by_user_id.return_value = [original]
    repository_session.chunk_repo.get_by_document_id.return_value = []

    embedding_provider = AsyncMock()
    embedding_provider.embed_text.return_value = [0.1] * 1536

    service = EnrichmentService(
        repository_session,
        repository_session.document_repo,
        embedding_provider,
        repository_session.chunk_repo,
    )
    result = await service.enrich_document(doc_id)

    assert result["is_duplicate"] is True
    repository_session.document_repo.update.assert_called_once()


@pytest.mark.asyncio
async def test_enrichment_service_uses_chunk_embeddings_for_document_embedding():
    doc_id = uuid4()
    user_id = uuid4()
    doc = DocumentModel.create(
        id=doc_id,
        user_id=user_id,
        title="Long Document",
        type=DocumentType.URL,
        raw_content="Long content",
    )
    chunks = [
        ChunkModel.create(
            id=uuid4(),
            document_id=doc_id,
            content="first",
            embedding=[0.2] * 1536,
            chunk_index=0,
        ),
        ChunkModel.create(
            id=uuid4(),
            document_id=doc_id,
            content="second",
            embedding=[0.4] * 1536,
            chunk_index=1,
        ),
    ]

    repository_session = AsyncMock()
    repository_session.document_repo.get_by_id.return_value = doc
    repository_session.document_repo.get_by_user_id.return_value = []
    repository_session.chunk_repo.get_by_document_id.return_value = chunks
    embedding_provider = AsyncMock()

    service = EnrichmentService(
        repository_session,
        repository_session.document_repo,
        embedding_provider,
        repository_session.chunk_repo,
    )
    await service.enrich_document(doc_id)

    embedding_provider.embed_text.assert_not_called()
    assert doc.doc_embedding == pytest.approx([0.3] * 1536)


@pytest.mark.asyncio
async def test_enrichment_service_skips_large_full_text_embedding_without_chunks(monkeypatch):
    doc_id = uuid4()
    user_id = uuid4()
    doc = DocumentModel.create(
        id=doc_id,
        user_id=user_id,
        title="Large Document",
        type=DocumentType.URL,
        raw_content="x" * 100,
    )

    repository_session = AsyncMock()
    repository_session.document_repo.get_by_id.return_value = doc
    repository_session.document_repo.get_by_user_id.return_value = []
    repository_session.chunk_repo.get_by_document_id.return_value = []
    embedding_provider = AsyncMock()

    monkeypatch.setattr(
        "src.documents.services.enrichment.document_embedding_service.settings.ENRICHMENT_FULL_TEXT_EMBEDDING_MAX_CHARS",
        10,
    )

    service = EnrichmentService(
        repository_session,
        repository_session.document_repo,
        embedding_provider,
        repository_session.chunk_repo,
    )
    await service.enrich_document(doc_id)

    embedding_provider.embed_text.assert_not_called()
    assert doc.doc_embedding is None
