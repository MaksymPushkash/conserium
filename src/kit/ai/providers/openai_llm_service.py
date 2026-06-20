from collections.abc import AsyncIterator
from typing import Any, cast

from openai import AsyncOpenAI

from src.kit.ports.ai.llm_service import ILLMService, IStreamingLLMService
from src.observability.metrics_registry import metrics_registry
from src.query.schemas import RefragChunk, RefragContextPackage
from src.settings import settings


class OpenAILLMService(ILLMService, IStreamingLLMService):
    def __init__(self) -> None:
        self._client: AsyncOpenAI | None = None
        self._model = settings.OPENAI_LLM_MODEL

    async def synthesize_answer(self, *, query: str, context: RefragContextPackage) -> str:
        if not settings.OPENAI_API_KEY:
            return _fallback_answer(context)
        if self._client is None:
            self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=_build_messages(query=query, context=context),
                temperature=0.2,
            )
        except Exception:
            metrics_registry.inc_counter(
                "conserium_openai_requests_total",
                "OpenAI API requests grouped by operation and outcome.",
                labels={"operation": "chat", "status": "error"},
            )
            raise
        metrics_registry.inc_counter(
            "conserium_openai_requests_total",
            "OpenAI API requests grouped by operation and outcome.",
            labels={"operation": "chat", "status": "success"},
        )
        metrics_registry.inc_counter(
            "conserium_openai_estimated_cost_usd",
            "Approximate OpenAI API cost estimate in USD.",
            value=_estimate_chat_cost(query=query, context=context),
        )
        return response.choices[0].message.content or _fallback_answer(context)

    async def stream_answer(self, *, query: str, context: RefragContextPackage) -> AsyncIterator[str]:
        if not settings.OPENAI_API_KEY:
            yield _fallback_answer(context)
            return
        if self._client is None:
            self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        try:
            stream = cast(
                "Any",
                await self._client.chat.completions.create(
                    model=self._model,
                    messages=_build_messages(query=query, context=context),
                    temperature=0.2,
                    stream=True,
                ),
            )
        except Exception:
            metrics_registry.inc_counter(
                "conserium_openai_requests_total",
                "OpenAI API requests grouped by operation and outcome.",
                labels={"operation": "chat_stream", "status": "error"},
            )
            raise
        metrics_registry.inc_counter(
            "conserium_openai_requests_total",
            "OpenAI API requests grouped by operation and outcome.",
            labels={"operation": "chat_stream", "status": "success"},
        )
        metrics_registry.inc_counter(
            "conserium_openai_estimated_cost_usd",
            "Approximate OpenAI API cost estimate in USD.",
            value=_estimate_chat_cost(query=query, context=context),
        )
        async for chunk in stream:
            token = chunk.choices[0].delta.content
            if token:
                yield token


def _build_messages(*, query: str, context: RefragContextPackage) -> list[Any]:
    full_text_context = "\n\n".join(
        _format_context_chunk(index, chunk)
        for index, chunk in enumerate(context.full_text_chunks, start=1)
    )
    compressed_start = len(context.full_text_chunks) + 1
    compressed_context = "\n\n".join(
        _format_context_chunk(index, chunk)
        for index, chunk in enumerate(context.compressed_chunks, start=compressed_start)
    )
    return [
        {
            "role": "system",
            "content": (
                "Answer using only the provided REFRAG context. Full-text chunks are highest priority. "
                "Compressed chunks are lossy summaries for broader context. Include inline citations like [1], [2]. "
                "If the context is insufficient, say so briefly. Do not cite discarded chunks."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Question: {query}\n\n"
                f"REFRAG strategy: {context.compression_strategy}\n"
                f"Original tokens: {context.total_original_tokens}; "
                f"context tokens: {context.total_context_tokens}\n\n"
                f"Full-text context:\n{full_text_context or 'None'}\n\n"
                f"Compressed context:\n{compressed_context or 'None'}"
            ),
        },
    ]


def _format_context_chunk(index: int, chunk: RefragChunk) -> str:
    page = f", page {chunk.page_number}" if chunk.page_number is not None else ""
    title = chunk.document_title or str(chunk.document_id)
    return f"[{index}] {title}{page} ({chunk.representation.value}, score={chunk.score})\n{chunk.context_text}"


def _fallback_answer(context: RefragContextPackage) -> str:
    selected_chunks = context.selected_chunks
    if not selected_chunks:
        return "I could not find relevant saved context yet."
    citations = ", ".join(f"[{index}]" for index in range(1, len(selected_chunks) + 1))
    return (
        f"Found relevant saved context in sources {citations}. "
        "LLM synthesis is disabled until OPENAI_API_KEY is set."
    )


def _estimate_chat_cost(*, query: str, context: RefragContextPackage) -> float:
    estimated_input_tokens = len(query.split()) + context.total_context_tokens
    estimated_output_tokens = 500
    return (estimated_input_tokens / 1_000_000 * 0.15) + (estimated_output_tokens / 1_000_000 * 0.60)
