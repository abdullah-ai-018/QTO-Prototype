"""Generic pagination, filtering, and sorting helpers used across every
list endpoint in the API.
"""

from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import Select, asc, desc, func, select
from sqlalchemy.orm import Session

T = TypeVar("T")


class PageParams(BaseModel):
    page: int = 1
    page_size: int = 20
    sort_by: str | None = None
    sort_dir: str = "asc"

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def page_params(
    page: int = Query(1, ge=1, description="1-indexed page number"),
    page_size: int = Query(20, ge=1, le=200, description="Items per page"),
    sort_by: str | None = Query(None, description="Column name to sort by"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
) -> PageParams:
    return PageParams(page=page, page_size=page_size, sort_by=sort_by, sort_dir=sort_dir)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int


def paginate(
    db: Session,
    stmt: Select,
    params: PageParams,
    model,
    schema_cls: type[BaseModel],
) -> Page:
    """Apply optional sorting + offset/limit to `stmt`, execute it, and
    wrap the results (serialized via `schema_cls`) in a `Page` envelope.
    """
    if params.sort_by and hasattr(model, params.sort_by):
        column = getattr(model, params.sort_by)
        stmt = stmt.order_by(asc(column) if params.sort_dir == "asc" else desc(column))

    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = db.execute(count_stmt).scalar_one()
    rows = db.execute(stmt.offset(params.offset).limit(params.page_size)).scalars().all()

    total_pages = max(1, (total + params.page_size - 1) // params.page_size)
    return Page(
        items=[schema_cls.model_validate(row) for row in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=total_pages,
    )
