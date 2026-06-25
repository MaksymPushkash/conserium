from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from src.integrations.web_resource_fetcher import HTTPWebResourceFetcher
from src.kit.exceptions import ResourceNotFoundException, ValidationException
from src.knowledge_gaps.service import area_coverage, rubric_for_topic, to_knowledge_gap_area_response
from src.learning_goals.repository import LearningGoalRecord, LearningGoalRepository, LearningGoalResourceRecord
from src.learning_goals.schemas import (
    CreateLearningGoalPayload,
    LearningGoalRequest,
    LearningGoalResponse,
    LearningGoalResult,
    LearningGoalUpdateRequest,
    RankedLearningResource,
    RankedLearningResourceResponse,
    SuggestedLearningResource,
    SuggestedLearningResourceResponse,
    UpdateLearningGoalPayload,
)
from src.postgres import AsyncSession  # noqa: TC001
from src.topics.repository import TopicRepository

if TYPE_CHECKING:
    from src.knowledge_gaps.schemas import KnowledgeGapArea, KnowledgeGapAreaResponse
    from src.topics.repository import TopicDocumentRecord


LEARNING_RESOURCE_CACHE_TTL = timedelta(hours=24)


class LearningGoalService:
    async def list_goals(self, session: AsyncSession, *, user_id: UUID) -> list[LearningGoalResponse]:
        goals = await self._list_results(session, user_id=user_id)
        return [to_learning_goal_response(goal) for goal in goals]

    async def reminders(self, session: AsyncSession, *, user_id: UUID) -> list[LearningGoalResponse]:
        goals = await self._list_results(session, user_id=user_id)
        return [
            to_learning_goal_response(goal)
            for goal in goals
            if goal.status == "active" and goal.deadline_status in {"due_soon", "overdue"} and goal.missing_count > 0
        ]

    async def create(self, session: AsyncSession, *, user_id: UUID, body: LearningGoalRequest) -> LearningGoalResponse:
        dto = CreateLearningGoalPayload(
            user_id=user_id,
            topic=body.topic,
            description=body.description,
            target_date=body.target_date,
        )
        topic = normalize_goal_topic(dto.topic)
        record = await LearningGoalRepository.from_session(session).create(
            goal_id=uuid4(),
            user_id=dto.user_id,
            topic=topic,
            description=normalize_optional_text(dto.description),
            target_date=dto.target_date,
        )
        detail = await TopicRepository.from_session(session).get_detail_by_name(dto.user_id, name=topic, document_limit=200)
        await session.flush()
        return to_learning_goal_response(learning_goal_result(record, detail.documents if detail else []))

    async def update(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        goal_id: UUID,
        body: LearningGoalUpdateRequest,
    ) -> LearningGoalResponse:
        dto = UpdateLearningGoalPayload(
            user_id=user_id,
            goal_id=goal_id,
            topic=body.topic,
            description=body.description,
            target_date=body.target_date,
            status=body.status,
        )
        repository = LearningGoalRepository.from_session(session)
        existing = await repository.get_by_id(dto.goal_id)
        if existing is None or existing.user_id != dto.user_id:
            raise ResourceNotFoundException("learning goal not found")
        topic = normalize_goal_topic(dto.topic) if dto.topic is not None else existing.topic
        status = normalize_goal_status(dto.status) if dto.status is not None else existing.status
        record = await repository.update(
            goal_id=dto.goal_id,
            topic=topic,
            description=normalize_optional_text(dto.description) if dto.description is not None else existing.description,
            target_date=dto.target_date if dto.target_date is not None else existing.target_date,
            status=status,
        )
        detail = await TopicRepository.from_session(session).get_detail_by_name(dto.user_id, name=topic, document_limit=200)
        await session.flush()
        return to_learning_goal_response(learning_goal_result(record, detail.documents if detail else []))

    async def delete(self, session: AsyncSession, *, user_id: UUID, goal_id: UUID) -> None:
        repository = LearningGoalRepository.from_session(session)
        existing = await repository.get_by_id(goal_id)
        if existing is None or existing.user_id != user_id:
            raise ResourceNotFoundException("learning goal not found")
        await repository.delete(goal_id)
        await session.flush()

    async def rank_resources(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        goal_id: UUID,
        refresh: bool,
        web_resource_fetcher: HTTPWebResourceFetcher,
    ) -> list[RankedLearningResourceResponse]:
        repository = LearningGoalRepository.from_session(session)
        record = await repository.get_by_id(goal_id)
        if record is None or record.user_id != user_id:
            raise ResourceNotFoundException("learning goal not found")
        if not refresh:
            cached = await repository.list_cached_resources(
                goal_id=goal_id,
                refreshed_after=datetime.now(UTC) - LEARNING_RESOURCE_CACHE_TTL,
            )
            if cached:
                return [to_ranked_resource_response(ranked_resource_from_record(resource)) for resource in cached]
        detail = await TopicRepository.from_session(session).get_detail_by_name(user_id, name=record.topic, document_limit=200)
        await session.flush()

        goal = learning_goal_result(record, detail.documents if detail else [])
        ranked = await self._rank_resources(goal.suggested_resources, web_resource_fetcher)
        ranked = sorted(ranked, key=lambda resource: resource.score, reverse=True)
        refreshed_at = datetime.now(UTC)
        ranked = [replace(resource, cached=False, refreshed_at=refreshed_at) for resource in ranked]
        await self._store_resources(session, goal_id, ranked)
        return [to_ranked_resource_response(resource) for resource in ranked]

    async def _list_results(self, session: AsyncSession, *, user_id: UUID) -> list[LearningGoalResult]:
        records = await LearningGoalRepository.from_session(session).list_by_user_id(user_id)
        details = await TopicRepository.from_session(session).get_details_by_names(
            user_id,
            names={record.topic for record in records},
            document_limit=200,
        )
        goals: list[LearningGoalResult] = []
        for record in records:
            detail = details.get(record.topic.casefold())
            goals.append(learning_goal_result(record, detail.documents if detail else []))
        return goals

    async def _rank_resources(
        self,
        resources: list[SuggestedLearningResource],
        web_resource_fetcher: HTTPWebResourceFetcher,
    ) -> list[RankedLearningResource]:
        semaphore = asyncio.Semaphore(3)

        async def rank(resource: SuggestedLearningResource) -> RankedLearningResource:
            async with semaphore:
                fetched = await web_resource_fetcher.fetch(resource.url) if resource.url else None
            return RankedLearningResource(
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
            result if isinstance(result, RankedLearningResource) else unfetched_ranked_resource(resource, result)
            for resource, result in zip(resources, ranked, strict=True)
        ]

    async def _store_resources(
        self,
        session: AsyncSession,
        goal_id: UUID,
        resources: list[RankedLearningResource],
    ) -> None:
        await LearningGoalRepository.from_session(session).replace_cached_resources(
            goal_id=goal_id,
            resources=[
                LearningGoalResourceRecord(
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
        await session.flush()



def learning_goal_result(record: LearningGoalRecord, documents: list[TopicDocumentRecord]) -> LearningGoalResult:
    areas = [area_coverage(area, documents) for area in rubric_for_topic(record.topic)]
    covered_count = sum(1 for area in areas if area.covered)
    missing_count = len(areas) - covered_count
    missing = missing_areas(areas)
    return LearningGoalResult(
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


def ranked_resource_from_record(record: LearningGoalResourceRecord) -> RankedLearningResource:
    return RankedLearningResource(
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


def missing_areas(areas: list[KnowledgeGapArea]) -> list[KnowledgeGapArea]:
    return [area for area in areas if not area.covered]


def suggested_resources(topic: str, gaps: list[KnowledgeGapArea]) -> list[SuggestedLearningResource]:
    return [
        SuggestedLearningResource(
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


def resource_score(resource: SuggestedLearningResource, fetched: bool) -> float:
    score = 0.4
    if resource.url:
        score += 0.35
    if fetched:
        score += 0.25
    return min(score, 1.0)


def unfetched_ranked_resource(resource: SuggestedLearningResource, exc: BaseException | None = None) -> RankedLearningResource:
    return RankedLearningResource(
        area=resource.area,
        title=resource.title,
        search_query=resource.search_query,
        reason=resource.reason,
        url=resource.url,
        excerpt=None,
        score=resource_score(resource, fetched=False),
        warning="Resource refresh failed." if exc else "Resource metadata unavailable.",
    )


def deadline_status(record: LearningGoalRecord) -> str:
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


def days_remaining(record: LearningGoalRecord) -> int | None:
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


def get_learning_goal_service() -> LearningGoalService:
    return learning_goals


def get_web_resource_fetcher() -> HTTPWebResourceFetcher:
    return HTTPWebResourceFetcher()


def to_learning_goal_response(dto: LearningGoalResult) -> LearningGoalResponse:
    return LearningGoalResponse(
        id=dto.id,
        user_id=dto.user_id,
        topic=dto.topic,
        description=dto.description,
        target_date=dto.target_date,
        status=dto.status,
        progress_ratio=dto.progress_ratio,
        covered_count=dto.covered_count,
        missing_count=dto.missing_count,
        gaps=[to_gap_area_response(area) for area in dto.gaps],
        recommended_next_areas=dto.recommended_next_areas,
        suggested_resources=[to_suggested_resource_response(resource) for resource in dto.suggested_resources],
        deadline_status=dto.deadline_status,
        days_remaining=dto.days_remaining,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
    )


def to_gap_area_response(dto: KnowledgeGapArea) -> KnowledgeGapAreaResponse:
    return to_knowledge_gap_area_response(dto)


def to_suggested_resource_response(dto: SuggestedLearningResource) -> SuggestedLearningResourceResponse:
    return SuggestedLearningResourceResponse(
        area=dto.area,
        title=dto.title,
        search_query=dto.search_query,
        reason=dto.reason,
        url=dto.url,
    )


def to_ranked_resource_response(dto: RankedLearningResource) -> RankedLearningResourceResponse:
    return RankedLearningResourceResponse(
        area=dto.area,
        title=dto.title,
        search_query=dto.search_query,
        reason=dto.reason,
        url=dto.url,
        excerpt=dto.excerpt,
        score=dto.score,
        warning=dto.warning,
        cached=dto.cached,
        refreshed_at=dto.refreshed_at,
    )



learning_goals = LearningGoalService()

__all__ = [
    "LEARNING_RESOURCE_CACHE_TTL",
    "LearningGoalService",
    "get_learning_goal_service",
    "get_web_resource_fetcher",
    "learning_goal_result",
    "learning_goals",
    "normalize_goal_status",
    "normalize_goal_topic",
    "normalize_optional_text",
    "ranked_resource_from_record",
    "resource_score",
    "to_learning_goal_response",
    "to_ranked_resource_response",
    "unfetched_ranked_resource",
]
