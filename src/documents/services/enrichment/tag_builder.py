from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.documents.schemas import CategoryMetadata, EntityMetadata


def build_auto_tags(
    entities: list[EntityMetadata],
    categories: list[CategoryMetadata],
) -> list[str]:
    entity_tags: list[str] = []
    for entity in entities:
        entity_text = str(entity.get("text", "")).strip().lower()
        if 2 <= len(entity_text) <= 40:
            entity_tags.append(entity_text)

    category_tags = [
        str(category.get("label", "")).strip().lower()
        for category in categories
        if float(category.get("score", 0.0)) >= 0.5 and str(category.get("label", "")).strip()
    ]

    return list(dict.fromkeys([*category_tags[:3], *entity_tags[:5]]))
