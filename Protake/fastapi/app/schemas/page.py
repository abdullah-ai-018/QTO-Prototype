from typing import Literal

from pydantic import Field

from app.schemas.common import ORMModel


class PageRead(ORMModel):
    id: int
    blueprint_id: int
    page_number: int
    sheet_code: str | None
    sheet_name: str | None
    width_px: int
    height_px: int
    dpi: int
    scale_ft_per_px: float | None
    # One of metrics.SCALE_SOURCE_* — "assumed_default" means no calibration
    # was found (user, printed note, or measured dimensions all missing) and
    # geometry ran on the uncalibrated fallback scale. Frontend should flag
    # this for review rather than presenting the page's rooms/walls as if
    # measured normally.
    scale_source: str | None = None
    geometry_processed: bool
    ocr_processed: bool
    ai_validated: bool
    # Page classifier results — frontend uses these to skip non-drawing pages
    page_type: str | None = None
    is_takeoff_eligible: bool = True
    skip_reason: str | None = None
    # Richer classifier fields (see app.models.page.Page) — null when the
    # page never made it through classification.
    discipline: str | None = None
    primary_title: str | None = None
    classification_confidence: float | None = None
    geometry_authority: str | None = None


class PageImageInfo(ORMModel):
    image_path: str
    thumbnail_path: str | None


class CalibrationRequest(ORMModel):
    point_a: tuple[float, float]
    point_b: tuple[float, float]
    real_world_feet: float = Field(gt=0)
    unit: Literal["ft", "m"] = "ft"


class PageBulkReviewRequest(ORMModel):
    status: str
    reason: str | None = None

