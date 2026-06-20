from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.models.document import DocumentModel
from src.models.tag import TagModel

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


class DocumentTagSync:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def sync_auto_tags(
        self,
        *,
        user_id: uuid.UUID,
        document_id: uuid.UUID,
        tag_names: list[str],
    ) -> list[str]:
        normalized_names = sorted({name.strip().lower() for name in tag_names if name.strip()})
        document = await self._session.scalar(
            select(DocumentModel)
            .options(selectinload(DocumentModel.tag_models))
            .where(DocumentModel.id == document_id, DocumentModel.user_id == user_id)
        )
        if document is None:
            raise ValueError(f"Document {document_id} not found for tag sync")

        manual_tags = [tag for tag in document.tag_models if not tag.auto]
        existing_tags = await self._session.scalars(
            select(TagModel).where(TagModel.user_id == user_id, TagModel.name.in_(normalized_names))
        )
        tags_by_name = {tag.name: tag for tag in existing_tags}

        for name in normalized_names:
            if name not in tags_by_name:
                new_tag = TagModel(user_id=user_id, name=name, auto=True)
                self._session.add(new_tag)
                await self._session.flush()
                tags_by_name[name] = new_tag

        document.tag_models = manual_tags + [tags_by_name[name] for name in normalized_names]
        return document.tags
