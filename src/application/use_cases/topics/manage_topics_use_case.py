from uuid import UUID

from src.application.dtos.topic_dtos import TopicDTO
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.topics.topic_mapping import topic_to_dto
from src.domain.exceptions import ValidationException


class RenameTopicUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: UUID, name: str, display_name: str) -> TopicDTO:
        source_name = clean_topic_name(name)
        normalized_display_name = clean_topic_name(display_name)
        if not source_name or not normalized_display_name:
            raise ValidationException("topic name cannot be empty")
        async with self._uow:
            record = await self._uow.topic_repo.rename_topic(
                user_id=user_id,
                source_name=source_name,
                display_name=normalized_display_name,
            )
            await self._uow.commit()
        return topic_to_dto(record)


class MergeTopicsUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: UUID, name: str, source_names: list[str]) -> TopicDTO:
        display_name = clean_topic_name(name)
        normalized_sources = unique_topic_names([*source_names, name])
        if not display_name or len(normalized_sources) < 2:
            raise ValidationException("at least two topics are required to merge")
        async with self._uow:
            record = await self._uow.topic_repo.merge_topics(
                user_id=user_id,
                source_names=normalized_sources,
                display_name=display_name,
            )
            await self._uow.commit()
        return topic_to_dto(record)


class PinTopicUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: UUID, name: str, pinned: bool = True) -> TopicDTO:
        topic_name = clean_topic_name(name)
        if not topic_name:
            raise ValidationException("topic name cannot be empty")
        async with self._uow:
            record = await self._uow.topic_repo.set_pinned(user_id=user_id, name=topic_name, pinned=pinned)
            await self._uow.commit()
        return topic_to_dto(record)


class IgnoreTopicUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: UUID, name: str, ignored: bool = True) -> TopicDTO:
        topic_name = clean_topic_name(name)
        if not topic_name:
            raise ValidationException("topic name cannot be empty")
        async with self._uow:
            record = await self._uow.topic_repo.set_ignored(user_id=user_id, name=topic_name, ignored=ignored)
            await self._uow.commit()
        return topic_to_dto(record)


def clean_topic_name(value: str) -> str:
    return " ".join(value.strip().split())[:100]


def unique_topic_names(values: list[str]) -> list[str]:
    names: dict[str, str] = {}
    for value in values:
        name = clean_topic_name(value)
        if name:
            names.setdefault(name.casefold(), name)
    return list(names.values())
