from __future__ import annotations

import json
from collections import defaultdict
from contextlib import contextmanager
from threading import Lock
from time import perf_counter
from typing import TYPE_CHECKING, cast

import redis
from amqp.exceptions import NotFound as AMQPNotFound
from kombu.exceptions import KombuError
from redis.exceptions import RedisError

from src.core.config import settings

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

_COUNTER_HELP_KEY = "cortex:metrics:counter_help"
_COUNTER_VALUE_KEY = "cortex:metrics:counter_values"
_GAUGE_HELP_KEY = "cortex:metrics:gauge_help"
_GAUGE_VALUE_KEY = "cortex:metrics:gauge_values"
_SUMMARY_HELP_KEY = "cortex:metrics:summary_help"
_SUMMARY_SUM_KEY = "cortex:metrics:summary_sum"
_SUMMARY_COUNT_KEY = "cortex:metrics:summary_count"


class MetricsRegistry:
    def __init__(self) -> None:
        self._counter_help: dict[str, str] = {}
        self._gauge_help: dict[str, str] = {}
        self._histogram_help: dict[str, str] = {}
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
        self._gauges: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
        self._histogram_sum: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
        self._histogram_count: dict[tuple[str, tuple[tuple[str, str], ...]], int] = defaultdict(int)
        self._lock = Lock()
        self._redis: redis.Redis | None = None

    def inc_counter(
        self,
        name: str,
        help_text: str,
        *,
        labels: dict[str, str] | None = None,
        value: float = 1.0,
    ) -> None:
        key = (name, _normalize_labels(labels))
        with self._lock:
            self._counter_help.setdefault(name, help_text)
            self._counters[key] += value
        self._with_redis(
            lambda client: client.hset(_COUNTER_HELP_KEY, name, help_text),
            lambda client: client.hincrbyfloat(_COUNTER_VALUE_KEY, _field(name, labels), value),
        )

    def add_gauge(
        self,
        name: str,
        help_text: str,
        *,
        labels: dict[str, str] | None = None,
        value: float,
    ) -> None:
        key = (name, _normalize_labels(labels))
        with self._lock:
            self._gauge_help.setdefault(name, help_text)
            self._gauges[key] = max(0.0, self._gauges[key] + value)
        self._with_redis(
            lambda client: client.hset(_GAUGE_HELP_KEY, name, help_text),
            lambda client: client.hincrbyfloat(_GAUGE_VALUE_KEY, _field(name, labels), value),
        )

    def observe_histogram(
        self,
        name: str,
        help_text: str,
        *,
        labels: dict[str, str] | None = None,
        value: float,
    ) -> None:
        key = (name, _normalize_labels(labels))
        with self._lock:
            self._histogram_help.setdefault(name, help_text)
            self._histogram_sum[key] += value
            self._histogram_count[key] += 1
        self._with_redis(
            lambda client: client.hset(_SUMMARY_HELP_KEY, name, help_text),
            lambda client: client.hincrbyfloat(_SUMMARY_SUM_KEY, _field(name, labels), value),
            lambda client: client.hincrby(_SUMMARY_COUNT_KEY, _field(name, labels), 1),
        )

    @contextmanager
    def timer(self, name: str, help_text: str, *, labels: dict[str, str] | None = None) -> Iterator[None]:
        started_at = perf_counter()
        try:
            yield
        finally:
            self.observe_histogram(name, help_text, labels=labels, value=perf_counter() - started_at)

    def render_prometheus(self) -> str:
        redis_snapshot = self._read_redis_snapshot()
        if redis_snapshot is not None:
            lines = _render_snapshot(*redis_snapshot)
        else:
            with self._lock:
                lines = _render_snapshot(
                    self._counter_help,
                    self._counters,
                    self._gauge_help,
                    self._gauges,
                    self._histogram_help,
                    self._histogram_sum,
                    self._histogram_count,
                )
        lines.extend(_render_queue_depth_metrics())
        return "\n".join(lines) + "\n"

    def reset_for_tests(self) -> None:
        with self._lock:
            self._counter_help.clear()
            self._gauge_help.clear()
            self._histogram_help.clear()
            self._counters.clear()
            self._gauges.clear()
            self._histogram_sum.clear()
            self._histogram_count.clear()
        self._with_redis(
            lambda client: client.delete(
                _COUNTER_HELP_KEY,
                _COUNTER_VALUE_KEY,
                _GAUGE_HELP_KEY,
                _GAUGE_VALUE_KEY,
                _SUMMARY_HELP_KEY,
                _SUMMARY_SUM_KEY,
                _SUMMARY_COUNT_KEY,
            )
        )

    def _read_redis_snapshot(
        self,
    ) -> tuple[
        dict[str, str],
        dict[tuple[str, tuple[tuple[str, str], ...]], float],
        dict[str, str],
        dict[tuple[str, tuple[tuple[str, str], ...]], float],
        dict[str, str],
        dict[tuple[str, tuple[tuple[str, str], ...]], float],
        dict[tuple[str, tuple[tuple[str, str], ...]], int],
    ] | None:
        client = self._get_redis()
        if client is None:
            return None
        try:
            counter_help = _sync_hgetall(client, _COUNTER_HELP_KEY)
            counters = _decode_float_metric_hash(_sync_hgetall(client, _COUNTER_VALUE_KEY))
            gauge_help = _sync_hgetall(client, _GAUGE_HELP_KEY)
            gauges = _decode_float_metric_hash(_sync_hgetall(client, _GAUGE_VALUE_KEY))
            histogram_help = _sync_hgetall(client, _SUMMARY_HELP_KEY)
            histogram_sum = _decode_float_metric_hash(_sync_hgetall(client, _SUMMARY_SUM_KEY))
            histogram_count = _decode_int_metric_hash(_sync_hgetall(client, _SUMMARY_COUNT_KEY))
        except (RedisError, OSError):
            return None
        if not any((counter_help, counters, gauge_help, gauges, histogram_help, histogram_sum, histogram_count)):
            return None
        return (
            counter_help,
            counters,
            gauge_help,
            gauges,
            histogram_help,
            histogram_sum,
            histogram_count,
        )

    def _with_redis(self, *operations: Callable[[redis.Redis], object]) -> None:
        client = self._get_redis()
        if client is None:
            return
        try:
            for operation in operations:
                operation(client)
        except (RedisError, OSError):
            return

    def _get_redis(self) -> redis.Redis | None:
        if self._redis is not None:
            return self._redis
        try:
            self._redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
            self._redis.ping()
        except (RedisError, OSError):
            self._redis = None
        return self._redis


def _normalize_labels(labels: dict[str, str] | None) -> tuple[tuple[str, str], ...]:
    if not labels:
        return ()
    return tuple(sorted((key, value) for key, value in labels.items()))


def _field(name: str, labels: dict[str, str] | None) -> str:
    return json.dumps({"name": name, "labels": list(_normalize_labels(labels))}, separators=(",", ":"))


def _sync_hgetall(client: redis.Redis, key: str) -> dict[str, str]:
    return cast("dict[str, str]", client.hgetall(key))


def _decode_field(field: str) -> tuple[str, tuple[tuple[str, str], ...]]:
    data = json.loads(field)
    return str(data["name"]), tuple((str(key), str(value)) for key, value in data["labels"])


def _decode_float_metric_hash(
    payload: dict[str, str],
) -> dict[tuple[str, tuple[tuple[str, str], ...]], float]:
    decoded: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
    for field, value in payload.items():
        decoded[_decode_field(field)] = float(value)
    return decoded


def _decode_int_metric_hash(
    payload: dict[str, str],
) -> dict[tuple[str, tuple[tuple[str, str], ...]], int]:
    decoded: dict[tuple[str, tuple[tuple[str, str], ...]], int] = {}
    for field, value in payload.items():
        decoded[_decode_field(field)] = int(value)
    return decoded


def _format_labels(labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    rendered = ",".join(f'{key}="{value}"' for key, value in labels)
    return f"{{{rendered}}}"


def _render_snapshot(
    counter_help: dict[str, str],
    counters: dict[tuple[str, tuple[tuple[str, str], ...]], float],
    gauge_help: dict[str, str],
    gauges: dict[tuple[str, tuple[tuple[str, str], ...]], float],
    histogram_help: dict[str, str],
    histogram_sum: dict[tuple[str, tuple[tuple[str, str], ...]], float],
    histogram_count: dict[tuple[str, tuple[tuple[str, str], ...]], int],
) -> list[str]:
    lines: list[str] = []
    for name, help_text in sorted(counter_help.items()):
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} counter")
        for (metric_name, labels), value in sorted(counters.items()):
            if metric_name == name:
                lines.append(f"{metric_name}{_format_labels(labels)} {value}")

    for name, help_text in sorted(gauge_help.items()):
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} gauge")
        for (metric_name, labels), value in sorted(gauges.items()):
            if metric_name == name:
                lines.append(f"{metric_name}{_format_labels(labels)} {value}")

    for name, help_text in sorted(histogram_help.items()):
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} summary")
        for (metric_name, labels), total in sorted(histogram_sum.items()):
            if metric_name == name:
                count = histogram_count[(metric_name, labels)]
                lines.append(f"{metric_name}_sum{_format_labels(labels)} {total}")
                lines.append(f"{metric_name}_count{_format_labels(labels)} {count}")
    return lines


def _render_queue_depth_metrics() -> list[str]:
    lines = [
        "# HELP cortex_queue_depth Number of messages currently waiting in each Celery queue.",
        "# TYPE cortex_queue_depth gauge",
    ]
    try:
        from src.infrastructure.celery.app import celery_app

        with celery_app.connection_or_acquire() as connection:
            channel = connection.channel()
            try:
                for queue_def in celery_app.conf.task_queues:
                    bound_queue = queue_def(channel)
                    try:
                        declare_result = bound_queue.queue_declare(passive=True)
                        message_count = int(declare_result.message_count)
                    except AMQPNotFound:
                        continue
                    lines.append(f'cortex_queue_depth{{queue="{queue_def.name}"}} {message_count}')
            finally:
                channel.close()
    except (KombuError, OSError, AttributeError):
        return lines
    return lines


metrics_registry = MetricsRegistry()
