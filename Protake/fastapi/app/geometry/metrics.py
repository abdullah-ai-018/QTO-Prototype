"""Pixel <-> real-world unit conversions.

`DEFAULT_SCALE_FT_PER_PX` is a documented assumption (1/8" = 1'-0"
architectural scale, rendered at 200 DPI) used until a page is
explicitly calibrated — exactly like every commercial takeoff tool
defaults to an assumed scale pending user calibration.

`ScaleContext` carries that value together with where it came from and
whether it is trustworthy, so geometry can express a physical constraint
("a wall is at least 3 inches thick") instead of a pixel one ("at least
29px"), and can tell a measured scale apart from an assumed one rather
than treating both as fact.
"""

from dataclasses import dataclass

# At 1/8" = 1'-0": 1 drawn inch = 96 real inches = 8 real feet.
# At WORKING_DPI (300) px/inch: 1 px = 1/300 drawn inch = 8/300 real feet.
DEFAULT_SCALE_FT_PER_PX = 8.0 / 300.0  # = 0.02667 ft/px

METERS_TO_FEET = 3.280839895013123


def default_scale_ft_per_px(dpi: float) -> float:
    """Same 1/8"=1'-0" fallback assumption as `DEFAULT_SCALE_FT_PER_PX`,
    generalized to whatever DPI a page was actually rasterized at.

    Pages are no longer all rendered at a fixed 300 DPI — large sheets
    (ARCH D/E) are rasterized at a lower adaptive DPI to keep processing
    time bounded (see `app.services.pdf_engine.compute_adaptive_dpi`) —
    so the uncalibrated-page default must scale with the page's real dpi,
    not the old constant, or areas would be silently wrong on those sheets.
    """
    return 8.0 / dpi


# Where a page's scale came from, strongest evidence first. The ordering is
# the one blueprint_service already applies and documents: a scale measured
# off the sheet's own gridline dimensions beats the printed note, because
# the note states what the drawing was *authored* at and not necessarily
# what this PDF was *plotted* at (measured on a real sheet where the note
# was 2.00x off and inflated every area ~4x).
SCALE_SOURCE_USER = "user_calibration"
SCALE_SOURCE_MEASURED = "dimension_measurement"
SCALE_SOURCE_PRINTED = "printed_notation"
SCALE_SOURCE_REFERENCE_OBJECT = "reference_object_calibration"
SCALE_SOURCE_ASSUMED = "assumed_default"

# Confidence attached to each source. These are not tuned detector
# thresholds — they rank evidence quality so a consumer can require
# "measured or better" without hardcoding source names.
_SOURCE_CONFIDENCE = {
    SCALE_SOURCE_USER: 1.0,
    SCALE_SOURCE_MEASURED: 0.9,
    SCALE_SOURCE_PRINTED: 0.75,
    SCALE_SOURCE_REFERENCE_OBJECT: 0.65,
    SCALE_SOURCE_ASSUMED: 0.0,
}


def calibrate_scale_from_reference_objects(
    detections: list,
    dpi: float,
    wall_thickness_px: float | None = None,
    sheet_width_px: float = 3300.0,
) -> tuple["ScaleContext | None", dict]:
    """Attempt to reverse-engineer exact scale from reference objects (doors, windows, wall thickness).
    
    Returns (ScaleContext | None, diagnostics_dict)
    """
    import numpy as np

    diagnostics = {
        "door_count_total": 0,
        "door_count_high_conf": 0,
        "door_candidates_valid_bbox": 0,
        "door_candidates_inliers": 0,
        "window_count_high_conf": 0,
        "tier_used": None,
        "derived_ft_per_px": None,
    }

    if not detections and not wall_thickness_px:
        return None, diagnostics

    doors = [
        d for d in detections
        if getattr(d, "kind", None) == "door" or getattr(getattr(d, "kind", None), "value", None) == "door"
    ]
    diagnostics["door_count_total"] = len(doors)

    high_conf_doors = [d for d in doors if getattr(d, "confidence", 0.0) >= 0.45]
    if not high_conf_doors and doors:
        high_conf_doors = doors
    diagnostics["door_count_high_conf"] = len(high_conf_doors)


    candidate_scales = []
    for d in high_conf_doors:
        bbox = getattr(d, "bbox_norm", None)
        if not bbox:
            continue

        if isinstance(bbox, dict):
            min_x = bbox.get("minX", bbox.get("x", 0))
            min_y = bbox.get("minY", bbox.get("y", 0))
            max_x = bbox.get("maxX", min_x + bbox.get("width", 0))
            max_y = bbox.get("maxY", min_y + bbox.get("height", 0))
        else:
            min_x = getattr(bbox, "minX", getattr(bbox, "x", 0))
            min_y = getattr(bbox, "minY", getattr(bbox, "y", 0))
            max_x = getattr(bbox, "maxX", min_x + getattr(bbox, "width", 0))
            max_y = getattr(bbox, "maxY", min_y + getattr(bbox, "height", 0))

        w_norm = abs(max_x - min_x)
        h_norm = abs(max_y - min_y)

        if w_norm <= 0 or h_norm <= 0:
            continue

        short_dim_norm = min(w_norm, h_norm)
        long_dim_norm = max(w_norm, h_norm)
        aspect = long_dim_norm / short_dim_norm

        if aspect < 0.5 or aspect > 2.2:
            continue

        short_px = short_dim_norm * sheet_width_px
        if short_px < 10 or short_px > 450:
            continue

        diagnostics["door_candidates_valid_bbox"] += 1
        # Door width assumed = 3.0 ft
        cand_ft_per_px = 3.0 / short_px
        candidate_scales.append(cand_ft_per_px)

    if candidate_scales:
        scales_arr = np.array(candidate_scales)
        if len(scales_arr) >= 3:
            med = float(np.median(scales_arr))
            mad = float(np.median(np.abs(scales_arr - med)))
            inliers = scales_arr[np.abs(scales_arr - med) <= 1.5 * max(mad, 1e-4)]
            diagnostics["door_candidates_inliers"] = len(inliers)
            ft_per_px = float(np.mean(inliers)) if len(inliers) > 0 else med
        else:
            diagnostics["door_candidates_inliers"] = len(scales_arr)
            ft_per_px = float(np.median(scales_arr))

        diagnostics["tier_used"] = "door"
        diagnostics["derived_ft_per_px"] = ft_per_px
        ctx = ScaleContext(
            ft_per_px=ft_per_px,
            source=SCALE_SOURCE_REFERENCE_OBJECT,
            confidence=0.65,
            is_calibrated=True,
        )
        return ctx, diagnostics

    # 2. Window Tier
    windows = [
        d for d in detections
        if getattr(d, "kind", None) == "window" or getattr(getattr(d, "kind", None), "value", None) == "window"
    ]
    high_conf_windows = [w for w in windows if getattr(w, "confidence", 0.0) >= 0.80]
    diagnostics["window_count_high_conf"] = len(high_conf_windows)

    if high_conf_windows:
        win_scales = []
        for w in high_conf_windows:
            bbox = getattr(w, "bbox_norm", None)
            if not bbox:
                continue
            if isinstance(bbox, dict):
                min_x = bbox.get("minX", bbox.get("x", 0))
                min_y = bbox.get("minY", bbox.get("y", 0))
                max_x = bbox.get("maxX", min_x + bbox.get("width", 0))
                max_y = bbox.get("maxY", min_y + bbox.get("height", 0))
            else:
                min_x = getattr(bbox, "minX", getattr(bbox, "x", 0))
                min_y = getattr(bbox, "minY", getattr(bbox, "y", 0))
                max_x = getattr(bbox, "maxX", min_x + getattr(bbox, "width", 0))
                max_y = getattr(bbox, "maxY", min_y + getattr(bbox, "height", 0))

            w_norm = abs(max_x - min_x)
            h_norm = abs(max_y - min_y)
            if w_norm > 0 and h_norm > 0:
                short_px = min(w_norm, h_norm) * sheet_width_px
                if short_px >= 10:
                    # Use 3.5 ft (average commercial/residential window width).
                    # 3.0 ft (door width) was incorrect and degraded scale calibration.
                    win_scales.append(3.5 / short_px)
        if win_scales:
            ft_per_px = float(np.median(win_scales))
            diagnostics["tier_used"] = "window"
            diagnostics["derived_ft_per_px"] = ft_per_px
            ctx = ScaleContext(
                ft_per_px=ft_per_px,
                source=SCALE_SOURCE_REFERENCE_OBJECT,
                confidence=0.45,
                is_calibrated=True,
            )
            return ctx, diagnostics

    # 3. Wall Thickness Tier (Standard 5-inch stud wall = DEFAULT_WALL_THICKNESS_FT = 5/12 ft)
    if wall_thickness_px and wall_thickness_px > 3:
        ft_per_px = DEFAULT_WALL_THICKNESS_FT / wall_thickness_px
        diagnostics["tier_used"] = "wall_thickness"
        diagnostics["derived_ft_per_px"] = ft_per_px
        ctx = ScaleContext(
            ft_per_px=ft_per_px,
            source=SCALE_SOURCE_REFERENCE_OBJECT,
            confidence=0.30,
            is_calibrated=True,
        )
        return ctx, diagnostics

    return None, diagnostics



@dataclass(frozen=True)
class ScaleContext:
    """A page's drawing scale plus its provenance.

    `is_calibrated` is the load-bearing field: it is False for an assumed
    scale, and geometry must not apply real-world size gates when it is
    False. The fallback assumption (1/8"=1'-0") is frequently wrong by a
    factor of several on a real sheet, so filtering in feet derived from it
    silently deletes valid geometry — which is why the scale-free
    page-relative gates exist alongside the physical ones.

    Immutable so it can be threaded through the pipeline without any stage
    being able to quietly redefine the page's scale mid-analysis.
    """

    ft_per_px: float
    source: str
    confidence: float
    is_calibrated: bool

    # --- conversions -------------------------------------------------
    # The image is never resized, so these apply to the original raster's
    # pixel coordinates throughout.

    def px_to_ft(self, px: float) -> float:
        return px * self.ft_per_px

    def px_to_in(self, px: float) -> float:
        return px * self.ft_per_px * 12.0

    def ft_to_px(self, feet: float) -> float:
        return feet / self.ft_per_px if self.ft_per_px > 0 else 0.0

    def in_to_px(self, inches: float) -> float:
        return (inches / 12.0) / self.ft_per_px if self.ft_per_px > 0 else 0.0

    def sqft_per_sqpx(self) -> float:
        return self.ft_per_px**2

    # --- constructors ------------------------------------------------

    @classmethod
    def assumed(cls, dpi: float) -> "ScaleContext":
        """The uncalibrated fallback. Explicitly NOT calibrated, and
        confidence 0.0 — a consumer that requires real-world units must be
        able to see that this is an assumption, not a measurement.
        """
        return cls(
            ft_per_px=default_scale_ft_per_px(dpi),
            source=SCALE_SOURCE_ASSUMED,
            confidence=_SOURCE_CONFIDENCE[SCALE_SOURCE_ASSUMED],
            is_calibrated=False,
        )

    @classmethod
    def from_ft_per_px(
        cls, ft_per_px: float | None, source: str, dpi: float
    ) -> "ScaleContext":
        """Build from an already-derived feet-per-pixel value. Falls back to
        `assumed` when the value is missing or non-positive — a scale is
        never fabricated to satisfy a caller (see
        `app.ocr.parsers._parse_scale_ratio` for the same rule at the
        parsing end).
        """
        if not ft_per_px or ft_per_px <= 0:
            return cls.assumed(dpi)
        return cls(
            ft_per_px=float(ft_per_px),
            source=source,
            confidence=_SOURCE_CONFIDENCE.get(source, 0.5),
            is_calibrated=source != SCALE_SOURCE_ASSUMED,
        )

    @classmethod
    def from_printed_ratio(cls, ratio: float | None, dpi: float) -> "ScaleContext":
        """From a printed scale note's dimensionless ratio (1/48, 1/96,
        1/100 ...). `ratio=None` means the note could not be read, which
        yields an uncalibrated context rather than a guess.
        """
        if not ratio or ratio <= 0:
            return cls.assumed(dpi)
        return cls.from_ft_per_px(scale_ft_per_px_from_ratio(ratio, dpi), SCALE_SOURCE_PRINTED, dpi)

    @classmethod
    def from_legacy(
        cls, scale_ft_per_px: float | None, scale_is_calibrated: bool, dpi: float
    ) -> "ScaleContext":
        """Adapter for the existing (float, bool) call convention, so
        callers that have not been migrated keep working unchanged.
        """
        if not scale_ft_per_px or scale_ft_per_px <= 0:
            return cls.assumed(dpi)
        if not scale_is_calibrated:
            return cls(
                ft_per_px=float(scale_ft_per_px),
                source=SCALE_SOURCE_ASSUMED,
                confidence=_SOURCE_CONFIDENCE[SCALE_SOURCE_ASSUMED],
                is_calibrated=False,
            )
        return cls.from_ft_per_px(scale_ft_per_px, SCALE_SOURCE_USER, dpi)


def calibrate_scale_ft_per_px(
    point_a_px: tuple[float, float],
    point_b_px: tuple[float, float],
    real_world_value: float,
    unit: str = "ft",
) -> float:
    """`real_world_value` is in `unit` ("ft" or "m") — converted to feet
    once here so every downstream measurement stays canonically feet/sqft.
    """
    import math

    real_world_feet = real_world_value * METERS_TO_FEET if unit == "m" else real_world_value

    pixel_distance = math.hypot(point_b_px[0] - point_a_px[0], point_b_px[1] - point_a_px[1])
    if pixel_distance <= 0:
        raise ValueError("Calibration points must not be identical")
    return real_world_feet / pixel_distance


def wall_length_ft(start_px: tuple[float, float], end_px: tuple[float, float], scale_ft_per_px: float) -> float:
    import math

    pixel_length = math.hypot(end_px[0] - start_px[0], end_px[1] - start_px[1])
    return round(pixel_length * scale_ft_per_px, 2)


def scale_ft_per_px_from_ratio(ratio: float, dpi: float) -> float:
    """Converts an OCR-detected drawing-scale ratio (e.g. 1/96 for
    1/8"=1'-0", or 1/100 for a metric "1:100" plot scale — both are
    dimensionless real:drawn ratios, see `app.ocr.parsers._parse_scale_ratio`)
    into feet-per-pixel at the given rasterization DPI. Same derivation as
    `DEFAULT_SCALE_FT_PER_PX` above, generalized to any detected ratio.
    """
    if ratio <= 0:
        raise ValueError("ratio must be positive")
    return 1.0 / (ratio * 12 * dpi)


# A drawn wall stroke is measured, not assumed, but the measurement can
# still be nonsense on a page whose wall mask is really hatching or a tile
# pattern. These bound it to what a wall can physically be: a 2" stud
# partition at the low end (below that it is a drawn line, not a wall) and
# a 4' mass-masonry/retaining wall at the high end.
MIN_MEASURED_WALL_THICKNESS_FT = 2.0 / 12.0
# 24in covers everything from a stud partition to thick mass masonry. It
# was 4ft, which was loose enough to admit measurements that had paired a
# wall face with the far side of a corridor instead of its own opposite
# face — those surfaced as ~100cm "walls" on a real sheet, among otherwise
# textbook 15/20/25/30cm values. A genuinely thicker-than-24in wall now
# falls back to the assumed default, which is the safe direction: an
# assumption is labelled as one in the UI, a bad measurement is not.
MAX_MEASURED_WALL_THICKNESS_FT = 2.0

# Fallback when a segment's thickness cannot be measured (mask unavailable,
# or every sample rejected). Matches the Wall model's own column default:
# exact 5" (5/12 ft = 0.416666... ft) stud wall with board both sides.
DEFAULT_WALL_THICKNESS_FT = 5.0 / 12.0

# Samples are taken along the segment rather than at its midpoint alone,
# because a midpoint can land on a doorway, a wall junction (where the
# distance transform reports the *joint's* half-width, not the wall's), or
# a gap. The median of many samples is robust to all three.
_THICKNESS_SAMPLE_COUNT = 15

# A junction reports a locally larger half-width than the wall itself, so
# samples are taken away from the ends where junctions concentrate.
_THICKNESS_SAMPLE_INSET = 0.15


def measure_wall_thickness_ft(
    start_px: tuple[float, float],
    end_px: tuple[float, float],
    wall_distance_px,
    scale_ft_per_px: float,
) -> float | None:
    """The wall's real-world thickness, measured off the wall mask.

    `wall_distance_px` is the Euclidean distance transform of the wall mask
    (see cv2.distanceTransform), i.e. at every wall pixel, how far it is to
    the nearest non-wall pixel. On a wall's centerline that distance is
    exactly half the wall's width, so 2x the value sampled along the
    segment is the drawn stroke width — which is what the wall's real
    thickness is, since a floor plan draws walls in section.

    Returns None when nothing plausible could be measured, so the caller
    can fall back rather than record a fabricated number.
    """
    if scale_ft_per_px <= 0 or wall_distance_px is None:
        return None

    height, width = wall_distance_px.shape[:2]
    x1, y1 = start_px
    x2, y2 = end_px

    half_widths: list[float] = []
    for i in range(_THICKNESS_SAMPLE_COUNT):
        # Spread samples across the inset middle of the segment.
        t = _THICKNESS_SAMPLE_INSET + (1.0 - 2.0 * _THICKNESS_SAMPLE_INSET) * (
            i / max(1, _THICKNESS_SAMPLE_COUNT - 1)
        )
        px, py = int(round(x1 + (x2 - x1) * t)), int(round(y1 + (y2 - y1) * t))
        if not (0 <= px < width and 0 <= py < height):
            continue
        half_width = float(wall_distance_px[py, px])
        if half_width > 0:
            half_widths.append(half_width)

    if not half_widths:
        return None

    half_widths.sort()
    median_half_width = half_widths[len(half_widths) // 2]
    thickness_ft = 2.0 * median_half_width * scale_ft_per_px
    if not (MIN_MEASURED_WALL_THICKNESS_FT <= thickness_ft <= MAX_MEASURED_WALL_THICKNESS_FT):
        return None
    return round(thickness_ft, 3)


# How closely a raw face line must parallel a merged centerline to count as
# one of that wall's two faces. Rasterized-then-revectorized strokes wobble
# by a degree or so, and a true face is dead parallel by construction.
_FACE_ANGLE_TOLERANCE_DEG = 8.0

# A face must sit within this multiple of the expected wall thickness of
# the centerline. Generous, since it is bounded by the plausibility gate
# below anyway — its job is only to exclude the *next* wall over.
_FACE_MAX_OFFSET_FT = MAX_MEASURED_WALL_THICKNESS_FT

# The two faces must overlap along the wall's own direction by at least
# this share of the centerline, so a perpendicular wall crossing near one
# end is not mistaken for a face of this one.
_FACE_MIN_OVERLAP_RATIO = 0.25


def measure_wall_thickness_from_faces(
    segment,
    face_segments: list,
    scale_ft_per_px: float,
) -> float | None:
    """Wall thickness as the perpendicular gap between the wall's two drawn
    face lines.

    A CAD floor plan draws a wall in section as a *pair* of parallel lines
    (its two faces), with the wall's real thickness being the gap between
    them — verified on a real ArchiCAD export, whose wall layers hold only
    line items with 0.37-0.57pt stroke weights (pen weights for drawing
    those faces, carrying no thickness information themselves).

    This is the counterpart to `measure_wall_thickness_ft`, which reads
    thickness off a mask's own stroke width. That works when the mask *is*
    the drawn wall band (the raster path, where the band was found by
    opening at the wall's stroke thickness), but not on the vector-layer
    path: there the mask is drawn synthetically at a uniform nominal width,
    so measuring it just returns that synthetic constant. Measured on the
    real sheet, only 1 of 148 walls produced a plausible value that way, and
    that one was coincidence.

    `face_segments` are the pre-merge segments — both faces still separate,
    before merge_collinear_segments collapses each pair to one centerline.
    """
    import math

    if scale_ft_per_px <= 0 or not face_segments:
        return None

    length = segment.length
    if length <= 0:
        return None

    angle = math.radians(segment.angle_deg)
    dx, dy = math.cos(angle), math.sin(angle)
    ox, oy = segment.x1, segment.y1
    max_offset_px = _FACE_MAX_OFFSET_FT / scale_ft_per_px

    def _project(x: float, y: float) -> tuple[float, float]:
        """(along, perpendicular) of a point in the segment's own frame."""
        rx, ry = x - ox, y - oy
        return rx * dx + ry * dy, -rx * dy + ry * dx

    offsets: list[float] = []
    for face in face_segments:
        delta = abs(face.angle_deg - segment.angle_deg) % 180.0
        if min(delta, 180.0 - delta) > _FACE_ANGLE_TOLERANCE_DEG:
            continue

        a1, p1 = _project(face.x1, face.y1)
        a2, p2 = _project(face.x2, face.y2)
        perpendicular = (p1 + p2) / 2.0
        if abs(perpendicular) > max_offset_px:
            continue

        overlap = min(max(a1, a2), length) - max(min(a1, a2), 0.0)
        if overlap < length * _FACE_MIN_OVERLAP_RATIO:
            continue
        offsets.append(perpendicular)

    # The centerline sits midway between its own two faces, so those faces
    # are the nearest parallel line on each side of it. Spanning the full
    # min-to-max instead reaches past them to whatever else runs parallel
    # nearby — the far side of a corridor, the next partition over — which
    # measured as 25 bogus 38-47in "walls" on a real sheet alongside the
    # correct 10in ones. Taking the closest face on either side keeps the
    # measurement to this wall.
    nearer = [o for o in offsets if o > 0]
    farther = [o for o in offsets if o < 0]
    if not nearer or not farther:
        # Faces found on only one side: the opposite face was not drawn, was
        # broken up, or the centerline landed on a face rather than between
        # a pair. No pair, no measurement.
        return None

    thickness_ft = (min(nearer) - max(farther)) * scale_ft_per_px
    if not (MIN_MEASURED_WALL_THICKNESS_FT <= thickness_ft <= MAX_MEASURED_WALL_THICKNESS_FT):
        return None
    return round(thickness_ft, 3)
