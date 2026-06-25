from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from src.kit.exceptions import ResourceNotFoundException, ValidationException
from src.review.repository import FlashcardRecord, LearningPathRecord, QuizRecord
from src.review.schemas import (
    FlashcardResponse,
    GenerateFlashcardsPayload,
    GenerateLearningPathPayload,
    GenerateQuizPayload,
    LearningPathResponse,
    QuizResponse,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from src.models.document import DocumentModel


def flashcard_response(record: FlashcardRecord) -> FlashcardResponse:
    return FlashcardResponse(
        id=record.id,
        user_id=record.user_id,
        scope_type=record.scope_type,
        collection_id=record.collection_id,
        topic=record.topic,
        source_document_id=record.source_document_id,
        source_chunk_id=record.source_chunk_id,
        question=record.question,
        answer=record.answer,
        citation_metadata=record.citation_metadata,
        due_at=record.due_at,
        interval_days=record.interval_days,
        ease_factor=record.ease_factor,
        review_count=record.review_count,
        source_title=record.source_title,
        created_at=record.created_at or record.due_at,
        updated_at=record.updated_at,
    )


def build_flashcards_for_document(
    document: DocumentModel,
    chunks: Sequence[object],
    *,
    now: datetime,
    existing_questions: set[str],
    scope_type: str = "document",
    scope_collection_id: uuid.UUID | None = None,
    scope_topic: str | None = None,
) -> list[FlashcardRecord]:
    candidates: list[tuple[str, str, uuid.UUID | None, dict[str, object]]] = []
    for question in document.suggested_questions[:3]:
        answer = document.summary or _chunk_answer(chunks) or document.raw_content or ""
        candidates.append((question, answer, None, {"source": "suggested_question"}))
    if document.summary:
        candidates.append((f"What is the key idea in {document.title}?", document.summary, None, {"source": "summary"}))
    chunk_answer = _chunk_answer(chunks)
    if chunk_answer:
        chunk_id = getattr(chunks[0], "id", None) if chunks else None
        page_number = getattr(chunks[0], "page_number", None) if chunks else None
        candidates.append(
            (
                f"What should you remember from {document.title}?",
                chunk_answer,
                chunk_id,
                {"source": "chunk", "page_number": page_number},
            )
        )
    records: list[FlashcardRecord] = []
    seen = set(existing_questions)
    for question, answer, chunk_id, citation_metadata in candidates:
        normalized = question.strip().lower()
        if not question.strip() or not answer.strip() or normalized in seen:
            continue
        seen.add(normalized)
        records.append(
            FlashcardRecord(
                id=uuid.uuid4(),
                user_id=document.user_id,
                scope_type=scope_type,
                collection_id=scope_collection_id,
                topic=scope_topic,
                source_document_id=document.id,
                source_chunk_id=chunk_id,
                question=question.strip(),
                answer=_trim(answer.strip(), 1200),
                citation_metadata=citation_metadata,
                due_at=now,
                interval_days=0,
                ease_factor=2.5,
                review_count=0,
                source_title=document.title,
                created_at=now,
                updated_at=None,
            )
        )
    return records


def flashcard_scope_type(dto: GenerateFlashcardsPayload) -> str:
    if dto.document_id is not None:
        return "document"
    if dto.topic and dto.topic.strip():
        return "topic"
    if dto.collection_id is not None:
        return "collection"
    return "workspace"


def flashcard_scope_collection_id(dto: GenerateFlashcardsPayload, document: DocumentModel) -> uuid.UUID | None:
    if dto.collection_id is not None:
        return dto.collection_id
    if dto.document_id is not None:
        return document.collection_id
    return None


def build_quiz_questions_for_document(document: DocumentModel, chunks: Sequence[object], *, remaining: int) -> list[dict[str, object]]:
    if remaining <= 0:
        return []
    answer_text = document.summary or _chunk_answer(chunks) or document.raw_content or ""
    if not answer_text.strip():
        return []
    options = [
        _trim(answer_text.strip(), 220),
        "No saved source supports this.",
        "The document only contains metadata.",
        "The topic is unrelated to this source.",
    ]
    questions: list[dict[str, object]] = []
    prompts = document.suggested_questions[:2] or [f"What is the key idea in {document.title}?"]
    for prompt in prompts:
        questions.append(
            {
                "id": str(uuid.uuid4()),
                "question": prompt.strip(),
                "options": [{"id": str(index), "text": option} for index, option in enumerate(options)],
                "correct_option_id": "0",
                "explanation": _trim(answer_text.strip(), 500),
                "weak_area": document.tags[0] if document.tags else document.title,
                "source_document_id": str(document.id),
                "source_title": document.title,
            }
        )
        if len(questions) >= remaining:
            break
    return questions


def quiz_scope_type(dto: GenerateQuizPayload) -> str:
    if dto.document_id is not None:
        return "document"
    if dto.topic and dto.topic.strip():
        return "topic"
    if dto.collection_id is not None:
        return "collection"
    return "workspace"


def quiz_scope_collection_id(dto: GenerateQuizPayload, document: DocumentModel) -> uuid.UUID | None:
    if dto.collection_id is not None:
        return dto.collection_id
    if dto.document_id is not None:
        return document.collection_id
    return None


def quiz_title(dto: GenerateQuizPayload, source_document: DocumentModel) -> str:
    if dto.topic and dto.topic.strip():
        return f"Quiz: {dto.topic.strip()}"
    if dto.collection_id is not None:
        return "Collection quiz"
    return f"Quiz: {source_document.title}"


def quiz_response(record: QuizRecord) -> QuizResponse:
    return QuizResponse(
        id=record.id,
        user_id=record.user_id,
        scope_type=record.scope_type,
        collection_id=record.collection_id,
        topic=record.topic,
        source_document_id=record.source_document_id,
        title=record.title,
        questions=record.questions,
        source_title=record.source_title,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def score_quiz_answers(
    questions: list[dict[str, object]],
    submitted_answers: list[dict[str, object]],
) -> tuple[int, int, list[dict[str, object]], list[str]]:
    submitted_by_question = {str(answer.get("question_id")): str(answer.get("option_id")) for answer in submitted_answers}
    scored_answers: list[dict[str, object]] = []
    weak_areas: list[str] = []
    score = 0
    for question in questions:
        question_id = str(question.get("id"))
        selected = submitted_by_question.get(question_id, "")
        correct = str(question.get("correct_option_id", ""))
        is_correct = bool(selected) and selected == correct
        if is_correct:
            score += 1
        else:
            area = str(question.get("weak_area") or question.get("source_title") or "Review")
            if area not in weak_areas:
                weak_areas.append(area)
        scored_answers.append(
            {
                "question_id": question_id,
                "selected_option_id": selected,
                "correct_option_id": correct,
                "correct": is_correct,
                "weak_area": question.get("weak_area"),
            }
        )
    return score, len(questions), scored_answers, weak_areas


def build_learning_steps(documents: list[DocumentModel], *, limit: int) -> list[dict[str, object]]:
    steps: list[dict[str, object]] = []
    for document in documents[: max(1, min(limit, 12))]:
        focus = document.tags[0] if document.tags else document.title
        steps.append(
            {
                "id": str(uuid.uuid4()),
                "title": document.title,
                "focus": focus,
                "summary": document.summary or document.raw_content or "Review this saved source.",
                "source_document_id": str(document.id),
                "status": "todo",
            }
        )
    return steps


def learning_path_scope_type(dto: GenerateLearningPathPayload) -> str:
    if dto.document_id is not None:
        return "document"
    if dto.topic and dto.topic.strip():
        return "topic"
    if dto.collection_id is not None:
        return "collection"
    return "workspace"


def learning_path_scope_collection_id(dto: GenerateLearningPathPayload, document: DocumentModel) -> uuid.UUID | None:
    if dto.collection_id is not None:
        return dto.collection_id
    if dto.document_id is not None:
        return document.collection_id
    return None


def learning_path_title(dto: GenerateLearningPathPayload, source_document: DocumentModel) -> str:
    if dto.topic and dto.topic.strip():
        return f"Learning path: {dto.topic.strip()}"
    if dto.collection_id is not None:
        return "Collection learning path"
    return f"Learning path: {source_document.title}"


def learning_path_response(record: LearningPathRecord) -> LearningPathResponse:
    return LearningPathResponse(
        id=record.id,
        user_id=record.user_id,
        scope_type=record.scope_type,
        collection_id=record.collection_id,
        topic=record.topic,
        source_document_id=record.source_document_id,
        title=record.title,
        steps=record.steps,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def normalize_step_status(status: str) -> str:
    normalized = status.strip().lower()
    if normalized not in {"todo", "done"}:
        raise ValidationException("learning path step status must be todo or done")
    return normalized


def update_step_status(steps: list[dict[str, object]], *, step_id: str, status: str) -> list[dict[str, object]]:
    updated: list[dict[str, object]] = []
    matched = False
    for step in steps:
        next_step = dict(step)
        if str(next_step.get("id")) == step_id:
            next_step["status"] = status
            matched = True
        updated.append(next_step)
    if not matched:
        raise ResourceNotFoundException("learning path step not found")
    return updated


def _chunk_answer(chunks: Sequence[object]) -> str | None:
    if not chunks:
        return None
    content = str(getattr(chunks[0], "content", "")).strip()
    return _trim(content, 1200) if content else None


def _trim(value: str, limit: int) -> str:
    return value if len(value) <= limit else f"{value[: limit - 3].rstrip()}..."
