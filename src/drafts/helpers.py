from src.drafts.repository import DraftRecord, DraftVersionRecord
from src.drafts.schemas import (
    DraftDetail,
    DraftGenerationPayload,
    DraftListItem,
    DraftTemplate,
    DraftVersion,
)
from src.kit.exceptions import QueryValidationException
from src.query.schemas import QueryPayload, QuerySource

TEMPLATES = {
    "brief": DraftTemplate(
        id="brief",
        name="Brief",
        description="Concise cited summary for quick decision-making.",
        prompt="Write a concise brief with context, key points, risks, and next actions.",
        outline=["Context", "Key points", "Risks", "Next actions"],
    ),
    "prd": DraftTemplate(
        id="prd",
        name="PRD",
        description="Product requirements with problem, goals, scope, and acceptance criteria.",
        prompt="Write a PRD with problem, goals, users, requirements, non-goals, and acceptance criteria.",
        outline=["Problem", "Goals", "Users", "Requirements", "Non-goals", "Acceptance criteria"],
    ),
    "study_guide": DraftTemplate(
        id="study_guide",
        name="Study guide",
        description="Structured learning material with concepts, examples, and checks.",
        prompt="Write a study guide with concepts, explanations, examples, and review questions.",
        outline=["Learning goals", "Core concepts", "Examples", "Common mistakes", "Review questions"],
    ),
    "comparison_memo": DraftTemplate(
        id="comparison_memo",
        name="Comparison memo",
        description="Side-by-side memo focused on tradeoffs and recommendation.",
        prompt="Write a comparison memo covering options, evidence, tradeoffs, risks, and recommendation.",
        outline=["Options", "Evidence", "Tradeoffs", "Risks", "Recommendation"],
    ),
    "implementation_plan": DraftTemplate(
        id="implementation_plan",
        name="Implementation plan",
        description="Ordered engineering plan with phases, risks, and validation.",
        prompt="Write an implementation plan with phases, concrete tasks, risks, and validation.",
        outline=["Objective", "Phases", "Tasks", "Risks", "Validation"],
    ),
}

SCOPE_TYPES = {"all", "documents", "collection", "topic", "knowledge_gap"}


def draft_query_payload(
    dto: DraftGenerationPayload,
    prompt: str,
    *,
    template: DraftTemplate,
    outline: list[str],
    relevance_query: str,
    limit: int,
) -> QueryPayload:
    return QueryPayload(
        user_id=dto.user_id,
        query=draft_query(prompt, template=template, outline=outline, scope=dto),
        retrieval_query=prompt,
        relevance_query=relevance_query,
        collection_id=dto.collection_id,
        tag_names=dto.tag_names,
        document_types=dto.document_types,
        document_ids=dto.document_ids,
        limit=limit,
        retrieval_depth="deep",
    )


def draft_list_item(record: DraftRecord) -> DraftListItem:
    if record.created_at is None:
        raise ValueError("draft created_at is required")
    return DraftListItem(
        id=record.id,
        collection_id=record.collection_id,
        title=record.title,
        prompt=record.prompt,
        template_id=record.template_id,
        scope_type=record.scope_type,
        topic=record.topic,
        knowledge_gap_id=record.knowledge_gap_id,
        version_number=record.version_number,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def draft_detail(record: DraftRecord) -> DraftDetail:
    if record.created_at is None:
        raise ValueError("draft created_at is required")
    return DraftDetail(
        id=record.id,
        collection_id=record.collection_id,
        current_version_id=record.current_version_id,
        title=record.title,
        prompt=record.prompt,
        template_id=record.template_id,
        scope_type=record.scope_type,
        topic=record.topic,
        knowledge_gap_id=record.knowledge_gap_id,
        scope_metadata=record.scope_metadata,
        markdown=record.markdown,
        sources=record.sources,
        gaps=record.gaps,
        version_number=record.version_number,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def draft_version(record: DraftVersionRecord) -> DraftVersion:
    if record.created_at is None:
        raise ValueError("draft version created_at is required")
    return DraftVersion(
        id=record.id,
        draft_id=record.draft_id,
        version_number=record.version_number,
        title=record.title,
        prompt=record.prompt,
        template_id=record.template_id,
        scope_type=record.scope_type,
        collection_id=record.collection_id,
        topic=record.topic,
        knowledge_gap_id=record.knowledge_gap_id,
        markdown=record.markdown,
        sources=record.sources,
        gaps=record.gaps,
        created_at=record.created_at,
    )


def draft_query(prompt: str, *, template: DraftTemplate, outline: list[str], scope: DraftGenerationPayload) -> str:
    outline_text = "\n".join(f"- {section}" for section in outline)
    return (
        "Write a Markdown draft using only my saved Conserium materials.\n"
        f"Template: {template.name}\n"
        f"Template instructions: {template.prompt}\n"
        f"Scope: {scope_description(scope)}\n"
        f"Draft request: {prompt}\n"
        "Outline:\n"
        f"{outline_text}\n"
        "Requirements:\n"
        "- Use only retrieved saved context.\n"
        "- Include inline citations like [1], [2] for factual claims.\n"
        "- If the saved context is insufficient, say what is missing instead of inventing.\n"
        "- Return only the draft body."
    )


def has_sufficient_draft_context(sources: list[QuerySource]) -> bool:
    return any(source.used_in_answer for source in sources)


def normalize_scope(dto: DraftGenerationPayload) -> DraftGenerationPayload:
    scope_type = dto.scope_type.strip().lower() if dto.scope_type else "all"
    if scope_type not in SCOPE_TYPES:
        raise QueryValidationException("unsupported draft scope")
    if dto.document_ids:
        scope_type = "documents"
    elif dto.collection_id is not None and scope_type == "all":
        scope_type = "collection"
    elif dto.topic and scope_type == "all":
        scope_type = "topic"
    elif dto.knowledge_gap_id and scope_type == "all":
        scope_type = "knowledge_gap"

    topic = dto.topic.strip().lower() if dto.topic else None
    tag_names = tuple(tag.strip().lower() for tag in dto.tag_names or () if tag.strip())
    if topic and topic not in tag_names:
        tag_names = (*tag_names, topic)

    if scope_type == "documents" and not dto.document_ids:
        raise QueryValidationException("document scope requires document_ids")
    if scope_type == "collection" and dto.collection_id is None:
        raise QueryValidationException("collection scope requires collection_id")
    if scope_type == "topic" and not topic:
        raise QueryValidationException("topic scope requires topic")
    if scope_type == "knowledge_gap":
        if not dto.knowledge_gap_id:
            raise QueryValidationException("knowledge gap scope requires knowledge_gap_id")
        if not topic:
            raise QueryValidationException("knowledge gap scope requires topic")

    return DraftGenerationPayload(
        user_id=dto.user_id,
        prompt=dto.prompt,
        draft_id=dto.draft_id,
        template_id=dto.template_id,
        scope_type=scope_type,
        collection_id=dto.collection_id,
        document_ids=dto.document_ids,
        topic=topic,
        knowledge_gap_id=dto.knowledge_gap_id,
        outline=dto.outline,
        tag_names=tag_names or None,
        document_types=dto.document_types,
        limit=dto.limit,
    )


def draft_template(template_id: str) -> DraftTemplate:
    template = TEMPLATES.get(template_id.strip().lower())
    if template is None:
        raise QueryValidationException("unsupported draft template")
    return template


def normalize_outline(outline: tuple[str, ...] | None) -> list[str]:
    return [section.strip()[:120] for section in outline or () if section.strip()]


def draft_title(prompt: str, template: DraftTemplate) -> str:
    normalized = " ".join(prompt.split())
    return f"{template.name}: {normalized[:80]}"


def scope_description(dto: DraftGenerationPayload) -> str:
    if dto.scope_type == "documents":
        return f"selected documents only ({len(dto.document_ids or ())} document(s))"
    if dto.scope_type == "collection":
        return f"collection {dto.collection_id}"
    if dto.scope_type == "topic":
        return f"topic {dto.topic}"
    if dto.scope_type == "knowledge_gap":
        return f"knowledge gap {dto.knowledge_gap_id} for topic {dto.topic}"
    return "all saved workspace sources"


def scope_metadata(dto: DraftGenerationPayload) -> dict[str, object]:
    return {
        "scope_type": dto.scope_type,
        "collection_id": str(dto.collection_id) if dto.collection_id else None,
        "document_ids": [str(document_id) for document_id in dto.document_ids or ()],
        "topic": dto.topic,
        "knowledge_gap_id": dto.knowledge_gap_id,
        "tag_names": list(dto.tag_names or ()),
        "document_types": [document_type.value for document_type in dto.document_types or ()],
        "limit": dto.limit,
    }
