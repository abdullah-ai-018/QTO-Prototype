from app.models.enums import DetectionSource, ReviewStatus
from app.schemas.common import BBox, ORMModel, Point


class RoomRead(ORMModel):
    id: int
    page_id: int
    name: str
    room_type: str | None
    floor_finish: str | None
    wall_finish: str | None
    ceiling_finish: str | None
    polygon_norm: list[list[float]]
    bbox_norm: BBox
    centroid_norm: Point
    area_sqft: float
    perimeter_ft: float
    confidence: float
    source: DetectionSource
    status: ReviewStatus


class RoomUpdate(ORMModel):
    name: str | None = None
    room_type: str | None = None
    floor_finish: str | None = None
    wall_finish: str | None = None
    ceiling_finish: str | None = None
    status: ReviewStatus | None = None
    polygon_norm: list[list[float]] | None = None
    bbox_norm: BBox | None = None
    centroid_norm: Point | None = None
    area_sqft: float | None = None
    perimeter_ft: float | None = None
