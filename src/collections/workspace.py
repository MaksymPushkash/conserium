from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from src.collections.schemas import (
    CollectionWorkspaceDocumentResponse,
    CollectionWorkspaceGapResponse,
    CollectionWorkspaceTopicResponse,
)
from src.documents.activity import activity_temperature

if TYPE_CHECKING:
    from datetime import datetime

    from src.documents.repository import DocumentActivitySummary
    from src.models.document import DocumentModel


def workspace_document(
    document: DocumentModel,
    activity: DocumentActivitySummary | None,
) -> CollectionWorkspaceDocumentResponse:
    last_used_at = activity.last_used_at if activity and activity.last_used_at else document.created_at
    return CollectionWorkspaceDocumentResponse(
        id=document.id,
        title=document.title,
        type=document.type.value,
        status=document.status.value,
        summary=document.summary,
        tags=document.tags or [],
        activity_temperature=activity_temperature(last_used_at),
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def workspace_topics(documents: list[DocumentModel]) -> list[CollectionWorkspaceTopicResponse]:
    counts: Counter[str] = Counter()
    last_seen: dict[str, datetime] = {}
    for document in documents:
        for tag in document.tags or []:
            counts[tag] += 1
            current = last_seen.get(tag)
            if current is None or document.created_at > current:
                last_seen[tag] = document.created_at
    return [
        CollectionWorkspaceTopicResponse(
            name=name,
            document_count=count,
            last_document_at=last_seen[name],
        )
        for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def workspace_gaps(
    *,
    total_documents: int,
    ready_documents: int,
    failed_documents: int,
    topic_count: int,
) -> list[CollectionWorkspaceGapResponse]:
    gaps: list[CollectionWorkspaceGapResponse] = []
    if total_documents == 0:
        gaps.append(
            CollectionWorkspaceGapResponse(
                title="No sources",
                reason="Add documents before using collection-scoped retrieval.",
                severity="high",
            )
        )
    if total_documents > 0 and ready_documents == 0:
        gaps.append(
            CollectionWorkspaceGapResponse(
                title="No ready documents",
                reason="Sources exist, but none are searchable yet.",
                severity="high",
            )
        )
    if failed_documents:
        gaps.append(
            CollectionWorkspaceGapResponse(
                title="Failed processing",
                reason=f"{failed_documents} document(s) need retry or replacement.",
                severity="medium",
            )
        )
    if ready_documents > 0 and topic_count == 0:
        gaps.append(
            CollectionWorkspaceGapResponse(
                title="No topic coverage",
                reason="Ready documents do not have tags or extracted topics yet.",
                severity="medium",
            )
        )
    if ready_documents < 3 and total_documents > 0:
        gaps.append(
            CollectionWorkspaceGapResponse(
                title="Thin evidence base",
                reason="Add at least three ready sources for stronger synthesis.",
                severity="low",
            )
        )
    return gaps


def preview_text(value: str | None) -> str | None:
    if not value:
        return None
    return value[:240]
