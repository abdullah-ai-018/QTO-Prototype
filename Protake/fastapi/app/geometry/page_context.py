"""One composed context object carrying everything analyze_page's
detectors need to know about a page BEFORE any wall or room candidate is
generated.

This does not replace `page_classifier.ClassificationResult` or
`metrics.ScaleContext` — it composes them (see `PageContext.build`), so
every existing caller/test that already builds those two keeps working
completely unchanged. PageContext exists so a detector that previously had
no access to page_type/drawing_zone/scale/trade at all (wall extraction)
can now receive all of them through one parameter instead of five, and so
there is exactly one place — not two, not three — that knows what "inside
the drawing zone" means (see drawing_zone.py).

Unknown context stays unknown: `selected_trade` is None until a project
has genuinely selected one, `has_vector_data`/`ocr_available` are plain
facts about what this page actually has, never assumed defaults.
"""

from dataclasses import dataclass

from app.geometry.drawing_zone import MIN_DRAWING_ZONE_OVERLAP, zone_overlap_ratio
from app.geometry.metrics import ScaleContext
from app.geometry.page_classifier import ClassificationResult


@dataclass(frozen=True)
class PageContext:
    page_type: str
    discipline: str
    is_takeoff_eligible: bool
    drawing_zone: dict
    scale_context: ScaleContext
    width_px: int
    height_px: int
    # Whether this page's PDF exposed usable vector drawing content
    # (get_drawings() returned line/rect items) as opposed to being a
    # raster-only scan/image upload. Independent of has_wall_layer below —
    # a vector PDF may still have no wall-named layer.
    has_vector_data: bool
    # Whether this page's own wall-named (or wall-lineweight-recovered)
    # CAD layer was found — see vector_walls.extract_wall_mask_from_layers.
    # Distinct from has_vector_data: a vector PDF can have drawing content
    # with no wall layer at all (a flattened/generic export).
    has_wall_layer: bool
    # Whether any OCR/PDF-text spatial hint (word boxes) was available for
    # this page. False means the wall-band/text-blanking machinery had
    # nothing to work with, not that it was skipped.
    ocr_available: bool
    # Only set when a project has an explicit, persisted trade selection
    # (see app.models.trade.TradeConfig) — None otherwise, including for
    # every page processed before/without one. Never defaulted.
    selected_trade: str | None = None

    @property
    def scale(self) -> float:
        return self.scale_context.ft_per_px

    @property
    def scale_is_calibrated(self) -> bool:
        return self.scale_context.is_calibrated

    def zone_overlap_ratio(self, bbox_norm: dict) -> float:
        return zone_overlap_ratio(bbox_norm, self.drawing_zone)

    def in_drawing_zone(self, bbox_norm: dict, min_overlap: float = MIN_DRAWING_ZONE_OVERLAP) -> bool:
        return self.zone_overlap_ratio(bbox_norm) >= min_overlap

    @classmethod
    def build(
        cls,
        classification: ClassificationResult,
        scale_context: ScaleContext,
        width_px: int,
        height_px: int,
        has_vector_data: bool,
        has_wall_layer: bool,
        ocr_available: bool,
        selected_trade: str | None = None,
    ) -> "PageContext":
        return cls(
            page_type=classification.page_type.value,
            discipline=classification.discipline,
            is_takeoff_eligible=classification.is_takeoff_eligible,
            drawing_zone=classification.drawing_zone_bbox,
            scale_context=scale_context,
            width_px=width_px,
            height_px=height_px,
            has_vector_data=has_vector_data,
            has_wall_layer=has_wall_layer,
            ocr_available=ocr_available,
            selected_trade=selected_trade,
        )
