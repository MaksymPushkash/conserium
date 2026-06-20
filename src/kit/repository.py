from collections.abc import Sequence
from typing import Any, ClassVar, Self, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

ModelT = TypeVar("ModelT")


class RepositoryBase[ModelT]:
    model: ClassVar[type[Any]]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @classmethod
    def from_session(cls, session: AsyncSession) -> Self:
        return cls(session)

    def get_base_statement(self) -> Select[tuple[ModelT]]:
        return select(self.model)

    async def get_one(self, statement: Select[tuple[ModelT]]) -> ModelT:
        result = await self.session.execute(statement)
        return result.scalar_one()

    async def get_one_or_none(self, statement: Select[tuple[ModelT]]) -> ModelT | None:
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_all(self, statement: Select[tuple[ModelT]]) -> Sequence[ModelT]:
        result = await self.session.execute(statement)
        return result.scalars().all()

    async def paginate(self, statement: Select[tuple[ModelT]], *, limit: int, offset: int) -> tuple[Sequence[ModelT], int]:
        count_statement = select(func.count()).select_from(statement.order_by(None).subquery())
        count_result = await self.session.execute(count_statement)
        total = count_result.scalar_one()

        result = await self.session.execute(statement.limit(limit).offset(offset))
        return result.scalars().all(), total

    async def create(self, obj: ModelT, *, flush: bool = False) -> ModelT:
        self.session.add(obj)
        if flush:
            await self.session.flush()
        return obj

    async def update(self, obj: ModelT, *, flush: bool = False) -> ModelT:
        self.session.add(obj)
        if flush:
            await self.session.flush()
        return obj


__all__ = ["RepositoryBase"]
