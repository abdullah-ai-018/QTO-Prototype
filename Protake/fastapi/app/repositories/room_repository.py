from sqlalchemy import select

from app.models.enums import ReviewStatus
from app.models.room import Room
from app.repositories.base import BaseRepository


class RoomRepository(BaseRepository[Room]):
    model = Room

    def for_page(self, page_id: int):
        return select(Room).where(Room.page_id == page_id)

    def approved_for_pages(self, page_ids: list[int]) -> list[Room]:
        if not page_ids:
            return []
        stmt = select(Room).where(Room.page_id.in_(page_ids), Room.status == ReviewStatus.APPROVED)
        return list(self.db.execute(stmt).scalars().all())

    def candidate_for_pages(self, page_ids: list[int]) -> list[Room]:
        if not page_ids:
            return []
        stmt = select(Room).where(Room.page_id.in_(page_ids), Room.status != ReviewStatus.REJECTED)
        return list(self.db.execute(stmt).scalars().all())

    def clear_for_page(self, page_id: int) -> None:
        self.db.query(Room).filter(Room.page_id == page_id).delete()
        self.db.commit()

    def clear_for_pages(self, page_ids: list[int]) -> None:
        if not page_ids:
            return
        self.db.query(Room).filter(Room.page_id.in_(page_ids)).delete()
        self.db.commit()
