from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.documents.schemas import CategoryMetadata


def build_suggested_questions(
    *,
    title: str,
    text: str,
    tags: list[str],
    categories: list[CategoryMetadata],
) -> list[str]:
    clean_title = title.strip() or "this document"
    questions = [
        f"Summarize {clean_title}.",
        f"What are the key points in {clean_title}?",
    ]

    for tag in tags[:2]:
        questions.append(f"What does {tag} mean in {clean_title}?")

    for category in categories:
        label = str(category.get("label", "")).strip()
        if label:
            questions.append(f"What does {clean_title} say about {label}?")
        if len(questions) >= 5:
            break

    if len(text.split()) > 150:
        questions.append(f"What should I remember from {clean_title}?")

    return list(dict.fromkeys(questions))[:5]
