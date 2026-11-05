from datetime import datetime

from pydantic import Field

from app.models.enums import DetectionKind, DetectionSource, ReviewStatus, TradeKey
from app.schemas.common import BBox, ORMModel


class DetectionRead(ORMModel):
    id: int
    page_id: int
    kind: DetectionKind
    label: str
    trade: TradeKey | None
    polygon_norm: list[list[float]]
    bbox_norm: BBox
    confidence: float
    source: DetectionSource
    status: ReviewStatus
    linked_room_id: int | None
    linked_wall_id: int | None
    reviewed_by_id: int | None
    reviewed_at: datetime | None


class DetectionReviewRequest(ORMModel):
    reason: str | None = None


class BulkReviewRequest(ORMModel):
    detection_ids: list[int] = Field(min_length=1)
    reason: str | None = None


class BulkReviewResponse(ORMModel):
    updated: int
    detection_ids: list[int]


class DetectionUpdate(ORMModel):
    label: str | None = None
    trade: TradeKey | None = None
    status: ReviewStatus | None = None
    polygon_norm: list[list[float]] | None = None
    bbox_norm: BBox | None = None
    confidence: float | None = None
