import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID

import structlog
from redis.asyncio import Redis

from src.settings import settings

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class DocumentProcessingStepDTO:
    key: str
    label: str
    state: str
    progress: int
    message: str | None = None


@dataclass(frozen=True, slots=True)
class DocumentStatusDTO:
    document_id: UUID
    status: str
    progress: int
    message: str
    failure_reason: str | None = None
    timeline: list[DocumentProcessingStepDTO] | None = None


class IDocumentStatusCache(ABC):
    @abstractmethod
    async def set_status(
        self,
        document_id: UUID,
        status: str,
        progress: int,
        message: str,
    ) -> None: ...

    @abstractmethod
    async def get_status(self, document_id: UUID) -> DocumentStatusDTO | None: ...

    @abstractmethod
    async def delete_status(self, document_id: UUID) -> None: ...


def _key(document_id: UUID) -> str:
    return f"doc:status:{document_id}"


class RedisDocumentStatusCache(IDocumentStatusCache):
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def set_status(
        self,
        document_id: UUID,
        status: str,
        progress: int,
        message: str,
    ) -> None:
        payload = json.dumps(
            {
                "document_id": str(document_id),
                "status": status,
                "progress": max(0, min(100, progress)),
                "message": message,
                "failure_reason": _failure_reason(status, message),
                "timeline": [_step_payload(step) for step in _build_timeline(status, progress, message)],
            }
        )
        await self._redis.set(_key(document_id), payload, ex=settings.REDIS_DOC_STATUS_TTL)
        logger.debug(
            "Document status updated",
            document_id=str(document_id),
            status=status,
            progress=progress,
        )

    async def get_status(self, document_id: UUID) -> DocumentStatusDTO | None:
        raw = await self._redis.get(_key(document_id))
        if raw is None:
            return None
        data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
        return DocumentStatusDTO(
            document_id=UUID(data["document_id"]),
            status=data["status"],
            progress=int(data["progress"]),
            message=data["message"],
            failure_reason=data.get("failure_reason") or _failure_reason(data["status"], data["message"]),
            timeline=[
                DocumentProcessingStepDTO(
                    key=str(step["key"]),
                    label=str(step["label"]),
                    state=str(step["state"]),
                    progress=int(step["progress"]),
                    message=step.get("message"),
                )
                for step in data.get(
                    "timeline", _default_timeline_payload(data["status"], int(data["progress"]), data["message"])
                )
            ],
        )

    async def delete_status(self, document_id: UUID) -> None:
        await self._redis.delete(_key(document_id))


def _failure_reason(status: str, message: str) -> str | None:
    if status != "FAILED":
        return None
    prefix = "Processing failed: "
    return message.removeprefix(prefix).strip() or message


def _build_timeline(status: str, progress: int, message: str) -> list[DocumentProcessingStepDTO]:
    clamped_progress = max(0, min(100, progress))
    failed = status == "FAILED"
    return [
        _step("uploaded", "Uploaded", 0, clamped_progress, failed, message),
        _step("extracted", "Extracted", 40, clamped_progress, failed, message),
        _step("embedded", "Embedded", 90, clamped_progress, failed, message),
        _step("enriched", "Enriched", 95, clamped_progress, failed, message),
        _step("ready", "Ready", 100, clamped_progress, failed, message, ready=status == "READY"),
    ]


def _step(
    key: str,
    label: str,
    threshold: int,
    progress: int,
    failed: bool,
    message: str,
    *,
    ready: bool = False,
) -> DocumentProcessingStepDTO:
    if failed and progress < threshold:
        state = "failed" if _is_current_failure_stage(progress, threshold) else "pending"
    elif failed or ready or progress >= threshold:
        state = "complete"
    elif _is_current_stage(progress, threshold):
        state = "current"
    else:
        state = "pending"
    return DocumentProcessingStepDTO(
        key=key,
        label=label,
        state=state,
        progress=threshold,
        message=message if state in {"current", "failed"} else None,
    )


def _is_current_stage(progress: int, threshold: int) -> bool:
    thresholds = [0, 40, 90, 95, 100]
    index = thresholds.index(threshold)
    previous = thresholds[index - 1] if index > 0 else -1
    return previous <= progress < threshold


def _is_current_failure_stage(progress: int, threshold: int) -> bool:
    thresholds = [0, 40, 90, 95, 100]
    index = thresholds.index(threshold)
    previous = thresholds[index - 1] if index > 0 else -1
    return previous <= progress < threshold


def _step_payload(step: DocumentProcessingStepDTO) -> dict[str, object]:
    return {
        "key": step.key,
        "label": step.label,
        "state": step.state,
        "progress": step.progress,
        "message": step.message,
    }


def _default_timeline_payload(status: str, progress: int, message: str) -> list[dict[str, object]]:
    return [_step_payload(step) for step in _build_timeline(status, progress, message)]
