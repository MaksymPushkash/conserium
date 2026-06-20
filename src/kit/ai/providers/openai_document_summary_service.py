import re
from typing import Any

from openai import AsyncOpenAI

from src.kit.ports.ai.document_summary_service import IDocumentSummaryService
from src.observability.metrics_registry import metrics_registry
from src.settings import settings

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
_MAX_SUMMARY_INPUT_CHARS = 12_000
_MAX_FALLBACK_SENTENCES = 5


class OpenAIDocumentSummaryService(IDocumentSummaryService):
    def __init__(self) -> None:
        self._client: AsyncOpenAI | None = None
        self._model = settings.OPENAI_LLM_MODEL

    async def summarize_document(self, *, title: str, text: str) -> str | None:
        normalized_text = " ".join(text.split())
        if not normalized_text:
            return None
        if not settings.OPENAI_API_KEY:
            return _fallback_summary(normalized_text)
        if self._client is None:
            self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=_summary_messages(title=title, text=normalized_text[:_MAX_SUMMARY_INPUT_CHARS]),
                temperature=0.1,
            )
        except Exception:
            metrics_registry.inc_counter(
                "conserium_openai_requests_total",
                "OpenAI API requests grouped by operation and outcome.",
                labels={"operation": "document_summary", "status": "error"},
            )
            raise

        metrics_registry.inc_counter(
            "conserium_openai_requests_total",
            "OpenAI API requests grouped by operation and outcome.",
            labels={"operation": "document_summary", "status": "success"},
        )
        metrics_registry.inc_counter(
            "conserium_openai_estimated_cost_usd",
            "Approximate OpenAI API cost estimate in USD.",
            value=_estimate_summary_cost(normalized_text),
        )
        summary = response.choices[0].message.content
        return summary.strip() if summary and summary.strip() else _fallback_summary(normalized_text)


def _summary_messages(*, title: str, text: str) -> list[Any]:
    return [
        {
            "role": "system",
            "content": (
                "Summarize the provided saved document in 3 to 5 concise sentences. "
                "Use only the provided document text. Do not add outside knowledge."
            ),
        },
        {
            "role": "user",
            "content": f"Title: {title}\n\nDocument text:\n{text}",
        },
    ]


def _fallback_summary(text: str) -> str:
    sentences = [sentence.strip() for sentence in _SENTENCE_RE.split(text) if sentence.strip()]
    if not sentences:
        words = text.split()
        return " ".join(words[:90])
    return " ".join(sentences[:_MAX_FALLBACK_SENTENCES])


def _estimate_summary_cost(text: str) -> float:
    estimated_input_tokens = min(len(text.split()), 3_000)
    estimated_output_tokens = 140
    return (estimated_input_tokens / 1_000_000 * 0.15) + (estimated_output_tokens / 1_000_000 * 0.60)
