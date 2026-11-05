from sqlalchemy import select

from app.models.enums import ReviewStatus
from app.models.wall import Wall
from app.repositories.base import BaseRepository


class WallRepository(BaseRepository[Wall]):
    model = Wall

    def for_page(self, page_id: int):
        return select(Wall).where(Wall.page_id == page_id)

    def approved_for_pages(self, page_ids: list[int]) -> list[Wall]:
        if not page_ids:
            return []
        stmt = select(Wall).where(Wall.page_id.in_(page_ids), Wall.status == ReviewStatus.APPROVED)
        return list(self.db.execute(stmt).scalars().all())

    def candidate_for_pages(self, page_ids: list[int]) -> list[Wall]:
        if not page_ids:
            return []
        stmt = select(Wall).where(Wall.page_id.in_(page_ids), Wall.status != ReviewStatus.REJECTED)
        return list(self.db.execute(stmt).scalars().all())

    def clear_for_page(self, page_id: int) -> None:
        self.db.query(Wall).filter(Wall.page_id == page_id).delete()
        self.db.commit()

    def clear_for_pages(self, page_ids: list[int]) -> None:
        if not page_ids:
            return
        self.db.query(Wall).filter(Wall.page_id.in_(page_ids)).delete()
        self.db.commit()
