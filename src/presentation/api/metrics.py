from collections.abc import Iterator
from contextlib import contextmanager

from src.core.metrics import metrics_registry


@contextmanager
def query_latency_timer(mode: str) -> Iterator[None]:
    with metrics_registry.timer(
        "conserium_query_latency_seconds",
        "Latency of query execution in seconds.",
        labels={"mode": mode},
    ):
        yield


def observe_query_latency(mode: str, value: float) -> None:
    metrics_registry.observe_histogram(
        "conserium_query_latency_seconds",
        "Latency of query execution in seconds.",
        labels={"mode": mode},
        value=value,
    )


@contextmanager
def ingestion_latency_timer(endpoint: str) -> Iterator[None]:
    with metrics_registry.timer(
        "conserium_ingestion_latency_seconds",
        "Latency of ingestion HTTP requests in seconds.",
        labels={"endpoint": endpoint},
    ):
        yield


def record_http_request(endpoint: str, *, method: str = "POST", status: str) -> None:
    metrics_registry.inc_counter(
        "conserium_http_requests_total",
        "HTTP requests handled by selected endpoints.",
        labels={"endpoint": endpoint, "method": method, "status": status},
    )
