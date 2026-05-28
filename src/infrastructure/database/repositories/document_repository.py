from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import ColumnElement, delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.application.ports.persistence.document_repository import IDocumentRepository, RelatedDocumentRecord
from src.domain.entities.document_entity import DocumentEntity
from src.domain.value_objects.document_status import DocumentStatus
from src.domain.value_objects.document_type import DocumentType
from src.infrastructure.database.models.document import DocumentModel
from src.infrastructure.database.models.document_activity import DocumentActivityModel
from src.infrastructure.database.models.tag import TagModel
from src.infrastructure.database.models.topic import TopicModel


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
        model = self._to_model(document)
        self._session.add(model)
        if document.tags:
            await self._session.flush()
            await self._sync_initial_tags(model, document.user_id, document.tags)

    async def update(self, document: DocumentEntity) -> None:
        result = await self._session.execute(select(DocumentModel).where(DocumentModel.id == document.id))
        model = result.scalar_one()
        self._apply_entity(model, document)

    async def delete(self, document_id: UUID) -> None:
        await self._session.execute(delete(DocumentModel).where(DocumentModel.id == document_id))

    async def add_manual_tags(self, *, document_id: UUID, user_id: UUID, tag_names: list[str]) -> None:
        normalized_names = sorted({name.strip().lower() for name in tag_names if name.strip()})
        if not normalized_names:
            return

        document = await self._session.scalar(
            select(DocumentModel)
            .options(selectinload(DocumentModel.tags))
            .where(DocumentModel.id == document_id, DocumentModel.user_id == user_id)
        )
        if document is None:
            return

        existing_tags = await self._session.scalars(
            select(TagModel).where(TagModel.user_id == user_id, TagModel.name.in_(normalized_names))
        )
        tags_by_name = {tag.name: tag for tag in existing_tags}
        for name in normalized_names:
            tag = tags_by_name.get(name)
            if tag is None:
                tag = TagModel(user_id=user_id, name=name, auto=False)
                self._session.add(tag)
                await self._session.flush()
                tags_by_name[name] = tag
            elif tag.auto:
                tag.auto = False

        current_names = {tag.name for tag in document.tags}
        document.tags = [*document.tags, *[tags_by_name[name] for name in normalized_names if name not in current_names]]

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

    async def count_by_status(
        self,
        user_id: UUID,
        *,
        collection_id: UUID | None = None,
    ) -> dict[DocumentStatus, int]:
        conditions = self._document_conditions(
            user_id,
            document_type=None,
            collection_id=collection_id,
            status=None,
        )
        result = await self._session.execute(
            select(DocumentModel.status, func.count())
            .where(*conditions)
            .group_by(DocumentModel.status)
        )
        counts: dict[DocumentStatus, int] = {}
        for status, count in result.all():
            counts[status] = count
        return counts

    async def get_collection_documents_with_status_counts(
        self,
        user_id: UUID,
        *,
        collection_id: UUID,
        limit: int = 200,
    ) -> tuple[list[DocumentEntity], dict[DocumentStatus, int]]:
        documents = await self.get_by_user_id(user_id, collection_id=collection_id, limit=limit)
        counts = await self.count_by_status(user_id, collection_id=collection_id)
        return documents, counts

    async def get_related_documents(
        self,
        *,
        user_id: UUID,
        document_id: UUID,
        limit: int = 5,
    ) -> list[RelatedDocumentRecord]:
        target = await self._session.scalar(
            select(DocumentModel)
            .options(selectinload(DocumentModel.tags), selectinload(DocumentModel.topics))
            .where(DocumentModel.id == document_id, DocumentModel.user_id == user_id)
        )
        if target is None:
            return []

        target_tags = {tag.name for tag in target.tags}
        target_topics = {topic.name for topic in target.topics}
        target_terms = _connection_terms(target.title, target.summary)
        activity_subquery = (
            select(
                DocumentActivityModel.document_id,
                func.max(DocumentActivityModel.created_at).label("last_used_at"),
            )
            .where(DocumentActivityModel.user_id == user_id)
            .group_by(DocumentActivityModel.document_id)
            .subquery()
        )
        conditions = [
            DocumentModel.user_id == user_id,
            DocumentModel.id != document_id,
            DocumentModel.status == DocumentStatus.READY,
        ]
        overlap_conditions = []
        if target.collection_id:
            overlap_conditions.append(DocumentModel.collection_id == target.collection_id)
        if target_tags:
            overlap_conditions.append(DocumentModel.tags.any(TagModel.name.in_(target_tags)))
        if target_topics:
            overlap_conditions.append(DocumentModel.topics.any(TopicModel.name.in_(target_topics)))
        if overlap_conditions:
            conditions.append(or_(*overlap_conditions))

        candidate_rows = await self._session.execute(
            select(DocumentModel, activity_subquery.c.last_used_at)
            .outerjoin(activity_subquery, activity_subquery.c.document_id == DocumentModel.id)
            .options(selectinload(DocumentModel.tags), selectinload(DocumentModel.topics))
            .where(*conditions)
            .order_by(activity_subquery.c.last_used_at.desc().nullslast(), DocumentModel.created_at.desc())
            .limit(500)
        )
        records: list[RelatedDocumentRecord] = []
        for candidate, last_used_at in candidate_rows.all():
            reasons: list[str] = []
            score = 0
            shared_tags = sorted(target_tags.intersection({tag.name for tag in candidate.tags}))
            shared_topics = sorted(target_topics.intersection({topic.name for topic in candidate.topics}))
            shared_terms = sorted(target_terms.intersection(_connection_terms(candidate.title, candidate.summary)))
            if shared_tags:
                score += len(shared_tags) * 3
                reasons.append(f"Shared tags: {', '.join(shared_tags[:3])}")
            if shared_topics:
                score += len(shared_topics) * 4
                reasons.append(f"Shared topics: {', '.join(shared_topics[:3])}")
            if target.collection_id and candidate.collection_id == target.collection_id:
                score += 2
                reasons.append("Same collection")
            if len(shared_terms) >= 2:
                score += min(len(shared_terms), 5)
                reasons.append(f"Similar wording: {', '.join(shared_terms[:3])}")
            activity_score = _activity_connection_score(last_used_at)
            if activity_score:
                score += activity_score
                reasons.append("Recent activity")
            if score <= 0:
                continue
            records.append(
                RelatedDocumentRecord(
                    document=self._to_entity(candidate),
                    reasons=reasons[:4],
                    relationship_score=score,
                )
            )
        records.sort(key=lambda item: (item.relationship_score, item.document.created_at), reverse=True)
        return records[: max(1, min(limit, 20))]

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
            suggested_questions=_suggested_questions(model.suggested_questions, model.visual_metadata),
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
            suggested_questions=entity.suggested_questions,
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
        model.suggested_questions = entity.suggested_questions
        model.doc_embedding = entity.doc_embedding
        model.is_duplicate = entity.is_duplicate
        model.duplicate_of_id = entity.duplicate_of_id
        model.updated_at = entity.updated_at

    async def _sync_initial_tags(self, model: DocumentModel, user_id: UUID, tag_names: list[str]) -> None:
        normalized_names = sorted({name.strip().lower() for name in tag_names if name.strip()})
        if not normalized_names:
            return
        existing_tags = await self._session.scalars(
            select(TagModel).where(TagModel.user_id == user_id, TagModel.name.in_(normalized_names))
        )
        tags_by_name = {tag.name: tag for tag in existing_tags}
        for name in normalized_names:
            if name not in tags_by_name:
                tag = TagModel(user_id=user_id, name=name, auto=False)
                self._session.add(tag)
                await self._session.flush()
                tags_by_name[name] = tag
        model.tags = [tags_by_name[name] for name in normalized_names]


def _suggested_questions(
    suggested_questions: list[str] | None,
    visual_metadata: dict[str, object] | None,
) -> list[str]:
    if suggested_questions:
        return list(suggested_questions)
    if not visual_metadata:
        return []
    value = visual_metadata.get("suggested_questions")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _connection_terms(title: str | None, summary: str | None) -> set[str]:
    text = f"{title or ''} {summary or ''}".lower()
    terms = {"".join(character for character in token if character.isalnum()) for token in text.split()}
    stop_words = {"about", "after", "and", "are", "for", "from", "into", "that", "the", "this", "with", "your"}
    return {term for term in terms if len(term) >= 4 and term not in stop_words}


def _activity_connection_score(last_used_at: datetime | None) -> int:
    if last_used_at is None:
        return 0
    now = datetime.now(UTC)
    if last_used_at.tzinfo is None:
        last_used_at = last_used_at.replace(tzinfo=UTC)
    age = now - last_used_at
    if age <= timedelta(days=7):
        return 2
    if age <= timedelta(days=30):
        return 1
    return 0
