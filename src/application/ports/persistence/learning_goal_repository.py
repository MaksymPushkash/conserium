from abc import ABC, abstractmethod
from datetime import date, datetime
from uuid import UUID

from src.application.dtos.learning_goal_dtos import LearningGoalRecordDTO, LearningGoalResourceRecordDTO


class ILearningGoalRepository(ABC):
    @abstractmethod
    async def list_by_user_id(self, user_id: UUID) -> list[LearningGoalRecordDTO]: ...

    @abstractmethod
    async def get_by_id(self, goal_id: UUID) -> LearningGoalRecordDTO | None: ...

    @abstractmethod
    async def create(
        self,
        *,
        goal_id: UUID,
        user_id: UUID,
        topic: str,
        description: str | None,
        target_date: date | None,
    ) -> LearningGoalRecordDTO: ...

    @abstractmethod
    async def update(
        self,
        *,
        goal_id: UUID,
        topic: str,
        description: str | None,
        target_date: date | None,
        status: str,
    ) -> LearningGoalRecordDTO: ...

    @abstractmethod
    async def delete(self, goal_id: UUID) -> None: ...

    @abstractmethod
    async def list_cached_resources(
        self,
        *,
        goal_id: UUID,
        refreshed_after: datetime,
    ) -> list[LearningGoalResourceRecordDTO]: ...

    @abstractmethod
    async def replace_cached_resources(
        self,
        *,
        goal_id: UUID,
        resources: list[LearningGoalResourceRecordDTO],
    ) -> None: ...

    @abstractmethod
    async def delete_cached_resources(self, goal_id: UUID) -> None: ...
