"""Line-segment extraction and merging from a rasterized blueprint page.

Pipeline: Canny edges -> probabilistic Hough transform -> angle/offset
clustering -> collinear-segment merge. Every step is deterministic:
the same input image always produces the same wall segments.
"""

from dataclasses import dataclass

import cv2
import numpy as np

ANGLE_BUCKET_DEG = 5.0
OFFSET_CLUSTER_PX = 6.0
MIN_LINE_LENGTH_PX = 20
MAX_LINE_GAP_PX = 15
HOUGH_THRESHOLD = 40

# --- Wall-candidate filtering (real-world units, so these hold regardless
# --- of the page's rasterization DPI) ---
#
# The Hough transform cannot tell a wall from a dimension line, a hatching
# stroke, a furniture outline, or a door-swing chord — it returns every
# straight edge it finds. Feeding all of that into the wall mask shatters
# the floor plan into hundreds of tiny fragments, each of which the
# flood fill then reports as a "room". These thresholds discriminate on
# the two properties that actually separate walls from annotation
# linework: real-world length, and agreement with the drawing's dominant
# orthogonal axes.
MIN_WALL_LENGTH_FT = 2.0  # nothing shorter than this is a wall segment
OFF_AXIS_MIN_WALL_LENGTH_FT = 5.0  # angled lines must be substantially longer to qualify
DOMINANT_ANGLE_TOLERANCE_DEG = 8.0

# Page-relative equivalents, used when the page scale is only assumed rather
# than known. The fallback scale assumption (1/8"=1'-0") is often wrong by a
# factor of several, and converting feet through a wrong scale would either
# discard real walls or admit noise; a fraction of the page's long edge is
# a scale-free stand-in that behaves consistently across sheet sizes.
MIN_WALL_LENGTH_PAGE_RATIO = 0.0035
OFF_AXIS_MIN_WALL_LENGTH_PAGE_RATIO = 0.010


# A dashed/hidden-line annotation (roof overhang edge, property line, match
# line, centerline — all drafted dashed by convention) is exactly as long
# and exactly as axis-agreeable as a real wall, so neither test above catches
# it. What's different is the stroke itself: a real wall is solid ink for
# its whole length; a dashed line is ink for only its dash segments. Verified
# on a real sheet where a single diagonal "EDGE OF ROOF LINE OVERHANG" dash
# line got merged into one continuous ~2400px "wall" segment spanning nearly
# the whole page — sampled at 4px spacing, only ~38% of points along it hit
# ink, versus 95%+ for every genuine wall run sampled the same way. Requiring
# most of the segment's length to actually be inked drops the dashed line
# without touching solid strokes.
DASH_INK_SAMPLE_STEP_PX = 4
DASH_INK_PROBE_RADIUS_PX = 2

# A real wall is not 100% inked either — a doorway opening along its run is
# a normal, legitimate gap, not evidence of a dashed annotation. Measured on
# a real (if simple) floor plan: a genuine solid wall segment with a doorway
# in it came out to 65-68% ink coverage, while the dashed roof-overhang line
# this filter was built for (see its docstring) measured ~38%. The original
# 0.75 threshold sat inside the real-wall range and rejected the wall
# instead of the annotation — verified by that exact false rejection
# breaking room detection on that plan. 0.5 sits in the wide gap between
# the two measured cases.
MIN_SOLID_INK_RATIO = 0.5

# A real angled wall (a chamfered corner, an angled bay) is drawn at one
# consistent off-axis angle, sometimes two (the bay's return wall). Organic/
# decorative linework — a tree canopy, a texture fill, a compass rose — has
# no consistent angle at all: verified on a real sheet, a tree symbol's
# outline decomposed into 13 Hough segments spanning 12 different angles
# packed into one ~500x600px patch, each individually long enough to pass
# the off-axis length test above. Counting how many distinctly-angled
# off-axis neighbors a segment has nearby catches this directly, without
# needing to recognize "tree" as a concept — it's a length/axis-blind
# structural difference between architecture and decoration.
CLUTTER_NEIGHBOR_RADIUS_PAGE_RATIO = 0.08
CLUTTER_ANGLE_BUCKET_DEG = 20.0
CLUTTER_MIN_DISTINCT_ANGLES = 4

# How far apart two collinear fragments may be, measured along their shared
# line, and still be treated as one wall broken by a gap. Bridging small
# gaps is desirable (it seals the breaks that let the room flood fill leak);
# bridging arbitrary distances is not, because two unrelated fragments at
# opposite ends of the sheet can fall into the same angle/offset cluster and
# would otherwise be joined into one segment slicing across the drawing.
MAX_COLLINEAR_MERGE_GAP_PAGE_RATIO = 0.035
# Only trust the dominant-axis test when the drawing really is orthogonal:
# if the two dominant axes don't account for at least this share of total
# line length, the sheet is angled/irregular and the test is skipped.
MIN_DOMINANT_AXIS_LENGTH_SHARE = 0.35


@dataclass
class Segment:
    x1: float
    y1: float
    x2: float
    y2: float
    id: int | None = None
    source_type: str = "vector"
    raw_coords: tuple[float, float, float, float] | None = None
    face_a_id: int | None = None
    face_b_id: int | None = None
    face_a: "Segment | None" = None
    face_b: "Segment | None" = None
    overlap_ratio: float | None = None
    thickness_in: float | None = None
    thickness_px: float | None = None

    @property
    def length(self) -> float:
        return float(np.hypot(self.x2 - self.x1, self.y2 - self.y1))

    @property
    def angle_deg(self) -> float:
        """Angle in [0, 180)."""
        angle = np.degrees(np.arctan2(self.y2 - self.y1, self.x2 - self.x1))
        return float(angle % 180)


def _remove_specks(binary: np.ndarray, min_area_px: int = 15) -> np.ndarray:
    """Remove connected components smaller than `min_area_px` pixels.

    Scanner noise, JPEG ringing artifacts, and halftone dots produce tiny
    isolated blobs that Canny treats as edges and Hough turns into spurious
    short line segments. Removing them before edge detection dramatically
    reduces the number of false wall candidates, especially on scanned plans.
    Threshold of 15px² keeps every real ink stroke (even a short tick mark is
    several hundred pixels) while eliminating single-pixel and sub-5px specks.

    A dense CAD sheet (hatching, dimension ticks, text glyphs) can produce
    tens of thousands of components — looping over labels in Python and
    rescanning the whole image per label (`labels == label`) turned this
    into an O(labels * pixels) operation that took the better part of an
    hour on one real architectural sheet. `keep_mask[labels]` does the same
    lookup as a single vectorized pass over the image instead.
    """
    num, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    areas = stats[:, cv2.CC_STAT_AREA]
    keep_mask = areas >= min_area_px
    keep_mask[0] = False  # background label is never "kept ink"
    return np.where(keep_mask[labels], np.uint8(255), np.uint8(0))


def extract_raw_segments(gray: np.ndarray) -> list[Segment]:
    """Canny + probabilistic Hough transform over a grayscale page image."""
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    # Threshold to binary so _remove_specks can work on connected components,
    # then convert back to grayscale for Canny. Otsu gives an adaptive
    # foreground/background split that works for both light-on-dark and
    # dark-on-light plans without any fixed threshold.
    _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    clean = _remove_specks(binary)
    # Invert back so Canny sees dark lines on bright background (standard).
    clean_gray = cv2.bitwise_not(clean)
    edges = cv2.Canny(clean_gray, 40, 130, apertureSize=3)
    # Close small gaps in hand/CAD line work before detecting lines.
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))

    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=HOUGH_THRESHOLD,
        minLineLength=MIN_LINE_LENGTH_PX,
        maxLineGap=MAX_LINE_GAP_PX,
    )
    if lines is None:
        return []
    return [
        Segment(
            float(x1),
            float(y1),
            float(x2),
            float(y2),
            id=idx,
            source_type="hough",
            raw_coords=(float(x1), float(y1), float(x2), float(y2)),
        )
        for idx, (x1, y1, x2, y2) in enumerate(lines.reshape(-1, 4))
    ]


def _perpendicular_offset(seg: Segment, angle_rad: float) -> float:
    """Signed perpendicular distance of the segment's midpoint from the
    origin, measured along the normal of `angle_rad` — the clustering key
    that groups collinear segments together regardless of small angle jitter.
    """
    mx, my = (seg.x1 + seg.x2) / 2, (seg.y1 + seg.y2) / 2
    nx, ny = -np.sin(angle_rad), np.cos(angle_rad)
    return float(mx * nx + my * ny)


def _cluster_key(seg: Segment, offset_cluster_px: float) -> tuple[float, float]:
    bucket_angle = round(seg.angle_deg / ANGLE_BUCKET_DEG) * ANGLE_BUCKET_DEG
    offset = _perpendicular_offset(seg, np.radians(bucket_angle))
    bucket_offset = round(offset / offset_cluster_px) * offset_cluster_px
    return (bucket_angle % 180, bucket_offset)


def merge_collinear_segments(
    segments: list[Segment],
    image_shape: tuple[int, int] | None = None,
    offset_cluster_px: float = OFFSET_CLUSTER_PX,
    max_gap_px_override: float | None = None,
) -> list[Segment]:
    """Cluster near-collinear/overlapping raw Hough segments and collapse
    each cluster into merged segments.
    """
    clusters: dict[tuple[float, float], list[Segment]] = {}
    for seg in segments:
        clusters.setdefault(_cluster_key(seg, offset_cluster_px), []).append(seg)

    if max_gap_px_override is not None:
        max_gap_px = max_gap_px_override
    else:
        max_gap_px = (
            max(image_shape) * MAX_COLLINEAR_MERGE_GAP_PAGE_RATIO if image_shape else float(MAX_LINE_GAP_PX)
        )

    merged: list[Segment] = []
    for (bucket_angle, _offset), group in clusters.items():
        angle_rad = np.radians(bucket_angle)
        direction = np.array([np.cos(angle_rad), np.sin(angle_rad)])

        # One projected interval per fragment, sorted along the line.
        intervals: list[tuple[float, float]] = []
        for seg in group:
            a = float(np.dot((seg.x1, seg.y1), direction))
            b = float(np.dot((seg.x2, seg.y2), direction))
            intervals.append((min(a, b), max(a, b)))
        intervals.sort()

        # A point on the shared line, so a projection can be mapped back to
        # pixel coordinates: take the first fragment's midpoint and remove
        # its along-line component, leaving the line's perpendicular offset.
        seed = np.array([(group[0].x1 + group[0].x2) / 2.0, (group[0].y1 + group[0].y2) / 2.0])
        origin = seed - float(np.dot(seed, direction)) * direction

        run_start, run_end = intervals[0]
        runs: list[tuple[float, float]] = []
        for start, end in intervals[1:]:
            if start - run_end <= max_gap_px:
                run_end = max(run_end, end)
            else:
                runs.append((run_start, run_end))
                run_start, run_end = start, end
        runs.append((run_start, run_end))

        for start, end in runs:
            p_min = origin + start * direction
            p_max = origin + end * direction
            # Find the primary contributing segment in group for provenance, prioritizing paired double-line faces
            paired_segs = [s for s in group if getattr(s, "face_b_id", None) is not None]
            best_seg = max(paired_segs, key=lambda s: s.length) if paired_segs else (max(group, key=lambda s: s.length) if group else None)
            candidate = Segment(
                float(p_min[0]),
                float(p_min[1]),
                float(p_max[0]),
                float(p_max[1]),
                id=best_seg.id if best_seg else None,
                source_type=best_seg.source_type if best_seg else "vector",
                raw_coords=best_seg.raw_coords if best_seg else None,
                face_a_id=best_seg.face_a_id if best_seg else None,
                face_b_id=best_seg.face_b_id if best_seg else None,
                face_a=best_seg.face_a if best_seg else None,
                face_b=best_seg.face_b if best_seg else None,
                overlap_ratio=best_seg.overlap_ratio if best_seg else None,
                thickness_in=best_seg.thickness_in if best_seg else None,
                thickness_px=best_seg.thickness_px if best_seg else None,
            )
            if candidate.length >= MIN_LINE_LENGTH_PX:
                merged.append(candidate)

    return merged


def extract_wall_segments_from_mask(mask: np.ndarray) -> list[Segment]:
    """Hough over the *boundary* of the wall-band mask (see wall_band.py),
    instead of over raw grayscale Canny edges.

    The band mask has already separated walls from cabinetry, countertops,
    tile grids and appliance symbols by stroke thickness — the discriminator
    that makes room detection work. Wall *segments* used to be extracted
    independently, straight from the raw image via extract_raw_segments(),
    which throws that separation away: on a detailed CAD sheet, cabinet
    edges and tile lines are frequently long and axis-aligned enough to
    pass the length/angle filter, producing the dense scribbled mess of
    "walls" that don't correspond to anything on the drawing.

    HoughLinesP expects thin edges, not a filled band: run directly on the
    solid mask it "sees" support for a line at every angle that crosses a
    filled rectangle, and returns diagonal chords cutting across every wall
    and room — worse than the problem it was meant to fix. Running Canny on
    the mask first reduces it back to a true edge map (the two long edges of
    each wall band) before Hough runs, exactly like extract_raw_segments
    does for the grayscale image.
    """
    edges = cv2.Canny(mask, 40, 130, apertureSize=3)
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=HOUGH_THRESHOLD,
        minLineLength=MIN_LINE_LENGTH_PX,
        maxLineGap=MAX_LINE_GAP_PX,
    )
    if lines is None:
        return []
    return [Segment(float(x1), float(y1), float(x2), float(y2)) for x1, y1, x2, y2 in lines.reshape(-1, 4)]


def dominant_axis_angles(segments: list[Segment]) -> tuple[float, float] | None:
    """Length-weighted dominant orientation of the drawing, plus its
    perpendicular — i.e. the two axes an orthogonal floor plan is drawn
    along. Weighting by length (not segment count) matters: a plan has a
    handful of long walls and hundreds of short hatching strokes, and it
    is the walls that define the building's orientation.

    Returns None when no orientation dominates (an angled or irregular
    sheet), in which case callers should skip the axis test rather than
    filter against a meaningless axis.
    """
    if not segments:
        return None

    histogram = np.zeros(180, dtype=float)
    for seg in segments:
        histogram[int(seg.angle_deg) % 180] += seg.length

    total_length = float(histogram.sum())
    if total_length <= 0:
        return None

    # An orthogonal drawing has two peaks 90 deg apart; score each candidate
    # axis by the combined length of it and its perpendicular so the pair is
    # chosen together rather than independently.
    tolerance = int(round(DOMINANT_ANGLE_TOLERANCE_DEG))
    best_angle, best_score = None, 0.0
    for angle in range(180):
        score = 0.0
        for centre in (angle, angle + 90):
            for offset in range(-tolerance, tolerance + 1):
                score += histogram[(centre + offset) % 180]
        if score > best_score:
            best_angle, best_score = float(angle), score

    if best_angle is None or best_score / total_length < MIN_DOMINANT_AXIS_LENGTH_SHARE:
        return None
    return (best_angle, (best_angle + 90.0) % 180.0)


def _angle_distance_deg(a: float, b: float) -> float:
    """Smallest separation between two undirected angles in [0, 180)."""
    diff = abs(a - b) % 180.0
    return min(diff, 180.0 - diff)


def _is_solid_stroke(seg: Segment, ink: np.ndarray) -> bool:
    """A real wall is inked along its whole length; a dashed/hidden-line
    annotation (roof overhang, property line, centerline) is only inked at
    its dash segments. See MIN_SOLID_INK_RATIO for the measured gap between
    the two on a real sheet.
    """
    h, w = ink.shape[:2]
    n_samples = max(2, int(seg.length // DASH_INK_SAMPLE_STEP_PX))
    hits = 0
    for i in range(n_samples + 1):
        t = i / n_samples
        x = int(round(seg.x1 + (seg.x2 - seg.x1) * t))
        y = int(round(seg.y1 + (seg.y2 - seg.y1) * t))
        x0, x1 = max(0, x - DASH_INK_PROBE_RADIUS_PX), min(w, x + DASH_INK_PROBE_RADIUS_PX + 1)
        y0, y1 = max(0, y - DASH_INK_PROBE_RADIUS_PX), min(h, y + DASH_INK_PROBE_RADIUS_PX + 1)
        if x0 >= x1 or y0 >= y1:
            continue
        if (ink[y0:y1, x0:x1] > 0).any():
            hits += 1
    return (hits / (n_samples + 1)) >= MIN_SOLID_INK_RATIO


def _decorative_clutter_ids(off_axis_kept: list[Segment], radius_px: float) -> set[int]:
    """Indices (into `off_axis_kept`) of segments whose local neighborhood
    contains too many distinctly-angled other off-axis segments to be
    architecture — see CLUTTER_MIN_DISTINCT_ANGLES.
    """
    midpoints = [((s.x1 + s.x2) / 2.0, (s.y1 + s.y2) / 2.0) for s in off_axis_kept]
    radius_sq = radius_px * radius_px
    clutter: set[int] = set()
    for i, seg in enumerate(off_axis_kept):
        cx, cy = midpoints[i]
        angle_buckets = {round(seg.angle_deg / CLUTTER_ANGLE_BUCKET_DEG) * CLUTTER_ANGLE_BUCKET_DEG}
        for j, other in enumerate(off_axis_kept):
            if i == j:
                continue
            ox, oy = midpoints[j]
            if (ox - cx) ** 2 + (oy - cy) ** 2 > radius_sq:
                continue
            angle_buckets.add(round(other.angle_deg / CLUTTER_ANGLE_BUCKET_DEG) * CLUTTER_ANGLE_BUCKET_DEG)
        if len(angle_buckets) >= CLUTTER_MIN_DISTINCT_ANGLES:
            clutter.add(i)
    return clutter


def filter_wall_candidates(
    segments: list[Segment],
    scale_ft_per_px: float,
    image_shape: tuple[int, int],
    scale_is_calibrated: bool = False,
    ink: np.ndarray | None = None,
) -> list[Segment]:
    """Drop the annotation linework that the Hough transform cannot
    distinguish from walls, before it ever reaches the wall mask.

    Three deterministic tests:

      1. Anything shorter than the minimum wall length is annotation, not
         a wall — this removes hatching, tick marks, text strokes, and
         fixture detail en masse.
      2. A segment that runs off the drawing's dominant orthogonal axes
         must clear a higher length bar to qualify, which removes
         door-swing chords and furniture outlines while still keeping
         genuinely angled walls (which are long).
      3. When the page's ink is available, a segment must actually be
         inked along most of its length — see _is_solid_stroke for why
         this is what catches dashed/hidden-line annotations that the
         length and axis tests both let through (they're exactly as long
         and axis-agreeable as a real wall).
      4. An off-axis survivor whose local neighborhood contains several
         other off-axis survivors at clearly different angles is decorative
         clutter (a tree, a texture fill), not an angled wall — see
         _decorative_clutter_ids.

    Lengths are measured in real-world feet when the page's scale is known,
    and as a fraction of the page otherwise — never in feet derived from an
    assumed scale, which would make the filter's strictness depend on how
    wrong that assumption happens to be.
    """
    if not segments:
        return segments

    if scale_is_calibrated and scale_ft_per_px > 0:
        min_length_px = MIN_WALL_LENGTH_FT / scale_ft_per_px
        off_axis_min_length_px = OFF_AXIS_MIN_WALL_LENGTH_FT / scale_ft_per_px
    else:
        long_edge = float(max(image_shape))
        min_length_px = max(MIN_LINE_LENGTH_PX, long_edge * MIN_WALL_LENGTH_PAGE_RATIO)
        off_axis_min_length_px = long_edge * OFF_AXIS_MIN_WALL_LENGTH_PAGE_RATIO

    axes = dominant_axis_angles(segments)

    def _classify(seg: Segment) -> bool | None:
        """True/False = keep as on-axis/off-axis; None = reject."""
        if seg.length < min_length_px:
            return None
        on_axis = axes is None or any(
            _angle_distance_deg(seg.angle_deg, axis) <= DOMINANT_ANGLE_TOLERANCE_DEG for axis in axes
        )
        if not on_axis and seg.length < off_axis_min_length_px:
            return None
        return on_axis

    on_axis_kept: list[Segment] = []
    off_axis_kept: list[Segment] = []
    for seg in segments:
        placement = _classify(seg)
        if placement is None:
            continue
        if ink is not None and not _is_solid_stroke(seg, ink):
            continue
        (on_axis_kept if placement else off_axis_kept).append(seg)

    if off_axis_kept:
        radius_px = float(max(image_shape)) * CLUTTER_NEIGHBOR_RADIUS_PAGE_RATIO
        clutter_ids = _decorative_clutter_ids(off_axis_kept, radius_px)
        off_axis_kept = [s for i, s in enumerate(off_axis_kept) if i not in clutter_ids]

    return on_axis_kept + off_axis_kept
