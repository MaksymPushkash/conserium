from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import delete

from src.models.conflict import ClaimConflictModel, DocumentClaimModel

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from src.conflicts.schemas import ConflictClaimRecord, PersistedConflictRecord


class ConflictRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_claims_for_documents(
        self,
        *,
        user_id: UUID,
        document_ids: list[UUID],
        claims: list[ConflictClaimRecord],
    ) -> None:
        if document_ids:
            await self._session.execute(
                delete(DocumentClaimModel).where(
                    DocumentClaimModel.user_id == user_id,
                    DocumentClaimModel.document_id.in_(document_ids),
                )
            )
        self._session.add_all(
            DocumentClaimModel(
                user_id=user_id,
                document_id=claim.document_id,
                subject=claim.subject,
                polarity=claim.polarity,
                evidence=claim.evidence,
            )
            for claim in claims
        )

    async def replace_conflicts(
        self,
        *,
        user_id: UUID,
        collection_id: UUID | None,
        conflicts: list[PersistedConflictRecord],
    ) -> None:
        where_clause = [ClaimConflictModel.user_id == user_id]
        if collection_id is None:
            where_clause.append(ClaimConflictModel.collection_id.is_(None))
        else:
            where_clause.append(ClaimConflictModel.collection_id == collection_id)
        await self._session.execute(delete(ClaimConflictModel).where(*where_clause))
        self._session.add_all(
            ClaimConflictModel(
                user_id=user_id,
                collection_id=collection_id,
                subject=conflict.subject,
                summary=conflict.summary,
                document_ids=[str(document_id) for document_id in conflict.document_ids],
                evidence=conflict.evidence,
                score=conflict.score,
            )
            for conflict in conflicts
        )


__all__ = ["ConflictRepository"]
