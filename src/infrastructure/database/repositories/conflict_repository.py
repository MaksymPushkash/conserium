from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.dtos.conflict_dtos import ConflictClaimRecordDTO, PersistedConflictRecordDTO
from src.application.ports.persistence.conflict_repository import IConflictRepository
from src.infrastructure.database.models.conflict import ClaimConflictModel, DocumentClaimModel


class SQLAlchemyConflictRepository(IConflictRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_claims_for_documents(
        self,
        *,
        user_id: UUID,
        document_ids: list[UUID],
        claims: list[ConflictClaimRecordDTO],
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
        conflicts: list[PersistedConflictRecordDTO],
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
