from uuid import UUID

from sqlalchemy import ColumnElement, delete, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.application.ports.persistence.document_repository import IDocumentRepository
from src.domain.entities.document_entity import DocumentEntity
from src.domain.value_objects.document_status import DocumentStatus
from src.domain.value_objects.document_type import DocumentType
from src.infrastructure.database.models.document import DocumentModel


class SQLAlchemyDocumentRepository(IDocumentRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, document_id: UUID) -> DocumentEntity | None:
        result = await self._session.execute(
            select(DocumentModel)
            .options(selectinload(DocumentModel.tags))
            .where(DocumentModel.id == document_id)
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_by_user_id(
        self,
        user_id: UUID,
        *,
        limit: int = 50,
        offset: int = 0,
        document_type: DocumentType | None = None,
        collection_id: UUID | None = None,
        status: DocumentStatus | None = None,
    ) -> list[DocumentEntity]:
        conditions = self._document_conditions(
            user_id,
            document_type=document_type,
            collection_id=collection_id,
            status=status,
        )
        result = await self._session.execute(
            select(DocumentModel)
            .options(selectinload(DocumentModel.tags))
            .where(*conditions)
            .order_by(DocumentModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [self._to_entity(model) for model in result.scalars().all()]

    async def create(self, document: DocumentEntity) -> None:
        self._session.add(self._to_model(document))

    async def update(self, document: DocumentEntity) -> None:
        result = await self._session.execute(select(DocumentModel).where(DocumentModel.id == document.id))
        model = result.scalar_one()
        self._apply_entity(model, document)

    async def delete(self, document_id: UUID) -> None:
        await self._session.execute(delete(DocumentModel).where(DocumentModel.id == document_id))

    async def exists(self, document_id: UUID) -> bool:
        result = await self._session.execute(select(exists().where(DocumentModel.id == document_id)))
        return result.scalar_one()

    async def count_by_user_id(
        self,
        user_id: UUID,
        *,
        document_type: DocumentType | None = None,
        collection_id: UUID | None = None,
        status: DocumentStatus | None = None,
    ) -> int:
        conditions = self._document_conditions(
            user_id,
            document_type=document_type,
            collection_id=collection_id,
            status=status,
        )
        result = await self._session.execute(
            select(func.count()).select_from(DocumentModel).where(*conditions)
        )
        return result.scalar_one()

    @staticmethod
    def _document_conditions(
        user_id: UUID,
        *,
        document_type: DocumentType | None,
        collection_id: UUID | None,
        status: DocumentStatus | None,
    ) -> list[ColumnElement[bool]]:
        conditions: list[ColumnElement[bool]] = [DocumentModel.user_id == user_id]
        if document_type is not None:
            conditions.append(DocumentModel.type == document_type)
        if collection_id is not None:
            conditions.append(DocumentModel.collection_id == collection_id)
        if status is not None:
            conditions.append(DocumentModel.status == status)
        return conditions

    def _to_entity(self, model: DocumentModel) -> DocumentEntity:
        return DocumentEntity(
            id=model.id,
            user_id=model.user_id,
            collection_id=model.collection_id,
            title=model.title,
            type=model.type,
            status=model.status,
            source_url=model.source_url,
            file_path=model.file_path,
            file_size_bytes=model.file_size_bytes,
            raw_content=model.raw_content,
            summary=model.summary,
            word_count=model.word_count,
            language=model.language,
            entities=model.entities,
            categories=model.categories,
            visual_metadata=model.visual_metadata,
            tags=[tag.name for tag in model.tags],
            doc_embedding=list(model.doc_embedding) if model.doc_embedding is not None else None,
            is_duplicate=model.is_duplicate,
            duplicate_of_id=model.duplicate_of_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, entity: DocumentEntity) -> DocumentModel:
        return DocumentModel(
            id=entity.id,
            user_id=entity.user_id,
            collection_id=entity.collection_id,
            title=entity.title,
            type=entity.type,
            status=entity.status,
            source_url=entity.source_url,
            file_path=entity.file_path,
            file_size_bytes=entity.file_size_bytes,
            raw_content=entity.raw_content,
            summary=entity.summary,
            word_count=entity.word_count,
            language=entity.language,
            entities=entity.entities,
            categories=entity.categories,
            visual_metadata=entity.visual_metadata,
            doc_embedding=entity.doc_embedding,
            is_duplicate=entity.is_duplicate,
            duplicate_of_id=entity.duplicate_of_id,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    def _apply_entity(self, model: DocumentModel, entity: DocumentEntity) -> None:
        model.user_id = entity.user_id
        model.collection_id = entity.collection_id
        model.title = entity.title
        model.type = entity.type
        model.status = entity.status
        model.source_url = entity.source_url
        model.file_path = entity.file_path
        model.file_size_bytes = entity.file_size_bytes
        model.raw_content = entity.raw_content
        model.summary = entity.summary
        model.word_count = entity.word_count
        model.language = entity.language
        model.entities = entity.entities
        model.categories = entity.categories
        model.visual_metadata = entity.visual_metadata
        model.doc_embedding = entity.doc_embedding
        model.is_duplicate = entity.is_duplicate
        model.duplicate_of_id = entity.duplicate_of_id
        model.updated_at = entity.updated_at
