from sqlalchemy import select

from app.models.detection import Detection
from app.models.enums import DetectionKind, ReviewStatus
from app.repositories.base import BaseRepository


class DetectionRepository(BaseRepository[Detection]):
    model = Detection

    def for_page(self, page_id: int, status: ReviewStatus | None = None):
        stmt = select(Detection).where(Detection.page_id == page_id)
        if status is not None:
            stmt = stmt.where(Detection.status == status)
        return stmt

    def pending_for_page(self, page_id: int) -> list[Detection]:
        stmt = self.for_page(page_id, status=ReviewStatus.PENDING)
        return list(self.db.execute(stmt).scalars().all())

    def approved_count_by_kind(self, page_ids: list[int], kind: DetectionKind) -> int:
        if not page_ids:
            return 0
        stmt = select(Detection).where(
            Detection.page_id.in_(page_ids),
            Detection.status == ReviewStatus.APPROVED,
            Detection.kind == kind,
        )
        return len(list(self.db.execute(stmt).scalars().all()))

    def candidate_count_by_kind(self, page_ids: list[int], kind: DetectionKind) -> int:
        if not page_ids:
            return 0
        stmt = select(Detection).where(
            Detection.page_id.in_(page_ids),
            Detection.status != ReviewStatus.REJECTED,
            Detection.kind == kind,
        )
        return len(list(self.db.execute(stmt).scalars().all()))

    def approved_for_pages(self, page_ids: list[int]) -> list[Detection]:
        if not page_ids:
            return []
        stmt = select(Detection).where(
            Detection.page_id.in_(page_ids),
            Detection.status == ReviewStatus.APPROVED,
        )
        return list(self.db.execute(stmt).scalars().all())

    def candidate_for_pages(self, page_ids: list[int]) -> list[Detection]:
        if not page_ids:
            return []
        stmt = select(Detection).where(
            Detection.page_id.in_(page_ids),
            Detection.status != ReviewStatus.REJECTED,
        )
        return list(self.db.execute(stmt).scalars().all())

    def clear_for_page(self, page_id: int) -> None:
        self.db.query(Detection).filter(Detection.page_id == page_id).delete()
        self.db.commit()

    def clear_for_pages(self, page_ids: list[int]) -> None:
        if not page_ids:
            return
        self.db.query(Detection).filter(Detection.page_id.in_(page_ids)).delete()
        self.db.commit()
