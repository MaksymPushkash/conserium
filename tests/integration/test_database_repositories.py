import os
import uuid
from collections import Counter
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.auth.password_hasher import BcryptPasswordHasher
from src.documents.chunk_repository import ChunkRepository
from src.documents.document_repository import DocumentRepository
from src.documents.status import DocumentStatus
from src.documents.types import DocumentType
from src.knowledge_graph.repository import KnowledgeGraphRepository
from src.models import Base
from src.models.base import document_tags, document_topics
from src.models.chunk import ChunkModel
from src.models.collection import CollectionModel
from src.models.document import DocumentModel
from src.models.tag import TagModel
from src.models.topic import TopicModel
from src.models.user import UserModel
from src.settings import settings
from src.topics.repository import TopicRepository
from src.users.repository import UserRepository

pytestmark = pytest.mark.skipif(
    os.environ.get("CONSERIUM_RUN_DB_TESTS") != "1",
    reason="set CONSERIUM_RUN_DB_TESTS=1 to run database integration tests against DATABASE_URL",
)


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.rollback()
            integration_user_ids = select(UserModel.id).where(UserModel.email.like("%@integration.test"))
            integration_document_ids = select(DocumentModel.id).where(DocumentModel.user_id.in_(integration_user_ids))
            await session.execute(delete(ChunkModel).where(ChunkModel.document_id.in_(integration_document_ids)))
            await session.execute(delete(DocumentModel).where(DocumentModel.user_id.in_(integration_user_ids)))
            await session.execute(delete(UserModel).where(UserModel.email.like("%@integration.test")))
            await session.commit()

    await engine.dispose()


def _embedding(value: float) -> list[float]:
    return [value] * ChunkModel.EMBEDDING_DIMENSIONS


async def test_user_repository_preserves_null_updated_at(db_session: AsyncSession) -> None:
    repository = UserRepository(db_session)
    user = UserModel.create(
        id=uuid.uuid4(),
        email=f"{uuid.uuid4()}@integration.test",
        password=BcryptPasswordHasher().hash("securepass123"),
    )

    await repository.create(user)
    await db_session.commit()

    persisted = await repository.get_by_id(user.id)

    assert persisted is not None
    assert persisted.updated_at is None


async def test_document_and_chunk_repositories_round_trip(db_session: AsyncSession) -> None:
    user = UserModel(
        email=f"{uuid.uuid4()}@integration.test",
        hashed_password=BcryptPasswordHasher().hash("securepass123"),
        display_name="Integration User",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    document_repository = DocumentRepository(db_session)
    chunk_repository = ChunkRepository(db_session)

    document = DocumentModel(
        id=uuid.uuid4(),
        user_id=user.id,
        collection_id=None,
        title="Integration Document",
        type=DocumentType.TEXT,
        status=DocumentStatus.PENDING,
        source_url=None,
        file_path=None,
        file_size_bytes=None,
        raw_content="Hello integration tests",
        summary=None,
        word_count=3,
        language="en",
        doc_embedding=None,
        is_duplicate=False,
        duplicate_of_id=None,
        created_at=user.created_at,
        updated_at=None,
    )
    chunk = ChunkModel.create(
        id=uuid.uuid4(),
        document_id=document.id,
        content="Hello integration tests",
        embedding=_embedding(0.1),
        chunk_index=0,
        start_char=0,
        end_char=23,
        page_number=1,
        token_count=3,
    )

    await document_repository.create(document)
    await chunk_repository.create_batch([chunk])
    await db_session.commit()

    loaded_document = await document_repository.get_by_id(document.id)
    loaded_chunks = await chunk_repository.get_by_document_id(document.id)
    search_results = await chunk_repository.semantic_search(_embedding(0.1), user.id, limit=1)

    assert loaded_document is not None
    assert loaded_document.title == "Integration Document"
    assert loaded_chunks[0].content == "Hello integration tests"
    assert search_results[0].id == chunk.id


async def test_knowledge_graph_repository_applies_combined_filters(db_session: AsyncSession) -> None:
    user = UserModel(
        email=f"{uuid.uuid4()}@integration.test",
        hashed_password=BcryptPasswordHasher().hash("securepass123"),
        display_name="Graph User",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    collection = CollectionModel(user_id=user.id, name=f"Backend {uuid.uuid4()}", description=None, color=None)
    other_collection = CollectionModel(user_id=user.id, name=f"Other {uuid.uuid4()}", description=None, color=None)
    db_session.add_all([collection, other_collection])
    await db_session.flush()

    backend_tag = TagModel(user_id=user.id, name="backend", auto=False)
    python_topic = TopicModel(user_id=user.id, name="python")
    image_topic = TopicModel(user_id=user.id, name="vision")
    db_session.add_all([backend_tag, python_topic, image_topic])
    await db_session.flush()

    matching_document = _document_model(
        user_id=user.id,
        collection_id=collection.id,
        title="FastAPI",
        document_type=DocumentType.MARKDOWN,
    )
    wrong_collection = _document_model(
        user_id=user.id,
        collection_id=other_collection.id,
        title="Django",
        document_type=DocumentType.MARKDOWN,
    )
    wrong_type = _document_model(
        user_id=user.id,
        collection_id=collection.id,
        title="Diagram",
        document_type=DocumentType.IMAGE,
    )
    stale_document = _document_model(
        user_id=user.id,
        collection_id=collection.id,
        title="Old API",
        document_type=DocumentType.MARKDOWN,
        created_at=datetime.now(UTC) - timedelta(days=90),
    )
    db_session.add_all([matching_document, wrong_collection, wrong_type, stale_document])
    await db_session.flush()
    await db_session.execute(
        document_tags.insert(),
        [
            {"document_id": matching_document.id, "tag_id": backend_tag.id},
            {"document_id": wrong_collection.id, "tag_id": backend_tag.id},
            {"document_id": wrong_type.id, "tag_id": backend_tag.id},
            {"document_id": stale_document.id, "tag_id": backend_tag.id},
        ],
    )
    await db_session.execute(
        document_topics.insert(),
        [
            {"document_id": matching_document.id, "topic_id": python_topic.id},
            {"document_id": wrong_collection.id, "topic_id": python_topic.id},
            {"document_id": wrong_type.id, "topic_id": image_topic.id},
            {"document_id": stale_document.id, "topic_id": python_topic.id},
        ],
    )
    await db_session.commit()

    repository = KnowledgeGraphRepository(db_session)
    result = await repository.list_topic_document_links(
        user.id,
        document_limit=20,
        topic_limit=10,
        collection_id=collection.id,
        tag_name="backend",
        topic_name="python",
        document_type=DocumentType.MARKDOWN,
        recency_days=30,
    )

    assert [record.document_title for record in result] == ["FastAPI"]


async def test_topic_repository_applies_alias_pin_and_ignore_overrides(db_session: AsyncSession) -> None:
    user = UserModel(
        email=f"{uuid.uuid4()}@integration.test",
        hashed_password=BcryptPasswordHasher().hash("securepass123"),
        display_name="Topic User",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    collection = CollectionModel(user_id=user.id, name=f"Topics {uuid.uuid4()}", description=None, color=None)
    python_topic = TopicModel(user_id=user.id, name="python")
    fastapi_topic = TopicModel(user_id=user.id, name="fastapi")
    db_session.add_all([collection, python_topic, fastapi_topic])
    await db_session.flush()

    python_document = _document_model(
        user_id=user.id,
        collection_id=collection.id,
        title="Python",
        document_type=DocumentType.TEXT,
    )
    fastapi_document = _document_model(
        user_id=user.id,
        collection_id=collection.id,
        title="FastAPI",
        document_type=DocumentType.TEXT,
    )
    db_session.add_all([python_document, fastapi_document])
    await db_session.flush()
    await db_session.execute(
        document_topics.insert(),
        [
            {"document_id": python_document.id, "topic_id": python_topic.id},
            {"document_id": fastapi_document.id, "topic_id": fastapi_topic.id},
        ],
    )
    await db_session.commit()

    repository = TopicRepository(db_session)
    renamed = await repository.rename_topic(user_id=user.id, source_name="python", display_name="Backend")
    merged = await repository.merge_topics(user_id=user.id, source_names=["python", "fastapi"], display_name="Backend")
    pinned = await repository.set_pinned(user_id=user.id, name="Backend", pinned=True)
    ignored = await repository.set_ignored(user_id=user.id, name="Backend", ignored=True)
    await db_session.commit()

    listed = await repository.list_by_user_id(user.id, limit=10, offset=0)
    events = await repository.list_override_events(user_id=user.id, topic_name="Backend", limit=10)

    assert renamed.name == "Backend"
    assert set(merged.source_names) == {"python", "fastapi"}
    assert pinned.pinned is True
    assert ignored.ignored is True
    assert listed == []
    assert Counter(event.action for event in events) == Counter(["ignored", "pinned", "merged", "renamed"])


def _document_model(
    *,
    user_id: uuid.UUID,
    collection_id: uuid.UUID,
    title: str,
    document_type: DocumentType,
    created_at: datetime | None = None,
) -> DocumentModel:
    return DocumentModel(
        id=uuid.uuid4(),
        user_id=user_id,
        collection_id=collection_id,
        title=title,
        type=document_type,
        status=DocumentStatus.READY,
        raw_content=title,
        summary=f"{title} summary",
        word_count=1,
        language="en",
        suggested_questions=[],
        is_duplicate=False,
        created_at=created_at,
    )
