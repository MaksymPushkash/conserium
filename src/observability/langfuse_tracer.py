from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import httpx

from src.kit.ports.observability.query_trace import IQueryTracer
from src.settings import settings

if TYPE_CHECKING:
    from src.query.agents.state import ConseriumQueryState


class LangfuseQueryTracer(IQueryTracer):
    async def trace_query(self, state: ConseriumQueryState) -> str | None:
        trace_id = uuid.uuid4().hex
        if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
            return trace_id

        payload = {
            "batch": [
                {
                    "id": trace_id,
                    "type": "trace-create",
                    "timestamp": None,
                    "body": {
                        "id": trace_id,
                        "name": "conserium.query",
                        "userId": str(state.user_id),
                        "input": state.query,
                        "output": state.answer,
                        "metadata": {
                            "query_type": state.query_type.value,
                            "source_count": len(state.sources),
                            "eval_scores": state.eval_scores,
                            "conversation_id": str(state.conversation_id),
                        },
                    },
                }
            ]
        }
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                f"{settings.LANGFUSE_HOST.rstrip('/')}/api/public/ingestion",
                json=payload,
                auth=(settings.LANGFUSE_PUBLIC_KEY, settings.LANGFUSE_SECRET_KEY),
            )
        return trace_id
