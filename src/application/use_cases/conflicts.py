from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import uuid4

from src.application.dtos.conflict_dtos import (
    ConflictClaimRecordDTO,
    ConflictDetectionDTO,
    ConflictDetectionResultDTO,
    ConflictDocumentDTO,
    ConflictFindingDTO,
    PersistedConflictRecordDTO,
)
from src.application.dtos.refrag_dtos import RefragChunk, RefragContextPackage, RefragRepresentation
from src.application.use_cases.documents.base import ensure_collection_owner
from src.domain.value_objects.document_status import DocumentStatus

if TYPE_CHECKING:
    from collections.abc import Iterable
    from uuid import UUID

    from src.application.ports.ai.llm_service import ILLMService
    from src.application.ports.persistence.unit_of_work import IUnitOfWork
    from src.domain.entities.document_entity import DocumentEntity


class DetectConflictsUseCase:
    def __init__(self, uow: IUnitOfWork, llm_service: ILLMService | None = None) -> None:
        self._uow = uow
        self._llm_service = llm_service

    async def __call__(self, dto: ConflictDetectionDTO) -> ConflictDetectionResultDTO:
        documents = await self._load_documents(dto)
        claims = extract_conflict_claims(documents)
        conflicts = detect_conflicts(claims)
        conflicts = await self._validate_conflicts(conflicts)
        await self._persist_results(dto, documents, claims, conflicts)
        return ConflictDetectionResultDTO(
            collection_id=dto.collection_id,
            analyzed_document_count=len(documents),
            conflicts=conflicts,
        )

    async def _load_documents(self, dto: ConflictDetectionDTO) -> list[DocumentEntity]:
        async with self._uow:
            await ensure_collection_owner(self._uow, dto.collection_id, dto.user_id)
            return await self._uow.document_repo.get_by_user_id(
                dto.user_id,
                limit=dto.limit,
                collection_id=dto.collection_id,
                status=DocumentStatus.READY,
            )

    async def _persist_results(
        self,
        dto: ConflictDetectionDTO,
        documents: list[DocumentEntity],
        claims: list[ConflictClaim],
        conflicts: list[ConflictFindingDTO],
    ) -> None:
        async with self._uow:
            await self._uow.conflict_repo.replace_claims_for_documents(
                user_id=dto.user_id,
                document_ids=[document.id for document in documents],
                claims=[claim.to_record() for claim in claims],
            )
            await self._uow.conflict_repo.replace_conflicts(
                user_id=dto.user_id,
                collection_id=dto.collection_id,
                conflicts=[persisted_conflict(conflict) for conflict in conflicts],
            )
            await self._uow.commit()

    async def _validate_conflicts(self, conflicts: list[ConflictFindingDTO]) -> list[ConflictFindingDTO]:
        if self._llm_service is None:
            return conflicts
        validated: list[ConflictFindingDTO] = []
        for conflict in conflicts:
            answer = await self._llm_service.synthesize_answer(
                query=conflict_validation_prompt(conflict),
                context=conflict_context(conflict),
            )
            if not answer.strip().casefold().startswith("rejected"):
                validated.append(conflict)
        return validated


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

    def to_record(self) -> ConflictClaimRecordDTO:
        return ConflictClaimRecordDTO(
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


def extract_conflict_claims(documents: list[DocumentEntity]) -> list[ConflictClaim]:
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


def detect_conflicts(claims: list[ConflictClaim]) -> list[ConflictFindingDTO]:
    findings: list[ConflictFindingDTO] = []
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
            ConflictFindingDTO(
                subject=subject,
                summary=f"Saved materials contain opposing guidance about {subject.lower()}.",
                documents=documents,
                evidence=[claim.evidence for claim in [*positives[:2], *negatives[:2]]],
                score=min(1.0, 0.5 + (len(documents) * 0.1)),
            )
        )
    return findings


def document_sentences(document: DocumentEntity) -> list[str]:
    text = "\n".join(part for part in (document.title, document.summary, document.raw_content) if part)
    return [sentence.strip() for sentence in _SENTENCE_PATTERN.split(text) if len(sentence.strip()) >= 12]


def _unique_claims(claims: Iterable[ConflictClaim]) -> list[ConflictClaim]:
    unique: dict[tuple[UUID, str], ConflictClaim] = {}
    for claim in claims:
        unique[(claim.document_id, claim.evidence)] = claim
    return list(unique.values())


def _conflict_documents(claims: list[ConflictClaim]) -> list[ConflictDocumentDTO]:
    documents: dict[UUID, ConflictDocumentDTO] = {}
    for claim in claims:
        documents[claim.document_id] = ConflictDocumentDTO(id=claim.document_id, title=claim.document_title)
    return list(documents.values())


def persisted_conflict(conflict: ConflictFindingDTO) -> PersistedConflictRecordDTO:
    return PersistedConflictRecordDTO(
        subject=conflict.subject,
        summary=conflict.summary,
        document_ids=[document.id for document in conflict.documents],
        evidence=conflict.evidence,
        score=conflict.score,
    )


def conflict_validation_prompt(conflict: ConflictFindingDTO) -> str:
    return (
        "Decide whether the evidence contains a real contradiction. "
        "Reply with CONFIRMED if the sources give opposing guidance, or REJECTED if they do not. "
        f"Subject: {conflict.subject}"
    )


def conflict_context(conflict: ConflictFindingDTO) -> RefragContextPackage:
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
