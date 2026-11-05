from datetime import datetime

from app.models.enums import DetectionKind, ReviewStatus
from app.schemas.common import ORMModel


class ScheduleItemRead(ORMModel):
    id: int
    page_id: int
    schedule_type: DetectionKind
    item_code: str
    quantity: int
    attributes: dict
    confidence: float
    status: ReviewStatus
    created_at: datetime


class ScheduleItemReviewRequest(ORMModel):
    reason: str | None = None
