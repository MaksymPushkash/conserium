from src.application.services.enrichment.suggested_questions import build_suggested_questions


def test_build_suggested_questions_uses_title_tags_and_categories() -> None:
    questions = build_suggested_questions(
        title="Cloud Glossary",
        text=" ".join(["cloud"] * 200),
        tags=["api", "vendor lock-in"],
        categories=[{"label": "cloud computing", "score": 0.9}],
    )

    assert questions == [
        "Summarize Cloud Glossary.",
        "What are the key points in Cloud Glossary?",
        "What does api mean in Cloud Glossary?",
        "What does vendor lock-in mean in Cloud Glossary?",
        "What does Cloud Glossary say about cloud computing?",
    ]


def test_build_suggested_questions_deduplicates_and_limits_results() -> None:
    questions = build_suggested_questions(
        title="API",
        text="short",
        tags=["api", "api"],
        categories=[{"label": "api", "score": 0.9}, {"label": "backend", "score": 0.8}],
    )

    assert len(questions) <= 5
    assert len(questions) == len(set(questions))
