from src.query.schemas import QueryStreamEvent, QueryStreamEventType
from src.query.service import format_sse_event


def test_format_sse_event_serializes_structured_event() -> None:
    event = QueryStreamEvent(
        event=QueryStreamEventType.TOKEN,
        data={"text": "hello"},
    )

    assert format_sse_event(event) == 'event: token\ndata: {"text":"hello"}\n\n'
