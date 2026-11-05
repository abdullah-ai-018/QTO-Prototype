from sqlalchemy import select

from app.models.estimate import Estimate
from app.repositories.base import BaseRepository


class EstimateRepository(BaseRepository[Estimate]):
    model = Estimate

    def for_project(self, project_id: int):
        return select(Estimate).where(Estimate.project_id == project_id).order_by(Estimate.created_at.desc())

    def latest_for_project(self, project_id: int) -> Estimate | None:
        stmt = self.for_project(project_id).limit(1)
        return self.db.execute(stmt).scalars().first()
