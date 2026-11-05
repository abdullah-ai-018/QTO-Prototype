from sqlalchemy import select

from app.models.painting import PaintingClassification, PaintingItem, PaintingTakeoff
from app.repositories.base import BaseRepository


class PaintingTakeoffRepository(BaseRepository[PaintingTakeoff]):
    model = PaintingTakeoff


class PaintingItemRepository(BaseRepository[PaintingItem]):
    model = PaintingItem


class PaintingClassificationRepository(BaseRepository[PaintingClassification]):
    model = PaintingClassification

    def for_walls(self, wall_ids: list[int]) -> dict[int, PaintingClassification]:
        if not wall_ids:
            return {}
        stmt = select(PaintingClassification).where(PaintingClassification.wall_id.in_(wall_ids))
        return {c.wall_id: c for c in self.db.execute(stmt).scalars().all()}
