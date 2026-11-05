from app.models.enums import DetectionSource, ReviewStatus, RoofFeature, WallType
from app.schemas.common import ORMModel, Point


class WallRead(ORMModel):
    id: int
    page_id: int
    room_id: int | None
    start_norm: Point
    end_norm: Point
    length_ft: float
    height_ft: float
    thickness_ft: float
    thickness_measured: bool
    wall_type: WallType
    wall_type_code: str | None
    roof_feature: RoofFeature | None
    confidence: float
    source: DetectionSource
    status: ReviewStatus
    area_sqft: float


class WallUpdate(ORMModel):
    height_ft: float | None = None
    wall_type: WallType | None = None
    wall_type_code: str | None = None
    roof_feature: RoofFeature | None = None
    status: ReviewStatus | None = None
    start_norm: Point | None = None
    end_norm: Point | None = None
    length_ft: float | None = None
    thickness_ft: float | None = None
    thickness_measured: bool | None = None
    room_id: int | None = None


class BatchApplyWallsRequest(ORMModel):
    wall_ids: list[str]
    wall_tag: str
    height_ft: float
    sides_to_hang: float = 2.0
    assembly_description: str | None = None


class BatchApplyWallsResponse(ORMModel):
    page_id: int
    updated_count: int
    total_linear_ft: float
    total_gross_sf: float
    total_net_sf: float
    assembly_applied: str
    status: str = "success"

