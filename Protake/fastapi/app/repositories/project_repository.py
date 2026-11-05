from sqlalchemy import select

from app.models.project import Project
from app.repositories.base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    model = Project

    def for_owner(self, owner_id: int):
        return select(Project).where(Project.owner_id == owner_id)
