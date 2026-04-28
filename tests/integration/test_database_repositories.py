import os
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import settings
from src.domain.entities.chunk_entity import ChunkEntity
from src.domain.entities.document_entity import DocumentEntity
from src.domain.entities.user_entity import UserEntity
from src.domain.value_objects.document_status import DocumentStatus
from src.domain.value_objects.document_type import DocumentType
from src.domain.value_objects.email import Email
from src.infrastructure.auth.password_hasher import BcryptPasswordHasher
from src.infrastructure.database.models import Base
from src.infrastructure.database.models.chunk import ChunkModel
from src.infrastructure.database.models.document import DocumentModel
from src.infrastructure.database.models.user import UserModel
from src.infrastructure.database.repositories.chunk_repository import SQLAlchemyChunkRepository
from src.infrastructure.database.repositories.document_repository import SQLAlchemyDocumentRepository
from src.infrastructure.database.repositories.user_repository import SQLAlchemyUserRepository

pytestmark = pytest.mark.skipif(
    os.environ.get("CORTEX_RUN_DB_TESTS") != "1",
    reason="set CORTEX_RUN_DB_TESTS=1 to run database integration tests against DATABASE_URL",
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
    return [value] * ChunkEntity.EMBEDDING_DIMENSIONS


async def test_user_repository_preserves_null_updated_at(db_session: AsyncSession) -> None:
    repository = SQLAlchemyUserRepository(db_session)
    user = UserEntity.create(
        id=uuid.uuid4(),
        email=Email(value=f"{uuid.uuid4()}@integration.test"),
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

    document_repository = SQLAlchemyDocumentRepository(db_session)
    chunk_repository = SQLAlchemyChunkRepository(db_session)

    document = DocumentEntity(
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
    chunk = ChunkEntity.create(
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
