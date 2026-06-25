from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from src.collections.service import WRITE_ROLES, ensure_collection_visible
from src.conflicts.repository import ConflictRepository
from src.conflicts.schemas import (
    ConflictClaimRecord,
    ConflictDetectionResponse,
    ConflictDetectionResult,
    ConflictDocument,
    ConflictDocumentResponse,
    ConflictFinding,
    ConflictFindingResponse,
    PersistedConflictRecord,
)
from src.documents.document_repository import DocumentRepository
from src.documents.status import DocumentStatus
from src.kit.exceptions import ResourceNotFoundException
from src.query.schemas import RefragChunk, RefragContextPackage, RefragRepresentation

if TYPE_CHECKING:
    from collections.abc import Iterable

    from src.kit.ai.llm_service import LLMService
    from src.models.document import DocumentModel
    from src.postgres import AsyncSession


class ConflictService:
    async def detect(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        collection_id: UUID | None,
        limit: int,
        llm_service: LLMService | None,
    ) -> ConflictDetectionResponse:
        documents = await self._load_documents(session, user_id=user_id, collection_id=collection_id, limit=limit)
        claims = extract_conflict_claims(documents)
        conflicts = detect_conflicts(claims)
        conflicts = await validate_conflicts(conflicts, llm_service)
        await self._persist_results(
            session,
            user_id=user_id,
            collection_id=collection_id,
            documents=documents,
            claims=claims,
            conflicts=conflicts,
        )
        return to_conflict_detection_response(
            ConflictDetectionResult(
                collection_id=collection_id,
                analyzed_document_count=len(documents),
                conflicts=conflicts,
            )
        )

    async def _load_documents(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        collection_id: UUID | None,
        limit: int,
    ) -> list[DocumentModel]:
        if collection_id is not None:
            role = await ensure_collection_visible(session, collection_id=collection_id, user_id=user_id)
            if role != "owner" and role not in WRITE_ROLES:
                raise ResourceNotFoundException("collection not found")
        return await DocumentRepository.from_session(session).get_by_user_id(
            user_id,
            limit=limit,
            collection_id=collection_id,
            status=DocumentStatus.READY,
        )

    async def _persist_results(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        collection_id: UUID | None,
        documents: list[DocumentModel],
        claims: list[ConflictClaim],
        conflicts: list[ConflictFinding],
    ) -> None:
        repository = ConflictRepository(session)
        await repository.replace_claims_for_documents(
            user_id=user_id,
            document_ids=[document.id for document in documents],
            claims=[claim.to_record() for claim in claims],
        )
        await repository.replace_conflicts(
            user_id=user_id,
            collection_id=collection_id,
            conflicts=[persisted_conflict(conflict) for conflict in conflicts],
        )
        await session.flush()


@dataclass(frozen=True, slots=True)
class ConflictSignal:
    subject: str
    positive: tuple[str, ...]
    negative: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ConflictClaim:
    document_id: UUID
    document_title: str
    subject: str
    polarity: str
    evidence: str

    def to_record(self) -> ConflictClaimRecord:
        return ConflictClaimRecord(
            document_id=self.document_id,
            subject=self.subject,
            polarity=self.polarity,
            evidence=self.evidence,
        )


_SIGNALS = (
    ConflictSignal(
        subject="ORM usage",
        positive=("use orm", "prefer orm", "orm is recommended", "orm always", "sqlalchemy orm"),
        negative=("avoid orm", "prefer raw sql", "use raw sql", "raw sql for performance", "orm overhead"),
    ),
    ConflictSignal(
        subject="Testing",
        positive=("write tests", "use pytest", "unit test", "integration test", "test coverage"),
        negative=("skip tests", "no tests", "without tests", "testing is unnecessary"),
    ),
    ConflictSignal(
        subject="Typing",
        positive=("type hint", "static typing", "use mypy", "typing is recommended", "protocol"),
        negative=("avoid type hints", "no typing", "without types", "dynamic typing only"),
    ),
    ConflictSignal(
        subject="Async",
        positive=("use async", "asyncio", "concurrent", "parallel requests", "nonblocking"),
        negative=("avoid async", "synchronous only", "blocking is simpler", "do not use asyncio"),
    ),
    ConflictSignal(
        subject="Caching",
        positive=("use cache", "cache results", "redis cache", "memoize"),
        negative=("avoid cache", "do not cache", "cache invalidation risk", "stale cache"),
    ),
)

_SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s+|\n+")


def extract_conflict_claims(documents: list[DocumentModel]) -> list[ConflictClaim]:
    claims: list[ConflictClaim] = []
    for document in documents:
        for sentence in document_sentences(document):
            normalized = sentence.casefold()
            for signal in _SIGNALS:
                if any(term in normalized for term in signal.negative):
                    claims.append(
                        ConflictClaim(
                            document_id=document.id,
                            document_title=document.title,
                            subject=signal.subject,
                            polarity="negative",
                            evidence=sentence,
                        )
                    )
                elif any(term in normalized for term in signal.positive):
                    claims.append(
                        ConflictClaim(
                            document_id=document.id,
                            document_title=document.title,
                            subject=signal.subject,
                            polarity="positive",
                            evidence=sentence,
                        )
                    )
    return claims


def detect_conflicts(claims: list[ConflictClaim]) -> list[ConflictFinding]:
    findings: list[ConflictFinding] = []
    for subject in sorted({claim.subject for claim in claims}):
        positives = _unique_claims(
            claim for claim in claims if claim.subject == subject and claim.polarity == "positive"
        )
        negatives = _unique_claims(
            claim for claim in claims if claim.subject == subject and claim.polarity == "negative"
        )
        if not positives or not negatives:
            continue
        documents = _conflict_documents([*positives, *negatives])
        findings.append(
            ConflictFinding(
                subject=subject,
                summary=f"Saved materials contain opposing guidance about {subject.lower()}.",
                documents=documents,
                evidence=[claim.evidence for claim in [*positives[:2], *negatives[:2]]],
                score=min(1.0, 0.5 + (len(documents) * 0.1)),
            )
        )
    return findings


def document_sentences(document: DocumentModel) -> list[str]:
    text = "\n".join(part for part in (document.title, document.summary, document.raw_content) if part)
    return [sentence.strip() for sentence in _SENTENCE_PATTERN.split(text) if len(sentence.strip()) >= 12]


async def validate_conflicts(
    conflicts: list[ConflictFinding],
    llm_service: LLMService | None,
) -> list[ConflictFinding]:
    if llm_service is None:
        return conflicts
    validated: list[ConflictFinding] = []
    for conflict in conflicts:
        answer = await llm_service.synthesize_answer(
            query=conflict_validation_prompt(conflict),
            context=conflict_context(conflict),
        )
        if not answer.strip().casefold().startswith("rejected"):
            validated.append(conflict)
    return validated


def persisted_conflict(conflict: ConflictFinding) -> PersistedConflictRecord:
    return PersistedConflictRecord(
        subject=conflict.subject,
        summary=conflict.summary,
        document_ids=[document.id for document in conflict.documents],
        evidence=conflict.evidence,
        score=conflict.score,
    )


def conflict_validation_prompt(conflict: ConflictFinding) -> str:
    return (
        "Decide whether the evidence contains a real contradiction. "
        "Reply with CONFIRMED if the sources give opposing guidance, or REJECTED if they do not. "
        f"Subject: {conflict.subject}"
    )


def conflict_context(conflict: ConflictFinding) -> RefragContextPackage:
    chunks = [
        RefragChunk(
            chunk_id=uuid4(),
            document_id=conflict.documents[index % len(conflict.documents)].id,
            document_title=conflict.documents[index % len(conflict.documents)].title,
            original_text=evidence,
            context_text=evidence,
            representation=RefragRepresentation.FULL_TEXT,
            page_number=None,
            chunk_index=index,
            score=conflict.score,
            original_token_count=len(evidence.split()),
            context_token_count=len(evidence.split()),
        )
        for index, evidence in enumerate(conflict.evidence)
        if conflict.documents
    ]
    return RefragContextPackage(
        query=conflict.subject,
        full_text_chunks=chunks,
        compressed_chunks=[],
        discarded_chunks=[],
        total_original_tokens=sum(chunk.original_token_count for chunk in chunks),
        total_context_tokens=sum(chunk.context_token_count for chunk in chunks),
        compression_strategy="conflict-validation",
    )


def _unique_claims(claims: Iterable[ConflictClaim]) -> list[ConflictClaim]:
    unique: dict[tuple[UUID, str], ConflictClaim] = {}
    for claim in claims:
        unique[(claim.document_id, claim.evidence)] = claim
    return list(unique.values())


def _conflict_documents(claims: list[ConflictClaim]) -> list[ConflictDocument]:
    documents: dict[UUID, ConflictDocument] = {}
    for claim in claims:
        documents[claim.document_id] = ConflictDocument(id=claim.document_id, title=claim.document_title)
    return list(documents.values())


def to_conflict_detection_response(dto: ConflictDetectionResult) -> ConflictDetectionResponse:
    return ConflictDetectionResponse(
        collection_id=dto.collection_id,
        analyzed_document_count=dto.analyzed_document_count,
        conflicts=[to_conflict_finding_response(conflict) for conflict in dto.conflicts],
    )


def to_conflict_finding_response(dto: ConflictFinding) -> ConflictFindingResponse:
    return ConflictFindingResponse(
        subject=dto.subject,
        summary=dto.summary,
        documents=[to_conflict_document_response(document) for document in dto.documents],
        evidence=dto.evidence,
        score=dto.score,
    )


def to_conflict_document_response(dto: ConflictDocument) -> ConflictDocumentResponse:
    return ConflictDocumentResponse(id=dto.id, title=dto.title)


conflicts = ConflictService()
