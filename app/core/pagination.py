from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query


@dataclass(frozen=True)
class PaginationParams:
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    def total_pages(self, total: int) -> int:
        return (total + self.page_size - 1) // self.page_size


def get_pagination(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginationParams:
    return PaginationParams(
        page=page,
        page_size=page_size,
    )


Pagination = Annotated[
    PaginationParams,
    Depends(get_pagination),
]
