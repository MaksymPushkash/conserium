import uuid
from datetime import UTC, datetime

from src.documents.status import DocumentStatus
from src.documents.types import DocumentType
from src.models.document import DocumentModel
from src.review.helpers import build_quiz_questions_for_document, score_quiz_answers


def test_build_quiz_questions_uses_summary_and_suggested_question() -> None:
    document = _document(suggested_questions=["What is asyncio?"], summary="Asyncio runs cooperative I/O.")

    questions = build_quiz_questions_for_document(document, [], remaining=2)

    assert questions[0]["question"] == "What is asyncio?"
    assert questions[0]["correct_option_id"] == "0"
    assert questions[0]["weak_area"] == "python"
    assert questions[0]["source_document_id"] == str(document.id)


def test_score_quiz_answers_records_weak_areas_for_misses() -> None:
    questions: list[dict[str, object]] = [
        {
            "id": "q1",
            "correct_option_id": "0",
            "weak_area": "asyncio",
        }
    ]

    score, total, answers, weak_areas = score_quiz_answers(questions, [{"question_id": "q1", "option_id": "1"}])

    assert score == 0
    assert total == 1
    assert answers[0]["correct"] is False
    assert weak_areas == ["asyncio"]


def _document(*, suggested_questions: list[str], summary: str | None) -> DocumentModel:
    return DocumentModel(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        collection_id=None,
        title="Asyncio notes",
        type=DocumentType.TEXT,
        status=DocumentStatus.READY,
        source_url=None,
        file_path=None,
        file_size_bytes=None,
        raw_content="Asyncio content",
        summary=summary,
        word_count=20,
        language="en",
        doc_embedding=None,
        is_duplicate=False,
        duplicate_of_id=None,
        created_at=datetime.now(UTC),
        updated_at=None,
        suggested_questions=suggested_questions,
        tags=["python"],
    )
