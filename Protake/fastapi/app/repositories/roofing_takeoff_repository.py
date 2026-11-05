"""Repositories for app.models.roofing_takeoff — named distinctly from
app/repositories/roofing_repository.py if one ever exists for the
geometry-derived roof_* tables, to keep the two table families separate.
"""

from sqlalchemy import select

from app.models.roofing_takeoff import RoofingClassification, RoofingItem, RoofingTakeoff
from app.repositories.base import BaseRepository


class RoofingTakeoffRepository(BaseRepository[RoofingTakeoff]):
    model = RoofingTakeoff


class RoofingItemRepository(BaseRepository[RoofingItem]):
    model = RoofingItem


class RoofingClassificationRepository(BaseRepository[RoofingClassification]):
    model = RoofingClassification

    def for_walls(self, wall_ids: list[int]) -> dict[int, RoofingClassification]:
        if not wall_ids:
            return {}
        stmt = select(RoofingClassification).where(RoofingClassification.wall_id.in_(wall_ids))
        return {c.wall_id: c for c in self.db.execute(stmt).scalars().all()}
