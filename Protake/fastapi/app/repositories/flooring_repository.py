from sqlalchemy import select

from app.models.flooring import FlooringClassification, FlooringItem, FlooringTakeoff
from app.repositories.base import BaseRepository


class FlooringTakeoffRepository(BaseRepository[FlooringTakeoff]):
    model = FlooringTakeoff


class FlooringItemRepository(BaseRepository[FlooringItem]):
    model = FlooringItem


class FlooringClassificationRepository(BaseRepository[FlooringClassification]):
    model = FlooringClassification

    def for_rooms(self, room_ids: list[int]) -> dict[int, FlooringClassification]:
        if not room_ids:
            return {}
        stmt = select(FlooringClassification).where(FlooringClassification.room_id.in_(room_ids))
        return {c.room_id: c for c in self.db.execute(stmt).scalars().all()}
