import json

from src.application.dtos.query_stream_dtos import QueryStreamEventDTO


def format_sse_event(dto: QueryStreamEventDTO) -> str:
    payload = json.dumps(dto.data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {dto.event.value}\ndata: {payload}\n\n"
