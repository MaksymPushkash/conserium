from __future__ import annotations

from typing import TYPE_CHECKING

from src.documents.activity import activity_temperature
from src.documents.schemas import DocumentResult

if TYPE_CHECKING:
    from src.documents.repository import DocumentActivitySummary
    from src.models.document import DocumentModel


def document_result(document: DocumentModel, activity: DocumentActivitySummary | None = None) -> DocumentResult:
    last_used_at = activity.last_used_at if activity and activity.last_used_at else document.created_at
    return DocumentResult(
        id=document.id,
        user_id=document.user_id,
        collection_id=document.collection_id,
        title=document.title,
        type=document.type,
        status=document.status,
        source_url=document.source_url,
        file_path=document.file_path,
        file_size_bytes=document.file_size_bytes,
        raw_content=document.raw_content,
        summary=document.summary,
        word_count=document.word_count,
        language=document.language,
        entities=document.entities,
        categories=document.categories,
        visual_metadata=document.visual_metadata,
        suggested_questions=document.suggested_questions,
        tags=document.tags,
        last_used_at=last_used_at,
        query_count=activity.query_count if activity else 0,
        citation_count=activity.citation_count if activity else 0,
        activity_temperature=activity_temperature(last_used_at),
        is_duplicate=document.is_duplicate,
        duplicate_of_id=document.duplicate_of_id,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


__all__ = ["document_result"]
