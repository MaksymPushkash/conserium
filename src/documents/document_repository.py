from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import ColumnElement, delete, exists, func, or_, select
from sqlalchemy.orm import selectinload

from src.documents.repository import RelatedDocumentRecord
from src.documents.status import DocumentStatus
from src.models.document import DocumentModel
from src.models.document_activity import DocumentActivityModel
from src.models.tag import TagModel
from src.models.topic import TopicModel

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from src.documents.types import DocumentType


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @classmethod
    def from_session(cls, session: AsyncSession) -> DocumentRepository:
        return cls(session)

    async def get_by_id(self, document_id: UUID) -> DocumentModel | None:
        result = await self._session.execute(
            select(DocumentModel)
            .options(selectinload(DocumentModel.tag_models))
            .where(DocumentModel.id == document_id)
        )
        return result.scalar_one_or_none()

    async def get_by_user_id(
        self,
        user_id: UUID,
        *,
        limit: int = 50,
        offset: int = 0,
        document_type: DocumentType | None = None,
        collection_id: UUID | None = None,
        status: DocumentStatus | None = None,
        tag_name: str | None = None,
    ) -> list[DocumentModel]:
        conditions = self._document_conditions(
            user_id,
            document_type=document_type,
            collection_id=collection_id,
            status=status,
            tag_name=tag_name,
        )
        result = await self._session.execute(
            select(DocumentModel)
            .options(selectinload(DocumentModel.tag_models))
            .where(*conditions)
            .order_by(DocumentModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def create(self, document: DocumentModel) -> None:
        self._session.add(document)
        if document.tags:
            await self._session.flush()
            await self._sync_initial_tags(document, document.user_id, document.tags)

    async def update(self, document: DocumentModel) -> None:
        self._session.add(document)

    async def delete(self, document_id: UUID) -> None:
        await self._session.execute(delete(DocumentModel).where(DocumentModel.id == document_id))

    async def add_manual_tags(self, *, document_id: UUID, user_id: UUID, tag_names: list[str]) -> None:
        normalized_names = sorted({name.strip().lower() for name in tag_names if name.strip()})
        if not normalized_names:
            return

        document = await self._session.scalar(
            select(DocumentModel)
            .options(selectinload(DocumentModel.tag_models))
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

        current_names = {tag.name for tag in document.tag_models}
        document.tag_models = [
            *document.tag_models,
            *[tags_by_name[name] for name in normalized_names if name not in current_names],
        ]

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
        tag_name: str | None = None,
    ) -> int:
        conditions = self._document_conditions(
            user_id,
            document_type=document_type,
            collection_id=collection_id,
            status=status,
            tag_name=tag_name,
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
    ) -> tuple[list[DocumentModel], dict[DocumentStatus, int]]:
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
            .options(selectinload(DocumentModel.tag_models), selectinload(DocumentModel.topics))
            .where(DocumentModel.id == document_id, DocumentModel.user_id == user_id)
        )
        if target is None:
            return []

        target_tags = {tag.name for tag in target.tag_models}
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
            overlap_conditions.append(DocumentModel.tag_models.any(TagModel.name.in_(target_tags)))
        if target_topics:
            overlap_conditions.append(DocumentModel.topics.any(TopicModel.name.in_(target_topics)))
        if overlap_conditions:
            conditions.append(or_(*overlap_conditions))

        candidate_rows = await self._session.execute(
            select(DocumentModel, activity_subquery.c.last_used_at)
            .outerjoin(activity_subquery, activity_subquery.c.document_id == DocumentModel.id)
            .options(selectinload(DocumentModel.tag_models), selectinload(DocumentModel.topics))
            .where(*conditions)
            .order_by(activity_subquery.c.last_used_at.desc().nullslast(), DocumentModel.created_at.desc())
            .limit(500)
        )
        records: list[RelatedDocumentRecord] = []
        for candidate, last_used_at in candidate_rows.all():
            reasons: list[str] = []
            score = 0
            shared_tags = sorted(target_tags.intersection({tag.name for tag in candidate.tag_models}))
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
                    document=candidate,
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
        tag_name: str | None = None,
    ) -> list[ColumnElement[bool]]:
        conditions: list[ColumnElement[bool]] = [DocumentModel.user_id == user_id]
        if document_type is not None:
            conditions.append(DocumentModel.type == document_type)
        if tag_name:
            conditions.append(DocumentModel.tag_models.any(TagModel.name == tag_name.strip().lower()))
        if collection_id is not None:
            conditions.append(DocumentModel.collection_id == collection_id)
        if status is not None:
            conditions.append(DocumentModel.status == status)
        return conditions

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
        model.tag_models = [tags_by_name[name] for name in normalized_names]


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
