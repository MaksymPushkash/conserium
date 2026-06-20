import re
from uuid import UUID

from src.observability.metrics_registry import metrics_registry
from src.observability.repository import ObservabilityRepository
from src.observability.schemas import (
    DocumentProcessingSummary,
    ObservabilitySummaryResponse,
    OpenAISummary,
    QueryLatencySummary,
    RetrievalSummary,
)
from src.postgres import AsyncSession


class ObservabilityService:
    async def summary(self, session: AsyncSession, *, user_id: UUID) -> ObservabilitySummaryResponse:
        metrics_text = metrics_registry.render_prometheus()
        query_latency_sum = metric_value(metrics_text, "conserium_query_latency_seconds_sum")
        query_latency_count = metric_value(metrics_text, "conserium_query_latency_seconds_count")
        retrieval_requests = metric_value(metrics_text, "conserium_retrieval_requests_total")
        retrieval_hits = metric_value(metrics_text, "conserium_retrieval_hits_total")
        failed_documents = await ObservabilityRepository(session).count_failed_documents(user_id)
        return ObservabilitySummaryResponse(
            query_latency=QueryLatencySummary(
                count=query_latency_count,
                average_seconds=query_latency_sum / query_latency_count if query_latency_count else 0.0,
            ),
            retrieval=RetrievalSummary(
                hit_rate=retrieval_hits / retrieval_requests if retrieval_requests else 0.0,
                requests=retrieval_requests,
                hits=retrieval_hits,
            ),
            documents=DocumentProcessingSummary(failed_processing_count=failed_documents),
            openai=OpenAISummary(estimated_cost_usd=metric_value(metrics_text, "conserium_openai_estimated_cost_usd")),
            queues=queue_depths(metrics_text),
        )


def get_observability_service() -> ObservabilityService:
    return observability


def metric_value(metrics_text: str, name: str) -> float:
    total = 0.0
    for line in metrics_text.splitlines():
        if line.startswith("#") or not line.startswith(name):
            continue
        parts = line.rsplit(" ", maxsplit=1)
        if len(parts) == 2:
            total += float(parts[1])
    return total


def queue_depths(metrics_text: str) -> dict[str, float]:
    depths: dict[str, float] = {}
    pattern = re.compile(r'^conserium_queue_depth\{queue="([^"]+)"\}\s+(.+)$')
    for line in metrics_text.splitlines():
        match = pattern.match(line)
        if match:
            depths[match.group(1)] = float(match.group(2))
    return depths


observability = ObservabilityService()

__all__ = ["ObservabilityService", "get_observability_service", "metric_value", "observability", "queue_depths"]
