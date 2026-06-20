from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from sqlalchemy import delete, select

from src.models.learning_goal import LearningGoalModel, LearningGoalResourceModel

if TYPE_CHECKING:
    from datetime import date, datetime
    from uuid import UUID

    from src.postgres import AsyncSession


@final
@dataclass(frozen=True, slots=True)
class LearningGoalResourceRecordDTO:
    goal_id: UUID
    area: str
    title: str
    search_query: str
    reason: str
    url: str | None
    excerpt: str | None
    score: float
    refreshed_at: datetime


@final
@dataclass(frozen=True, slots=True)
class LearningGoalRecordDTO:
    id: UUID
    user_id: UUID
    topic: str
    description: str | None
    target_date: date | None
    status: str
    created_at: datetime
    updated_at: datetime | None


class LearningGoalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @classmethod
    def from_session(cls, session: AsyncSession) -> LearningGoalRepository:
        return cls(session)

    async def list_by_user_id(self, user_id: UUID) -> list[LearningGoalRecordDTO]:
        result = await self._session.execute(
            select(LearningGoalModel)
            .where(LearningGoalModel.user_id == user_id)
            .order_by(LearningGoalModel.created_at.desc())
        )
        return [self._to_dto(model) for model in result.scalars().all()]

    async def get_by_id(self, goal_id: UUID) -> LearningGoalRecordDTO | None:
        result = await self._session.execute(select(LearningGoalModel).where(LearningGoalModel.id == goal_id))
        model = result.scalar_one_or_none()
        return self._to_dto(model) if model else None

    async def create(
        self,
        *,
        goal_id: UUID,
        user_id: UUID,
        topic: str,
        description: str | None,
        target_date: date | None,
    ) -> LearningGoalRecordDTO:
        model = LearningGoalModel(
            id=goal_id,
            user_id=user_id,
            topic=topic,
            description=description,
            target_date=target_date,
            status="active",
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_dto(model)

    async def update(
        self,
        *,
        goal_id: UUID,
        topic: str,
        description: str | None,
        target_date: date | None,
        status: str,
    ) -> LearningGoalRecordDTO:
        result = await self._session.execute(select(LearningGoalModel).where(LearningGoalModel.id == goal_id))
        model = result.scalar_one()
        model.topic = topic
        model.description = description
        model.target_date = target_date
        model.status = status
        await self.delete_cached_resources(goal_id)
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_dto(model)

    async def delete(self, goal_id: UUID) -> None:
        await self._session.execute(delete(LearningGoalModel).where(LearningGoalModel.id == goal_id))

    async def list_cached_resources(
        self,
        *,
        goal_id: UUID,
        refreshed_after: datetime,
    ) -> list[LearningGoalResourceRecordDTO]:
        result = await self._session.execute(
            select(LearningGoalResourceModel)
            .where(
                LearningGoalResourceModel.goal_id == goal_id,
                LearningGoalResourceModel.refreshed_at >= refreshed_after,
            )
            .order_by(LearningGoalResourceModel.score.desc())
        )
        return [self._resource_to_dto(model) for model in result.scalars().all()]

    async def replace_cached_resources(
        self,
        *,
        goal_id: UUID,
        resources: list[LearningGoalResourceRecordDTO],
    ) -> None:
        await self.delete_cached_resources(goal_id)
        self._session.add_all(
            LearningGoalResourceModel(
                goal_id=resource.goal_id,
                area=resource.area,
                title=resource.title,
                search_query=resource.search_query,
                reason=resource.reason,
                url=resource.url,
                excerpt=resource.excerpt,
                score=resource.score,
                refreshed_at=resource.refreshed_at,
            )
            for resource in resources
        )
        await self._session.flush()

    async def delete_cached_resources(self, goal_id: UUID) -> None:
        await self._session.execute(delete(LearningGoalResourceModel).where(LearningGoalResourceModel.goal_id == goal_id))

    @staticmethod
    def _to_dto(model: LearningGoalModel) -> LearningGoalRecordDTO:
        return LearningGoalRecordDTO(
            id=model.id,
            user_id=model.user_id,
            topic=model.topic,
            description=model.description,
            target_date=model.target_date,
            status=model.status,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _resource_to_dto(model: LearningGoalResourceModel) -> LearningGoalResourceRecordDTO:
        return LearningGoalResourceRecordDTO(
            goal_id=model.goal_id,
            area=model.area,
            title=model.title,
            search_query=model.search_query,
            reason=model.reason,
            url=model.url,
            excerpt=model.excerpt,
            score=model.score,
            refreshed_at=model.refreshed_at,
        )


__all__ = [
    "LearningGoalRecordDTO",
    "LearningGoalRepository",
    "LearningGoalResourceRecordDTO",
]
