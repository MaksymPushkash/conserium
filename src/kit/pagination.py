from collections.abc import Sequence
from typing import TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationParams(BaseModel):
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class ListResource[T](BaseModel):
    items: Sequence[T]
    total: int
    limit: int
    offset: int

    @classmethod
    def from_results(cls, items: Sequence[T], total: int, pagination: PaginationParams) -> "ListResource[T]":
        return cls(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


__all__ = ["ListResource", "PaginationParams"]
