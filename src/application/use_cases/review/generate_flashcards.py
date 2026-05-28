import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from src.application.dtos.review_dtos import GenerateFlashcardsDTO, GenerateFlashcardsResultDTO
from src.application.ports.persistence.flashcard_repository import FlashcardRecord
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.review.mapping import flashcard_to_dto
from src.domain.entities.document_entity import DocumentEntity
from src.domain.exceptions import DocumentAccessDeniedException, DocumentNotFoundException
from src.domain.value_objects.document_status import DocumentStatus


class GenerateFlashcardsUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, dto: GenerateFlashcardsDTO) -> GenerateFlashcardsResultDTO:
        now = datetime.now(UTC)
        async with self._uow:
            documents = await self._load_documents(dto)
            records: list[FlashcardRecord] = []
            remaining = max(1, min(dto.limit, 20))
            for document in documents:
                existing = await self._uow.flashcard_repo.existing_questions_for_document(
                    user_id=dto.user_id,
                    document_id=document.id,
                )
                chunks = await self._uow.chunk_repo.get_by_document_id(document.id)
                for record in build_flashcards_for_document(
                    document,
                    chunks,
                    now=now,
                    existing_questions=existing,
                    scope_type=flashcard_scope_type(dto),
                    scope_collection_id=flashcard_scope_collection_id(dto, document),
                    scope_topic=dto.topic.strip() if dto.topic and dto.topic.strip() else None,
                ):
                    records.append(record)
                    remaining -= 1
                    if remaining <= 0:
                        break
                if remaining <= 0:
                    break
            created = await self._uow.flashcard_repo.create_many(records) if records else []
            await self._uow.commit()

        return GenerateFlashcardsResultDTO(
            items=[flashcard_to_dto(record) for record in created],
            created_count=len(created),
        )

    async def _load_documents(self, dto: GenerateFlashcardsDTO) -> list[DocumentEntity]:
        if dto.document_id is not None:
            document = await self._uow.document_repo.get_by_id(dto.document_id)
            if document is None:
                raise DocumentNotFoundException("document not found")
            if document.user_id != dto.user_id:
                raise DocumentAccessDeniedException("document access denied")
            if document.status != DocumentStatus.READY:
                return []
            return [document]
        if dto.topic:
            detail = await self._uow.topic_repo.get_detail_by_name(
                dto.user_id,
                name=dto.topic,
                document_limit=max(1, min(dto.limit * 3, 60)),
            )
            if detail is None:
                return []
            documents: list[DocumentEntity] = []
            for topic_document in detail.documents:
                document = await self._uow.document_repo.get_by_id(topic_document.id)
                if document and document.user_id == dto.user_id and document.status == DocumentStatus.READY:
                    documents.append(document)
            return documents
        return await self._uow.document_repo.get_by_user_id(
            dto.user_id,
            limit=max(1, min(dto.limit * 3, 60)),
            collection_id=dto.collection_id,
            status=DocumentStatus.READY,
        )


def build_flashcards_for_document(
    document: DocumentEntity,
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


def flashcard_scope_type(dto: GenerateFlashcardsDTO) -> str:
    if dto.document_id is not None:
        return "document"
    if dto.topic and dto.topic.strip():
        return "topic"
    if dto.collection_id is not None:
        return "collection"
    return "workspace"


def flashcard_scope_collection_id(dto: GenerateFlashcardsDTO, document: DocumentEntity) -> uuid.UUID | None:
    if dto.collection_id is not None:
        return dto.collection_id
    if dto.document_id is not None:
        return document.collection_id
    return None


def _chunk_answer(chunks: Sequence[object]) -> str | None:
    if not chunks:
        return None
    content = str(getattr(chunks[0], "content", "")).strip()
    return _trim(content, 1200) if content else None


def _trim(value: str, limit: int) -> str:
    return value if len(value) <= limit else f"{value[: limit - 3].rstrip()}..."
