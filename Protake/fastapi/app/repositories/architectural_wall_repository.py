from sqlalchemy import select

from app.models.architectural_wall import ArchitecturalWallModel
from app.repositories.base import BaseRepository


class ArchitecturalWallRepository(BaseRepository[ArchitecturalWallModel]):
    model = ArchitecturalWallModel

    def for_page(self, page_id: int):
        return select(ArchitecturalWallModel).where(ArchitecturalWallModel.page_id == page_id)

    def for_pages(self, page_ids: list[int]) -> list[ArchitecturalWallModel]:
        if not page_ids:
            return []
        stmt = select(ArchitecturalWallModel).where(ArchitecturalWallModel.page_id.in_(page_ids))
        return list(self.db.execute(stmt).scalars().all())

    def clear_for_page(self, page_id: int) -> None:
        self.db.query(ArchitecturalWallModel).filter(ArchitecturalWallModel.page_id == page_id).delete()
        self.db.commit()

    def clear_for_pages(self, page_ids: list[int]) -> None:
        if not page_ids:
            return
        self.db.query(ArchitecturalWallModel).filter(ArchitecturalWallModel.page_id.in_(page_ids)).delete()
        self.db.commit()
