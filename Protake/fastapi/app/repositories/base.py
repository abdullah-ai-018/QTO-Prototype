"""Generic repository implementing the Repository Pattern over any
SQLAlchemy model. Entity-specific repositories subclass this and add
domain queries only where the generic CRUD surface isn't enough.
"""

from typing import Any, Generic, TypeVar

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.database import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, db: Session):
        self.db = db

    def get(self, id_: int) -> ModelT | None:
        return self.db.get(self.model, id_)

    def get_or_404(self, id_: int) -> ModelT:
        instance = self.get(id_)
        if instance is None:
            from fastapi import HTTPException, status

            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{self.model.__name__} {id_} not found")
        return instance

    def list_all(self) -> list[ModelT]:
        return list(self.db.execute(select(self.model)).scalars().all())

    def query(self, **filters: Any) -> Select:
        stmt = select(self.model)
        for key, value in filters.items():
            if value is not None:
                stmt = stmt.where(getattr(self.model, key) == value)
        return stmt

    def find(self, **filters: Any) -> list[ModelT]:
        return list(self.db.execute(self.query(**filters)).scalars().all())

    def find_one(self, **filters: Any) -> ModelT | None:
        return self.db.execute(self.query(**filters)).scalars().first()

    def create(self, **fields: Any) -> ModelT:
        instance = self.model(**fields)
        self.db.add(instance)
        self.db.flush()
        self.db.refresh(instance)
        return instance

    def update(self, instance: ModelT, **fields: Any) -> ModelT:
        for key, value in fields.items():
            if value is not None:
                setattr(instance, key, value)
        self.db.add(instance)
        self.db.flush()
        self.db.refresh(instance)
        return instance

    def delete(self, instance: ModelT) -> None:
        self.db.delete(instance)
        self.db.flush()
