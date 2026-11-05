from sqlalchemy import select

from app.models.enums import DetectionKind, ReviewStatus
from app.models.schedule_item import ScheduleItem
from app.repositories.base import BaseRepository


class ScheduleItemRepository(BaseRepository[ScheduleItem]):
    model = ScheduleItem

    def for_page(self, page_id: int):
        return select(ScheduleItem).where(ScheduleItem.page_id == page_id)

    def approved_quantity_for_pages(self, page_ids: list[int], schedule_type: DetectionKind) -> int:
        if not page_ids:
            return 0
        stmt = select(ScheduleItem).where(
            ScheduleItem.page_id.in_(page_ids),
            ScheduleItem.status == ReviewStatus.APPROVED,
            ScheduleItem.schedule_type == schedule_type,
        )
        items = list(self.db.execute(stmt).scalars().all())
        return sum(item.quantity for item in items)

    def any_for_pages(self, page_ids: list[int]) -> bool:
        if not page_ids:
            return False
        stmt = select(ScheduleItem.id).where(ScheduleItem.page_id.in_(page_ids)).limit(1)
        return self.db.execute(stmt).scalar() is not None

    def find_by_code_and_pages(self, page_ids: list[int], code: str) -> ScheduleItem | None:
        if not page_ids or not code:
            return None
        stmt = select(ScheduleItem).where(ScheduleItem.page_id.in_(page_ids))
        items = self.db.execute(stmt).scalars().all()
        target = code.upper().replace("-", "").replace(" ", "")
        for item in items:
            item_code_clean = (item.item_code or "").upper().replace("-", "").replace(" ", "")
            if item_code_clean == target:
                return item
        return None
