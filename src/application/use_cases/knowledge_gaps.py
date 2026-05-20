from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.application.dtos.knowledge_gap_dtos import KnowledgeGapAreaDTO, KnowledgeGapDTO
from src.domain.exceptions import ResourceNotFoundException

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.ports.persistence.topic_repository import TopicDocumentRecord
    from src.application.ports.persistence.unit_of_work import IUnitOfWork


class GetKnowledgeGapsUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: UUID, topic: str) -> KnowledgeGapDTO:
        normalized_topic = topic.strip()
        if not normalized_topic:
            raise ResourceNotFoundException("topic not found")
        async with self._uow:
            detail = await self._uow.topic_repo.get_detail_by_name(
                user_id,
                name=normalized_topic,
                document_limit=200,
            )
        if detail is None:
            raise ResourceNotFoundException("topic not found")

        rubric = rubric_for_topic(normalized_topic)
        areas = [area_coverage(area, detail.documents) for area in rubric]
        covered_count = sum(1 for area in areas if area.covered)
        missing_count = len(areas) - covered_count
        return KnowledgeGapDTO(
            topic=detail.topic.name,
            covered_count=covered_count,
            missing_count=missing_count,
            coverage_ratio=covered_count / len(areas) if areas else 0,
            areas=areas,
        )


@dataclass(frozen=True, slots=True)
class RubricArea:
    name: str
    keywords: tuple[str, ...]


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


def area_coverage(area: RubricArea, documents: list[TopicDocumentRecord]) -> KnowledgeGapAreaDTO:
    evidence_titles: list[str] = []
    for document in documents:
        if document_matches_area(document, area):
            evidence_titles.append(document.title)
    return KnowledgeGapAreaDTO(
        name=area.name,
        covered=bool(evidence_titles),
        evidence_count=len(evidence_titles),
        evidence_titles=evidence_titles[:5],
    )


def document_matches_area(document: TopicDocumentRecord, area: RubricArea) -> bool:
    haystack = normalize_text(f"{document.title}\n{document.summary or ''}")
    return any(normalize_text(keyword) in haystack for keyword in area.keywords)


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9+#]+", " ", value.casefold())).strip()
