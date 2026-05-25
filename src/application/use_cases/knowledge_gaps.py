from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.application.dtos.knowledge_gap_dtos import KnowledgeGapAreaDTO, KnowledgeGapDTO, KnowledgeGapListDTO
from src.application.dtos.note_dtos import CreateNoteDTO, NoteDTO
from src.domain.exceptions import ResourceNotFoundException, ValidationException
from src.domain.value_objects.document_status import DocumentStatus

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.ports.persistence.topic_repository import TopicDocumentRecord
    from src.application.ports.persistence.unit_of_work import IUnitOfWork
    from src.application.use_cases.documents.note_use_cases import CreateNoteUseCase
    from src.domain.entities.document_entity import DocumentEntity


class GetKnowledgeGapsUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: UUID, topic: str, collection_id: UUID | None = None) -> KnowledgeGapDTO:
        normalized_topic = topic.strip()
        if not normalized_topic:
            raise ResourceNotFoundException("topic not found")
        async with self._uow:
            await ensure_collection_owner(self._uow, user_id=user_id, collection_id=collection_id)
            if collection_id is not None:
                documents = await self._uow.document_repo.get_by_user_id(
                    user_id,
                    collection_id=collection_id,
                    status=DocumentStatus.READY,
                    limit=200,
                )
                topic_documents = [
                    topic_document_from_document(document)
                    for document in documents
                    if normalized_topic.casefold() in {tag.casefold() for tag in document.tags}
                ]
                if not topic_documents:
                    raise ResourceNotFoundException("topic not found")
                return knowledge_gap_dto(
                    topic=normalized_topic,
                    documents=topic_documents,
                    collection_id=collection_id,
                )
            detail = await self._uow.topic_repo.get_detail_by_name(
                user_id,
                name=normalized_topic,
                document_limit=200,
            )
        if detail is None:
            raise ResourceNotFoundException("topic not found")

        return knowledge_gap_dto(
            topic=detail.topic.name,
            documents=detail.documents,
            collection_id=collection_id,
        )


class ListKnowledgeGapsUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: UUID, collection_id: UUID | None = None, limit: int = 12) -> KnowledgeGapListDTO:
        async with self._uow:
            await ensure_collection_owner(self._uow, user_id=user_id, collection_id=collection_id)
            if collection_id is not None:
                documents = await self._uow.document_repo.get_by_user_id(
                    user_id,
                    collection_id=collection_id,
                    status=DocumentStatus.READY,
                    limit=200,
                )
                collection_gaps = collection_topic_gaps(documents, collection_id=collection_id)
                return KnowledgeGapListDTO(items=collection_gaps[:limit], total=len(collection_gaps))

            topics = await self._uow.topic_repo.list_by_user_id(user_id, limit=limit, offset=0)
            gaps: list[KnowledgeGapDTO] = []
            for topic in topics:
                detail = await self._uow.topic_repo.get_detail_by_name(
                    user_id,
                    name=topic.name,
                    document_limit=200,
                )
                if detail is not None:
                    gaps.append(knowledge_gap_dto(topic=detail.topic.name, documents=detail.documents, collection_id=None))
        return KnowledgeGapListDTO(items=gaps, total=len(gaps))


class CreateKnowledgeGapNoteUseCase:
    def __init__(self, create_note: CreateNoteUseCase) -> None:
        self._create_note = create_note

    async def __call__(
        self,
        *,
        user_id: UUID,
        gap_id: str,
        topic: str,
        area_name: str,
        collection_id: UUID | None = None,
    ) -> NoteDTO:
        normalized_topic = topic.strip()
        normalized_area = area_name.strip()
        if not normalized_topic or not normalized_area:
            raise ValidationException("topic and area are required")
        return await self._create_note(
            CreateNoteDTO(
                user_id=user_id,
                collection_id=collection_id,
                title=f"Fill gap: {normalized_topic} - {normalized_area}",
                content=gap_note_content(gap_id=gap_id, topic=normalized_topic, area_name=normalized_area),
                language="en",
            )
        )


@dataclass(frozen=True, slots=True)
class RubricArea:
    name: str
    keywords: tuple[str, ...]
    source_types: tuple[str, ...] = ("article", "reference", "example")


_DEFAULT_RUBRIC = (
    RubricArea("Core concepts", ("fundamental", "concept", "overview", "intro", "basics")),
    RubricArea("Implementation patterns", ("pattern", "architecture", "implementation", "example", "practice")),
    RubricArea("Testing", ("test", "testing", "pytest", "unit test", "integration test")),
    RubricArea("Performance", ("performance", "latency", "optimization", "scaling", "cache")),
    RubricArea("Production operations", ("deploy", "production", "monitoring", "observability", "logging")),
)

_PYTHON_RUBRIC = (
    RubricArea("Syntax and data model", ("syntax", "data model", "dunder", "object model", "descriptor")),
    RubricArea("Functions and generators", ("function", "generator", "yield", "iterator", "iterable")),
    RubricArea("OOP", ("class", "inheritance", "polymorphism", "oop", "object oriented")),
    RubricArea("Async and concurrency", ("async", "asyncio", "concurrency", "thread", "multiprocessing")),
    RubricArea("Testing", ("pytest", "unittest", "test", "mock", "fixture")),
    RubricArea("Typing", ("type hint", "typing", "mypy", "protocol", "generic")),
    RubricArea("Packaging", ("package", "pyproject", "wheel", "dependency", "virtualenv")),
)

_FASTAPI_RUBRIC = (
    RubricArea("Routing", ("route", "router", "endpoint", "path operation")),
    RubricArea("Validation", ("pydantic", "schema", "validation", "request model")),
    RubricArea("Dependency injection", ("dependency", "depends", "injection")),
    RubricArea("Auth", ("auth", "oauth", "jwt", "cookie", "session")),
    RubricArea("Testing", ("test", "pytest", "testclient")),
    RubricArea("Deployment", ("deploy", "uvicorn", "gunicorn", "container", "docker")),
)

_TYPESCRIPT_RUBRIC = (
    RubricArea("Type system", ("type", "interface", "generic", "union", "narrowing", "satisfies")),
    RubricArea("Runtime JavaScript", ("prototype", "closure", "event loop", "promise", "async", "module")),
    RubricArea("Tooling", ("tsconfig", "eslint", "prettier", "vite", "webpack", "build")),
    RubricArea("Testing", ("test", "vitest", "jest", "mock", "playwright")),
    RubricArea("API boundaries", ("schema", "validation", "zod", "contract", "serialization")),
    RubricArea("Performance", ("bundle", "tree shaking", "performance", "profiling", "lazy")),
)

_REACT_RUBRIC = (
    RubricArea("Components", ("component", "props", "composition", "jsx", "children")),
    RubricArea("State and effects", ("state", "effect", "hook", "reducer", "context")),
    RubricArea("Data fetching", ("fetch", "query", "mutation", "cache", "server action")),
    RubricArea("Routing and rendering", ("route", "router", "ssr", "render", "hydration")),
    RubricArea("Forms and validation", ("form", "input", "validation", "controlled", "uncontrolled")),
    RubricArea("Testing", ("test", "testing library", "jest", "vitest", "playwright")),
)

_BACKEND_RUBRIC = (
    RubricArea("API design", ("api", "endpoint", "rest", "graphql", "contract", "schema")),
    RubricArea("Persistence", ("database", "transaction", "repository", "migration", "sql")),
    RubricArea("Auth and permissions", ("auth", "permission", "rbac", "oauth", "jwt", "session")),
    RubricArea("Async jobs", ("queue", "worker", "background", "celery", "job")),
    RubricArea("Testing", ("test", "integration test", "fixture", "mock", "contract test")),
    RubricArea("Operations", ("deploy", "logging", "metrics", "monitoring", "rollback")),
)

_DATABASE_RUBRIC = (
    RubricArea("Schema design", ("schema", "normalization", "index", "constraint", "foreign key")),
    RubricArea("Queries", ("query", "join", "cte", "aggregate", "window function")),
    RubricArea("Transactions", ("transaction", "isolation", "lock", "deadlock", "consistency")),
    RubricArea("Performance", ("explain", "index", "vacuum", "latency", "optimization")),
    RubricArea("Migrations", ("migration", "alembic", "rollback", "ddl", "backfill")),
    RubricArea("Operations", ("backup", "replication", "monitoring", "restore", "connection pool")),
)

_DEVOPS_RUBRIC = (
    RubricArea("Containers", ("docker", "container", "image", "compose", "registry")),
    RubricArea("Orchestration", ("kubernetes", "pod", "deployment", "service", "helm")),
    RubricArea("CI/CD", ("ci", "pipeline", "github actions", "deploy", "release")),
    RubricArea("Observability", ("monitoring", "logging", "metrics", "tracing", "alert")),
    RubricArea("Security", ("secret", "iam", "policy", "vulnerability", "scan")),
    RubricArea("Reliability", ("rollback", "healthcheck", "autoscaling", "incident", "slo")),
)

_CLOUD_RUBRIC = (
    RubricArea("Compute", ("compute", "vm", "container", "serverless", "kubernetes")),
    RubricArea("Storage", ("storage", "s3", "blob", "database", "postgres")),
    RubricArea("Networking", ("network", "vpc", "dns", "load balancer", "cdn")),
    RubricArea("Security", ("iam", "security", "secret", "encryption", "policy")),
    RubricArea("Observability", ("monitoring", "logging", "metrics", "tracing")),
    RubricArea("Cost", ("cost", "billing", "finops", "reserved", "autoscaling")),
)

_SYSTEM_DESIGN_RUBRIC = (
    RubricArea("Requirements", ("requirement", "constraint", "tradeoff", "sla", "slo")),
    RubricArea("Architecture", ("architecture", "service", "boundary", "component", "module")),
    RubricArea("Data design", ("data model", "database", "cache", "consistency", "schema")),
    RubricArea("Scalability", ("scale", "shard", "partition", "queue", "load")),
    RubricArea("Reliability", ("reliability", "failover", "backup", "retry", "idempotency")),
    RubricArea("Observability", ("monitoring", "metrics", "logging", "tracing", "alert")),
)

_SECURITY_RUBRIC = (
    RubricArea("Identity", ("auth", "identity", "oauth", "oidc", "jwt", "session")),
    RubricArea("Authorization", ("permission", "rbac", "abac", "policy", "access control")),
    RubricArea("Data protection", ("encryption", "secret", "hash", "token", "privacy")),
    RubricArea("Threat modeling", ("threat", "attack", "xss", "csrf", "injection")),
    RubricArea("Secure operations", ("audit", "logging", "rotation", "vulnerability", "incident")),
)

_RUBRIC_ALIASES: tuple[tuple[tuple[str, ...], tuple[RubricArea, ...]], ...] = (
    (("fastapi",), _FASTAPI_RUBRIC),
    (("react", "next.js", "nextjs"), _REACT_RUBRIC),
    (("typescript", "javascript", "node.js", "nodejs"), _TYPESCRIPT_RUBRIC),
    (("python",), _PYTHON_RUBRIC),
    (("postgres", "postgresql", "sql", "database"), _DATABASE_RUBRIC),
    (("docker", "kubernetes", "k8s", "devops", "ci/cd", "cicd"), _DEVOPS_RUBRIC),
    (("aws", "azure", "gcp", "cloud"), _CLOUD_RUBRIC),
    (("system design", "architecture"), _SYSTEM_DESIGN_RUBRIC),
    (("security", "auth", "oauth"), _SECURITY_RUBRIC),
    (("backend", "api"), _BACKEND_RUBRIC),
)


def rubric_for_topic(topic: str) -> tuple[RubricArea, ...]:
    normalized = normalize_text(topic)
    for aliases, rubric in _RUBRIC_ALIASES:
        if any(normalize_text(alias) in normalized for alias in aliases):
            return rubric
    return _DEFAULT_RUBRIC


def area_coverage(area: RubricArea, documents: list[TopicDocumentRecord], *, topic: str = "") -> KnowledgeGapAreaDTO:
    evidence_titles: list[str] = []
    for document in documents:
        if document_matches_area(document, area):
            evidence_titles.append(document.title)
    covered = bool(evidence_titles)
    severity = area_severity(covered=covered, evidence_count=len(evidence_titles), document_count=len(documents))
    return KnowledgeGapAreaDTO(
        id=gap_id(topic=topic, area=area.name),
        name=area.name,
        covered=covered,
        evidence_count=len(evidence_titles),
        evidence_titles=evidence_titles[:5],
        why_detected=why_detected(area=area, covered=covered, evidence_count=len(evidence_titles), document_count=len(documents)),
        missing_source_types=[] if covered else list(area.source_types),
        severity=severity,
        rationale=area_rationale(area=area, covered=covered, evidence_count=len(evidence_titles)),
        suggested_actions=suggested_actions(area=area, topic=topic, covered=covered),
    )


def document_matches_area(document: TopicDocumentRecord, area: RubricArea) -> bool:
    haystack = normalize_text(f"{document.title}\n{document.summary or ''}")
    return any(normalize_text(keyword) in haystack for keyword in area.keywords)


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9+#]+", " ", value.casefold())).strip()


def knowledge_gap_dto(
    *,
    topic: str,
    documents: list[TopicDocumentRecord],
    collection_id: UUID | None,
) -> KnowledgeGapDTO:
    rubric = rubric_for_topic(topic)
    areas = [area_coverage(area, documents, topic=topic) for area in rubric]
    covered_count = sum(1 for area in areas if area.covered)
    missing_count = len(areas) - covered_count
    coverage_ratio = covered_count / len(areas) if areas else 0
    missing_source_types = sorted({source_type for area in areas for source_type in area.missing_source_types})
    severity = gap_severity(coverage_ratio=coverage_ratio, missing_count=missing_count, document_count=len(documents))
    return KnowledgeGapDTO(
        id=gap_id(topic=topic, area="summary"),
        topic=topic,
        collection_id=collection_id,
        covered_count=covered_count,
        missing_count=missing_count,
        coverage_ratio=coverage_ratio,
        why_detected=summary_why_detected(topic=topic, coverage_ratio=coverage_ratio, missing_count=missing_count, document_count=len(documents)),
        missing_source_types=missing_source_types,
        severity=severity,
        rationale=summary_rationale(coverage_ratio=coverage_ratio, missing_count=missing_count),
        suggested_actions=summary_actions(topic=topic, missing_source_types=missing_source_types),
        areas=areas,
    )


def collection_topic_gaps(documents: list[DocumentEntity], *, collection_id: UUID) -> list[KnowledgeGapDTO]:
    by_topic: dict[str, list[TopicDocumentRecord]] = {}
    for document in documents:
        for tag in document.tags:
            by_topic.setdefault(tag, []).append(topic_document_from_document(document))
    gaps = [
        knowledge_gap_dto(topic=topic, documents=topic_documents, collection_id=collection_id)
        for topic, topic_documents in by_topic.items()
    ]
    return sorted(gaps, key=lambda gap: (gap.coverage_ratio, -gap.missing_count, gap.topic.casefold()))


def topic_document_from_document(document: DocumentEntity) -> TopicDocumentRecord:
    from src.application.ports.persistence.topic_repository import TopicDocumentRecord

    return TopicDocumentRecord(
        id=document.id,
        title=document.title,
        type=document.type.value,
        status=document.status.value,
        summary=document.summary,
        created_at=document.created_at,
    )


async def ensure_collection_owner(uow: IUnitOfWork, *, user_id: UUID, collection_id: UUID | None) -> None:
    if collection_id is None:
        return
    collection = await uow.collection_repo.get_by_id(collection_id)
    if collection is None or collection.user_id != user_id:
        raise ResourceNotFoundException("collection not found")


def gap_id(*, topic: str, area: str) -> str:
    return f"{slug(topic)}--{slug(area)}"


def slug(value: str) -> str:
    normalized = normalize_text(value).replace(" ", "-")
    return normalized or "gap"


def gap_severity(*, coverage_ratio: float, missing_count: int, document_count: int) -> str:
    if document_count == 0 or coverage_ratio < 0.25:
        return "high"
    if missing_count >= 3 or coverage_ratio < 0.6:
        return "medium"
    return "low"


def area_severity(*, covered: bool, evidence_count: int, document_count: int) -> str:
    if covered and evidence_count >= 2:
        return "low"
    if document_count == 0:
        return "high"
    return "medium" if not covered else "low"


def why_detected(*, area: RubricArea, covered: bool, evidence_count: int, document_count: int) -> str:
    if covered:
        return f"Found {evidence_count} saved source(s) matching {area.name}."
    if document_count == 0:
        return "No ready saved sources exist for this topic."
    return f"No saved source matched the {area.name} rubric keywords."


def area_rationale(*, area: RubricArea, covered: bool, evidence_count: int) -> str:
    if covered:
        return f"{area.name} has evidence in saved material, but may still need review if evidence is thin."
    return f"{area.name} is missing from the current saved context and can weaken retrieval or synthesis."


def suggested_actions(*, area: RubricArea, topic: str, covered: bool) -> list[str]:
    if covered:
        return [f"Review the matched sources for {topic} {area.name}.", "Add a synthesis note if the evidence is fragmented."]
    return [
        f"Add a reference source about {topic} {area.name}.",
        f"Create a note summarizing what Cortex should know about {area.name}.",
        "Ask within this topic before drafting to confirm the gap.",
    ]


def summary_why_detected(*, topic: str, coverage_ratio: float, missing_count: int, document_count: int) -> str:
    if document_count == 0:
        return f"No ready saved sources were found for {topic}."
    return f"{missing_count} rubric area(s) are missing; current coverage is {round(coverage_ratio * 100)}%."


def summary_rationale(*, coverage_ratio: float, missing_count: int) -> str:
    if missing_count == 0:
        return "Saved context covers the current rubric, but source quality still depends on the underlying documents."
    if coverage_ratio < 0.5:
        return "The topic has weak coverage and answers may miss important dimensions."
    return "The topic is usable, but missing areas may reduce answer completeness."


def summary_actions(*, topic: str, missing_source_types: list[str]) -> list[str]:
    source_text = ", ".join(missing_source_types[:3]) if missing_source_types else "supporting sources"
    return [
        f"Add {source_text} for {topic}.",
        f"Create a note that fills the highest-severity missing area for {topic}.",
        f"Draft a short learning plan for {topic}.",
    ]


def gap_note_content(*, gap_id: str, topic: str, area_name: str) -> str:
    return "\n".join(
        [
            f"# Fill gap: {topic} - {area_name}",
            "",
            f"Gap id: {gap_id}",
            f"Topic: {topic}",
            f"Area: {area_name}",
            "",
            "## What to add",
            "",
            f"- Add saved evidence that explains {area_name} for {topic}.",
            "- Include concrete examples, constraints, and source-backed details.",
            "- Link this note back to documents once supporting sources exist.",
        ]
    )
