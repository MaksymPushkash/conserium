from src.application.dtos.draft_dtos import DraftGenerateDTO, DraftResultDTO
from src.application.dtos.query_dtos import QueryDTO
from src.application.use_cases.query.query_use_case import QueryUseCase
from src.domain.exceptions import QueryValidationException


class GenerateDraftUseCase:
    def __init__(self, query_use_case: QueryUseCase) -> None:
        self._query_use_case = query_use_case

    async def __call__(self, dto: DraftGenerateDTO) -> DraftResultDTO:
        prompt = dto.prompt.strip()
        if not prompt:
            raise QueryValidationException("draft prompt cannot be empty")

        result = await self._query_use_case(
            QueryDTO(
                user_id=dto.user_id,
                query=draft_query(prompt),
                collection_id=dto.collection_id,
                tag_names=dto.tag_names,
                document_types=dto.document_types,
                limit=dto.limit,
            )
        )
        return DraftResultDTO(
            prompt=prompt,
            markdown=result.answer,
            sources=[source for source in result.sources if source.used_in_answer],
            gaps=draft_gaps(result.answer),
        )


def draft_query(prompt: str) -> str:
    return (
        "Write a Markdown draft using only my saved Cortex materials.\n"
        f"Draft request: {prompt}\n"
        "Requirements:\n"
        "- Use only retrieved saved context.\n"
        "- Include inline citations like [1], [2] for factual claims.\n"
        "- If the saved context is insufficient, say what is missing instead of inventing.\n"
        "- Return only the draft body."
    )


def draft_gaps(markdown: str) -> list[str]:
    normalized = markdown.casefold()
    if "does not contain enough relevant information" in normalized or "could not find relevant saved context" in normalized:
        return ["Saved context is insufficient for this draft."]
    return []
