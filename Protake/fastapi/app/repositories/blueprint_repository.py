from sqlalchemy import select

from app.models.blueprint import Blueprint
from app.repositories.base import BaseRepository


class BlueprintRepository(BaseRepository[Blueprint]):
    model = Blueprint

    def for_project(self, project_id: int):
        return select(Blueprint).where(Blueprint.project_id == project_id)
