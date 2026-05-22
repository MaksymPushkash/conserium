from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

from src.application.dtos.learning_goal_dtos import (
    CreateLearningGoalDTO,
    LearningGoalDTO,
    LearningGoalRecordDTO,
    LearningGoalResourceRecordDTO,
    RankedLearningResourceDTO,
    SuggestedLearningResourceDTO,
    UpdateLearningGoalDTO,
)
from src.application.use_cases.knowledge_gaps import area_coverage, rubric_for_topic
from src.domain.exceptions import ResourceNotFoundException, ValidationException

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.dtos.knowledge_gap_dtos import KnowledgeGapAreaDTO
    from src.application.ports.integrations.web_resource_fetcher import IWebResourceFetcher
    from src.application.ports.persistence.topic_repository import TopicDocumentRecord
    from src.application.ports.persistence.unit_of_work import IUnitOfWork


LEARNING_RESOURCE_CACHE_TTL = timedelta(hours=24)


class ListLearningGoalsUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: UUID) -> list[LearningGoalDTO]:
        async with self._uow:
            records = await self._uow.learning_goal_repo.list_by_user_id(user_id)
            topic_documents = await self._load_topic_documents(records, user_id)
        return [learning_goal_to_dto(record, topic_documents.get(record.topic.casefold(), [])) for record in records]

    async def _load_topic_documents(
        self,
        records: list[LearningGoalRecordDTO],
        user_id: UUID,
    ) -> dict[str, list[TopicDocumentRecord]]:
        details = await self._uow.topic_repo.get_details_by_names(
            user_id,
            names={record.topic for record in records},
            document_limit=200,
        )
        return {topic: detail.documents for topic, detail in details.items()}


class ListLearningGoalRemindersUseCase:
    def __init__(self, list_goals: ListLearningGoalsUseCase) -> None:
        self._list_goals = list_goals

    async def __call__(self, *, user_id: UUID) -> list[LearningGoalDTO]:
        goals = await self._list_goals(user_id=user_id)
        return [
            goal
            for goal in goals
            if goal.status == "active" and goal.deadline_status in {"due_soon", "overdue"} and goal.missing_count > 0
        ]


class CreateLearningGoalUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, dto: CreateLearningGoalDTO) -> LearningGoalDTO:
        topic = normalize_goal_topic(dto.topic)
        async with self._uow:
            record = await self._uow.learning_goal_repo.create(
                goal_id=uuid4(),
                user_id=dto.user_id,
                topic=topic,
                description=normalize_optional_text(dto.description),
                target_date=dto.target_date,
            )
            detail = await self._uow.topic_repo.get_detail_by_name(dto.user_id, name=topic, document_limit=200)
            await self._uow.commit()
        return learning_goal_to_dto(record, detail.documents if detail else [])


class UpdateLearningGoalUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, dto: UpdateLearningGoalDTO) -> LearningGoalDTO:
        async with self._uow:
            existing = await self._uow.learning_goal_repo.get_by_id(dto.goal_id)
            if existing is None or existing.user_id != dto.user_id:
                raise ResourceNotFoundException("learning goal not found")
            topic = normalize_goal_topic(dto.topic) if dto.topic is not None else existing.topic
            status = normalize_goal_status(dto.status) if dto.status is not None else existing.status
            record = await self._uow.learning_goal_repo.update(
                goal_id=dto.goal_id,
                topic=topic,
                description=normalize_optional_text(dto.description) if dto.description is not None else existing.description,
                target_date=dto.target_date if dto.target_date is not None else existing.target_date,
                status=status,
            )
            detail = await self._uow.topic_repo.get_detail_by_name(dto.user_id, name=topic, document_limit=200)
            await self._uow.commit()
        return learning_goal_to_dto(record, detail.documents if detail else [])


class DeleteLearningGoalUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: UUID, goal_id: UUID) -> None:
        async with self._uow:
            existing = await self._uow.learning_goal_repo.get_by_id(goal_id)
            if existing is None or existing.user_id != user_id:
                raise ResourceNotFoundException("learning goal not found")
            await self._uow.learning_goal_repo.delete(goal_id)
            await self._uow.commit()


class RankLearningGoalResourcesUseCase:
    def __init__(self, uow: IUnitOfWork, web_resource_fetcher: IWebResourceFetcher) -> None:
        self._uow = uow
        self._web_resource_fetcher = web_resource_fetcher

    async def __call__(self, *, user_id: UUID, goal_id: UUID, refresh: bool = False) -> list[RankedLearningResourceDTO]:
        async with self._uow:
            record = await self._uow.learning_goal_repo.get_by_id(goal_id)
            if record is None or record.user_id != user_id:
                raise ResourceNotFoundException("learning goal not found")
            if not refresh:
                cached = await self._uow.learning_goal_repo.list_cached_resources(
                    goal_id=goal_id,
                    refreshed_after=datetime.now(UTC) - LEARNING_RESOURCE_CACHE_TTL,
                )
                if cached:
                    return [ranked_resource_from_record(resource) for resource in cached]
            detail = await self._uow.topic_repo.get_detail_by_name(user_id, name=record.topic, document_limit=200)

        goal = learning_goal_to_dto(record, detail.documents if detail else [])
        ranked = await self._rank_resources(goal.suggested_resources)
        ranked = sorted(ranked, key=lambda resource: resource.score, reverse=True)
        refreshed_at = datetime.now(UTC)
        ranked = [replace(resource, cached=False, refreshed_at=refreshed_at) for resource in ranked]
        await self._store_resources(goal_id, ranked)
        return ranked

    async def _store_resources(self, goal_id: UUID, resources: list[RankedLearningResourceDTO]) -> None:
        async with self._uow:
            await self._uow.learning_goal_repo.replace_cached_resources(
                goal_id=goal_id,
                resources=[
                    LearningGoalResourceRecordDTO(
                        goal_id=goal_id,
                        area=resource.area,
                        title=resource.title,
                        search_query=resource.search_query,
                        reason=resource.reason,
                        url=resource.url,
                        excerpt=resource.excerpt,
                        score=resource.score,
                        refreshed_at=resource.refreshed_at or datetime.now(UTC),
                    )
                    for resource in resources
                ],
            )
            await self._uow.commit()

    async def _rank_resources(self, resources: list[SuggestedLearningResourceDTO]) -> list[RankedLearningResourceDTO]:
        semaphore = asyncio.Semaphore(3)

        async def rank(resource: SuggestedLearningResourceDTO) -> RankedLearningResourceDTO:
            async with semaphore:
                fetched = await self._web_resource_fetcher.fetch(resource.url) if resource.url else None
            return RankedLearningResourceDTO(
                area=resource.area,
                title=fetched.title if fetched and fetched.title else resource.title,
                search_query=resource.search_query,
                reason=resource.reason,
                url=resource.url,
                excerpt=fetched.excerpt if fetched else None,
                score=resource_score(resource, fetched is not None),
                warning=None if fetched else "Resource metadata unavailable.",
            )

        ranked = await asyncio.gather(*(rank(resource) for resource in resources), return_exceptions=True)
        return [
            result if isinstance(result, RankedLearningResourceDTO) else unfetched_ranked_resource(resource, result)
            for resource, result in zip(resources, ranked, strict=True)
        ]


def learning_goal_to_dto(record: LearningGoalRecordDTO, documents: list[TopicDocumentRecord]) -> LearningGoalDTO:
    areas = [area_coverage(area, documents) for area in rubric_for_topic(record.topic)]
    covered_count = sum(1 for area in areas if area.covered)
    missing_count = len(areas) - covered_count
    missing = missing_areas(areas)
    return LearningGoalDTO(
        id=record.id,
        user_id=record.user_id,
        topic=record.topic,
        description=record.description,
        target_date=record.target_date,
        status=record.status,
        progress_ratio=covered_count / len(areas) if areas else 0,
        covered_count=covered_count,
        missing_count=missing_count,
        gaps=missing,
        recommended_next_areas=[area.name for area in missing[:3]],
        suggested_resources=suggested_resources(record.topic, missing),
        deadline_status=deadline_status(record),
        days_remaining=days_remaining(record),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def ranked_resource_from_record(record: LearningGoalResourceRecordDTO) -> RankedLearningResourceDTO:
    return RankedLearningResourceDTO(
        area=record.area,
        title=record.title,
        search_query=record.search_query,
        reason=record.reason,
        url=record.url,
        excerpt=record.excerpt,
        score=record.score,
        warning=None,
        cached=True,
        refreshed_at=record.refreshed_at,
    )


def missing_areas(areas: list[KnowledgeGapAreaDTO]) -> list[KnowledgeGapAreaDTO]:
    return [area for area in areas if not area.covered]


def suggested_resources(topic: str, gaps: list[KnowledgeGapAreaDTO]) -> list[SuggestedLearningResourceDTO]:
    return [
        SuggestedLearningResourceDTO(
            area=area.name,
            title=f"{topic}: {area.name}",
            search_query=f"{topic} {area.name} practical guide",
            reason=f"Add coverage for {area.name}.",
            url=resource_url(topic, area.name),
        )
        for area in gaps[:3]
    ]


def resource_url(topic: str, area: str) -> str | None:
    normalized_topic = topic.casefold()
    normalized_area = area.casefold()
    if "fastapi" in normalized_topic:
        return "https://fastapi.tiangolo.com/"
    if "python" in normalized_topic:
        if "async" in normalized_area:
            return "https://docs.python.org/3/library/asyncio.html"
        if "typing" in normalized_area:
            return "https://docs.python.org/3/library/typing.html"
        return "https://docs.python.org/3/tutorial/"
    if "react" in normalized_topic or "next" in normalized_topic:
        return "https://react.dev/learn"
    if "typescript" in normalized_topic or "javascript" in normalized_topic:
        return "https://www.typescriptlang.org/docs/"
    if "postgres" in normalized_topic or "sql" in normalized_topic or "database" in normalized_topic:
        return "https://www.postgresql.org/docs/current/"
    if "docker" in normalized_topic:
        return "https://docs.docker.com/get-started/"
    if "kubernetes" in normalized_topic or "k8s" in normalized_topic:
        return "https://kubernetes.io/docs/home/"
    if "cloud" in normalized_topic or "aws" in normalized_topic:
        return "https://docs.aws.amazon.com/"
    return None


def resource_score(resource: SuggestedLearningResourceDTO, fetched: bool) -> float:
    score = 0.4
    if resource.url:
        score += 0.35
    if fetched:
        score += 0.25
    return min(score, 1.0)


def unfetched_ranked_resource(resource: SuggestedLearningResourceDTO, exc: BaseException | None = None) -> RankedLearningResourceDTO:
    return RankedLearningResourceDTO(
        area=resource.area,
        title=resource.title,
        search_query=resource.search_query,
        reason=resource.reason,
        url=resource.url,
        excerpt=None,
        score=resource_score(resource, fetched=False),
        warning="Resource refresh failed." if exc else "Resource metadata unavailable.",
    )


def deadline_status(record: LearningGoalRecordDTO) -> str:
    if record.status == "completed":
        return "completed"
    remaining = days_remaining(record)
    if remaining is None:
        return "none"
    if remaining < 0:
        return "overdue"
    if remaining <= 7:
        return "due_soon"
    return "upcoming"


def days_remaining(record: LearningGoalRecordDTO) -> int | None:
    if record.target_date is None:
        return None
    return (record.target_date - datetime.now(UTC).date()).days


def normalize_goal_topic(topic: str | None) -> str:
    normalized = (topic or "").strip()
    if not normalized:
        raise ValidationException("topic is required")
    if len(normalized) > 160:
        raise ValidationException("topic is too long")
    return normalized


def normalize_goal_status(status: str | None) -> str:
    normalized = (status or "").strip().casefold()
    if normalized not in {"active", "paused", "completed"}:
        raise ValidationException("invalid learning goal status")
    return normalized


def normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
