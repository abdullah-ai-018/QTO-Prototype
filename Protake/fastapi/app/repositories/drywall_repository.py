from sqlalchemy import select

from app.models.drywall import DrywallClassification, DrywallItem, DrywallTakeoff
from app.repositories.base import BaseRepository


class DrywallTakeoffRepository(BaseRepository[DrywallTakeoff]):
    model = DrywallTakeoff


class DrywallItemRepository(BaseRepository[DrywallItem]):
    model = DrywallItem


class DrywallClassificationRepository(BaseRepository[DrywallClassification]):
    model = DrywallClassification

    def for_walls(self, wall_ids: list[int]) -> dict[int, DrywallClassification]:
        if not wall_ids:
            return {}
        stmt = select(DrywallClassification).where(DrywallClassification.wall_id.in_(wall_ids))
        return {c.wall_id: c for c in self.db.execute(stmt).scalars().all()}
