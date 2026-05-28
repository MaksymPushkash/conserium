import re

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter

from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.core.metrics import metrics_registry
from src.domain.value_objects.document_status import DocumentStatus
from src.presentation.dependencies.auth import CurrentUser

router = APIRouter(prefix="/observability", tags=["observability"])


@router.get("/summary")
@inject
async def observability_summary(current_user: CurrentUser, uow: FromDishka[IUnitOfWork]) -> dict[str, object]:
    metrics_text = metrics_registry.render_prometheus()
    query_latency_sum = _metric_value(metrics_text, "conserium_query_latency_seconds_sum")
    query_latency_count = _metric_value(metrics_text, "conserium_query_latency_seconds_count")
    retrieval_requests = _metric_value(metrics_text, "conserium_retrieval_requests_total")
    retrieval_hits = _metric_value(metrics_text, "conserium_retrieval_hits_total")
    async with uow:
        failed_documents = await uow.document_repo.count_by_user_id(current_user.id, status=DocumentStatus.FAILED)
    return {
        "query_latency": {
            "count": query_latency_count,
            "average_seconds": query_latency_sum / query_latency_count if query_latency_count else 0.0,
        },
        "retrieval": {
            "hit_rate": retrieval_hits / retrieval_requests if retrieval_requests else 0.0,
            "requests": retrieval_requests,
            "hits": retrieval_hits,
        },
        "documents": {
            "failed_processing_count": failed_documents,
        },
        "openai": {
            "estimated_cost_usd": _metric_value(metrics_text, "conserium_openai_estimated_cost_usd"),
        },
        "queues": _queue_depths(metrics_text),
    }


def _metric_value(metrics_text: str, name: str) -> float:
    total = 0.0
    for line in metrics_text.splitlines():
        if line.startswith("#") or not line.startswith(name):
            continue
        parts = line.rsplit(" ", maxsplit=1)
        if len(parts) == 2:
            total += float(parts[1])
    return total


def _queue_depths(metrics_text: str) -> dict[str, float]:
    depths: dict[str, float] = {}
    pattern = re.compile(r'^conserium_queue_depth\{queue="([^"]+)"\}\s+(.+)$')
    for line in metrics_text.splitlines():
        match = pattern.match(line)
        if match:
            depths[match.group(1)] = float(match.group(2))
    return depths
