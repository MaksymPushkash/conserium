from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.dtos.compare_dtos import CompareEvidenceRowDTO, CompareResultDTO
from src.application.ports.persistence.compare_repository import ICompareRepository
from src.infrastructure.database.models.comparison import ComparisonModel
from src.infrastructure.database.repositories.draft_repository import sources_from_json, sources_to_json


class SQLAlchemyCompareRepository(ICompareRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, result: CompareResultDTO) -> CompareResultDTO:
        model = ComparisonModel(
            id=result.id,
            user_id=result.user_id,
            collection_id=result.collection_id,
            left_document_id=result.left_document_id,
            right_document_id=result.right_document_id,
            left_title=result.left_title,
            right_title=result.right_title,
            dimensions=result.dimensions,
            markdown=result.markdown,
            summary=result.summary,
            evidence_rows=evidence_to_json(result.evidence_rows),
            source_metadata=sources_to_json(result.sources),
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_dto(model)

    async def get_by_id(self, comparison_id: UUID) -> CompareResultDTO | None:
        result = await self._session.execute(select(ComparisonModel).where(ComparisonModel.id == comparison_id))
        model = result.scalar_one_or_none()
        return self._to_dto(model) if model else None

    async def list_by_user_id(
        self,
        *,
        user_id: UUID,
        collection_id: UUID | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[CompareResultDTO]:
        statement = select(ComparisonModel).where(ComparisonModel.user_id == user_id)
        if collection_id is not None:
            statement = statement.where(ComparisonModel.collection_id == collection_id)
        result = await self._session.execute(statement.order_by(ComparisonModel.created_at.desc()).limit(limit).offset(offset))
        return [self._to_dto(model) for model in result.scalars().all()]

    async def count_by_user_id(
        self,
        *,
        user_id: UUID,
        collection_id: UUID | None = None,
    ) -> int:
        statement = select(func.count()).select_from(ComparisonModel).where(ComparisonModel.user_id == user_id)
        if collection_id is not None:
            statement = statement.where(ComparisonModel.collection_id == collection_id)
        result = await self._session.execute(statement)
        return result.scalar_one()

    async def delete(self, comparison_id: UUID) -> None:
        await self._session.execute(delete(ComparisonModel).where(ComparisonModel.id == comparison_id))

    @staticmethod
    def _to_dto(model: ComparisonModel) -> CompareResultDTO:
        return CompareResultDTO(
            id=model.id,
            user_id=model.user_id,
            collection_id=model.collection_id,
            left_document_id=model.left_document_id,
            right_document_id=model.right_document_id,
            left_title=model.left_title,
            right_title=model.right_title,
            dimensions=list(model.dimensions),
            markdown=model.markdown,
            summary=model.summary,
            evidence_rows=evidence_from_json(model.evidence_rows),
            sources=sources_from_json(model.source_metadata),
            created_at=model.created_at,
        )


def evidence_to_json(rows: list[CompareEvidenceRowDTO]) -> list[dict[str, object]]:
    return [
        {
            "dimension": row.dimension,
            "left_evidence": row.left_evidence,
            "right_evidence": row.right_evidence,
            "assessment": row.assessment,
            "left_source_id": str(row.left_source_id) if row.left_source_id is not None else None,
            "right_source_id": str(row.right_source_id) if row.right_source_id is not None else None,
            "left_citation": row.left_citation,
            "right_citation": row.right_citation,
        }
        for row in rows
    ]


def evidence_from_json(rows: list[dict[str, object]]) -> list[CompareEvidenceRowDTO]:
    return [
        CompareEvidenceRowDTO(
            dimension=str(row.get("dimension") or ""),
            left_evidence=str(row["left_evidence"]) if row.get("left_evidence") is not None else None,
            right_evidence=str(row["right_evidence"]) if row.get("right_evidence") is not None else None,
            assessment=str(row.get("assessment") or ""),
            left_source_id=UUID(str(row["left_source_id"])) if row.get("left_source_id") is not None else None,
            right_source_id=UUID(str(row["right_source_id"])) if row.get("right_source_id") is not None else None,
            left_citation=str(row["left_citation"]) if row.get("left_citation") is not None else None,
            right_citation=str(row["right_citation"]) if row.get("right_citation") is not None else None,
        )
        for row in rows
    ]
