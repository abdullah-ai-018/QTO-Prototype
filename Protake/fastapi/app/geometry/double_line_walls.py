"""Double-line wall detection: independent raster wall evidence for sheets
that draw walls as two thin strokes with a hollow cavity between them.

`wall_band.py` isolates walls by stroke *thickness* — a morphological
opening that keeps only ink wider than its kernel. That works when walls
are drawn as heavy poché, and fails completely when they are drawn as a
pair of thin lines: measured on a real finish-plan sheet, the wall strokes
are 5-8px wide, so ANY opening kernel large enough to suppress that sheet's
2px tile hatch also erases the walls themselves. Its wall band came out
holding only the 30-74px column blobs — no wall at all. That is a
structural limit of the thickness approach, not a tuning problem, which is
why this is a separate detector rather than a threshold change there.

What a double-line wall looks like, measured by scanning across a known
partition at five heights on that sheet:

    y=2000:  x=5634 w=6 | x=5651 w=5 | ... | x=5698 w=5 | x=5714 w=7
    y=2500:  x=5654 w=8 | x=5673 w=5 | ... | x=5698 w=5 | x=5714 w=7

Two solid strokes, each 5-8px, with white between them; outer-to-outer
22-23px, which at that sheet's verified scale (0.24 in/px, from the printed
1/4"=1'-0" note) is 5.3-5.5 real inches — a stud partition with gypsum both
sides.

The detector produces INDEPENDENT wall evidence (a band mask plus
centrelines). It deliberately does not consume, and is not consumed by, the
mask that generates room candidates — scoring a candidate against the mask
that produced it is circular self-certification (see
room_detector.detect_room_polygons' wall_evidence_mask).
"""

import math

import cv2
import numpy as np

from app.geometry.line_extraction import Segment

# --- Pair geometry -----------------------------------------------------
#
# The three discriminators below were measured together on the same sheet.
# Every parallel pair inside the building was enumerated and classified:
#
#   real wall pairs        separation 21.5-27.5px = 5.2-6.6 in   gap-ink 0.05-0.25
#   two edges of ONE line  separation  6.0- 9.0px = 1.4-2.2 in   gap-ink 0.75-1.00
#   cross-room pairings    separation up to 531px               (killed by mutual-nearest)
#
# No single test separates all three; together they do, and each corresponds
# to a physical property rather than a tuned number.

# A wall's two faces are each other's NEAREST parallel neighbour. This is
# what removes the cross-room pairings (a face matched with a face two rooms
# away) without needing any distance constant at all.
MIN_PAIR_OVERLAP = 0.35

# Real-world thickness window, used whenever the page scale is calibrated.
# Interior partitions start at ~3.5in (2x4 stud, no finish) and exterior /
# masonry walls reach ~16in; the measured sheet's partitions sit at 5.2-15.9in,
# comfortably inside.
MIN_WALL_THICKNESS_IN = 3.0
MAX_WALL_THICKNESS_IN = 16.0

# Scale-free fallback, as a share of the page's long edge, for an
# uncalibrated sheet. Derived from the same measurement: 21.5-27.5px on an
# 8400px page is 0.0026-0.0033. The window is widened either side because
# without scale we cannot know the sheet's plot ratio — deliberately
# permissive, since the hollow-cavity and mutual-nearest tests still apply.
MIN_WALL_THICKNESS_PAGE_RATIO = 0.0015
MAX_WALL_THICKNESS_PAGE_RATIO = 0.0075

# The defining property: a double-line wall is HOLLOW. Ink strictly between
# the two strokes separates the cases by a factor of three (walls 0.05-0.25,
# the two edges of a single solid stroke 0.75-1.00). 0.40 sits in that gap.
# Too high and every solid stroke's own two edges are promoted to a "wall";
# too low and a wall carrying a legitimate interruption (a door jamb symbol,
# a hatch crossing) is rejected.
MAX_CAVITY_INK = 0.40

# How far off parallel two strokes may be and still be one wall. Drafted
# walls are parallel by construction; this only absorbs Hough angle jitter.
MAX_PAIR_ANGLE_DELTA_DEG = 3.0

# A wall pair must span a real distance. Reuses the same reasoning as
# line_extraction's wall-length gate: shorter than this and a pair of
# furniture edges or a fixture outline qualifies.
MIN_WALL_PAIR_LENGTH_FT = 2.0
MIN_WALL_PAIR_LENGTH_PAGE_RATIO = 0.012

# Thickness of the band painted for each detected wall, as a share of the
# page's long edge — matched to vector_walls' convention so both evidence
# sources hand downstream code a barrier of comparable scale.
_BAND_THICKNESS_PAGE_RATIO = 1 / 1200
_MIN_BAND_THICKNESS_PX = 3


class WallPair:
    """One detected double-line wall: the two strokes, their centreline,
    and the measurements that admitted it. Kept as evidence so a later
    fusion/QA layer can explain why this is considered a wall.
    """

    __slots__ = (
        "centerline",
        "thickness_px",
        "thickness_in",
        "cavity_ink",
        "overlap",
        "orientation",
        "face_a",
        "face_b",
        "face_a_id",
        "face_b_id",
        "thickness_consistent",
    )

    def __init__(
        self,
        centerline: Segment,
        thickness_px: float,
        thickness_in: float | None,
        cavity_ink: float,
        overlap: float,
        orientation: str,
        face_a: Segment | None = None,
        face_b: Segment | None = None,
        face_a_id: int | None = None,
        face_b_id: int | None = None,
        thickness_consistent: bool = True,
    ):
        self.centerline: Segment = centerline
        self.thickness_px: float = thickness_px
        self.thickness_in: float | None = thickness_in
        self.cavity_ink: float = cavity_ink
        self.overlap: float = overlap
        self.orientation: str = orientation
        self.face_a: Segment | None = face_a
        self.face_b: Segment | None = face_b
        self.face_a_id: int | None = face_a_id if face_a_id is not None else getattr(face_a, "id", None)
        self.face_b_id: int | None = face_b_id if face_b_id is not None else getattr(face_b, "id", None)
        self.thickness_consistent: bool = thickness_consistent

    def __repr__(self) -> str:
        t = f"{self.thickness_in:.1f}in" if self.thickness_in is not None else f"{self.thickness_px:.0f}px"
        return (
            f"WallPair({self.orientation} len={self.centerline.length:.0f}px "
            f"thick={t} cavity={self.cavity_ink:.2f} fa={self.face_a_id} fb={self.face_b_id})"
        )


def _orientation(seg: Segment) -> str | None:
    a = seg.angle_deg
    if a < 15.0 or a > 165.0:
        return "H"
    if 75.0 < a < 105.0:
        return "V"
    return None


def _span(seg: Segment, orientation: str) -> tuple[float, float]:
    """Extent along the stroke's own direction."""
    if orientation == "V":
        return (min(seg.y1, seg.y2), max(seg.y1, seg.y2))
    return (min(seg.x1, seg.x2), max(seg.x1, seg.x2))


def _offset(seg: Segment, orientation: str) -> float:
    """Position across the stroke's direction — what separates the pair."""
    return (seg.x1 + seg.x2) / 2.0 if orientation == "V" else (seg.y1 + seg.y2) / 2.0


def _overlap_ratio(a: Segment, b: Segment, orientation: str) -> float:
    a0, a1 = _span(a, orientation)
    b0, b1 = _span(b, orientation)
    overlap = max(0.0, min(a1, b1) - max(a0, b0))
    shorter = max(1e-9, min(a1 - a0, b1 - b0))
    return overlap / shorter


def _cavity_ink(a: Segment, b: Segment, orientation: str, ink: np.ndarray, stroke_pad: int = 3) -> float | None:
    """Ink density strictly BETWEEN the two strokes, over the stretch where
    they run together. `stroke_pad` excludes the strokes themselves so the
    measurement is of the cavity, not of the lines bounding it.
    """
    h, w = ink.shape[:2]
    lo, hi = sorted((_offset(a, orientation), _offset(b, orientation)))
    a0, a1 = _span(a, orientation)
    b0, b1 = _span(b, orientation)
    s0, s1 = max(a0, b0), min(a1, b1)
    if s1 - s0 < 1:
        return None

    lo_i, hi_i = int(round(lo)) + stroke_pad, int(round(hi)) - stroke_pad
    s0_i, s1_i = int(round(s0)), int(round(s1))
    if hi_i <= lo_i:
        return None

    if orientation == "V":
        x0, x1, y0, y1 = lo_i, hi_i, s0_i, s1_i
    else:
        x0, x1, y0, y1 = s0_i, s1_i, lo_i, hi_i
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    if x1 <= x0 or y1 <= y0:
        return None
    region = ink[y0:y1, x0:x1]
    return float((region > 0).mean()) if region.size else None


def _centerline(a: Segment, b: Segment, orientation: str) -> Segment:
    """The wall's centreline: midway between the two strokes, spanning the
    stretch where they actually run together (the overlap interval).
    """
    mid = (_offset(a, orientation) + _offset(b, orientation)) / 2.0
    a0, a1 = _span(a, orientation)
    b0, b1 = _span(b, orientation)
    s0, s1 = max(a0, b0), min(a1, b1)
    if orientation == "V":
        c = Segment(mid, s0, mid, s1)
    else:
        c = Segment(s0, mid, s1, mid)
    c.id = a.id
    c.face_a_id = a.id
    c.face_b_id = b.id
    c.face_a = a
    c.face_b = b
    return c


def band_thickness_px(image_shape: tuple[int, int]) -> int:
    size = max(_MIN_BAND_THICKNESS_PX, int(round(max(image_shape) * _BAND_THICKNESS_PAGE_RATIO)))
    return size if size % 2 else size + 1


def detect_double_line_walls(
    segments: list[Segment],
    ink: np.ndarray,
    image_shape: tuple[int, int],
    scale_ft_per_px: float | None = None,
    scale_is_calibrated: bool = False,
) -> list[WallPair]:
    """Wall pairs found among `segments`, using `ink` to test the cavity.

    `segments` should already be wall CANDIDATES (see
    line_extraction.filter_wall_candidates) — this detector decides which of
    them pair up into walls, not which lines exist.

    When the page scale is calibrated the thickness window is applied in
    real inches; otherwise a page-relative window stands in and the result
    leans on the cavity and mutual-nearest tests. Scale is used to validate
    plausibility here — it never causes a wall to be asserted.
    """
    h, w = image_shape
    long_edge = float(max(h, w))

    if scale_is_calibrated and scale_ft_per_px and scale_ft_per_px > 0:
        in_per_px = scale_ft_per_px * 12.0
        min_sep = MIN_WALL_THICKNESS_IN / in_per_px
        max_sep = MAX_WALL_THICKNESS_IN / in_per_px
        min_len = MIN_WALL_PAIR_LENGTH_FT / scale_ft_per_px
    else:
        in_per_px = None
        min_sep = long_edge * MIN_WALL_THICKNESS_PAGE_RATIO
        max_sep = long_edge * MAX_WALL_THICKNESS_PAGE_RATIO
        min_len = long_edge * MIN_WALL_PAIR_LENGTH_PAGE_RATIO

    oriented: list[tuple[Segment, str]] = []
    for seg in segments:
        o = _orientation(seg)
        if o is not None and seg.length >= min_len:
            oriented.append((seg, o))

    # Nearest qualifying parallel neighbour for each stroke.
    nearest: dict[int, tuple[int, float]] = {}
    for i, (a, oa) in enumerate(oriented):
        best_j, best_d = None, math.inf
        for j, (b, ob) in enumerate(oriented):
            if i == j or oa != ob:
                continue
            if abs(a.angle_deg - b.angle_deg) > MAX_PAIR_ANGLE_DELTA_DEG:
                continue
            if _overlap_ratio(a, b, oa) < MIN_PAIR_OVERLAP:
                continue
            d = abs(_offset(a, oa) - _offset(b, oa))
            if d < min_sep or d > max_sep:
                continue
            if d < best_d:
                best_j, best_d = j, d
        if best_j is not None:
            nearest[i] = (best_j, best_d)

    pairs: list[WallPair] = []
    for i, (j, sep) in nearest.items():
        # Mutual: each stroke must be the other's nearest. This is what
        # rejects a face paired with something across the room.
        if nearest.get(j, (None, 0.0))[0] != i or i > j:
            continue
        a, oa = oriented[i]
        b, _ = oriented[j]
        cavity = _cavity_ink(a, b, oa, ink)
        if cavity is None or cavity > MAX_CAVITY_INK:
            continue
        overlap_val = _overlap_ratio(a, b, oa)
        centerline = _centerline(a, b, oa)
        if centerline.length < min_len:
            continue

        # ── D-010 FIX: Thickness consistency along the wall run ────────────
        # A genuine parallel wall pair has near-constant face-to-face distance.
        # Sample the perpendicular distance at 5 points along the overlap
        # region; if the coefficient of variation exceeds 35%, the pair is
        # likely two unrelated collinear strokes (furniture outline + wall)
        # that happened to pass the single-point nearest-neighbour test.
        # Marked as needs_review on the WallPair (caller can choose to exclude).
        thickness_consistent = _check_thickness_consistency(a, b, oa, in_per_px, samples=5)

        centerline.overlap_ratio = overlap_val
        centerline.thickness_in = (sep * in_per_px) if in_per_px else None
        centerline.thickness_px = sep
        pairs.append(
            WallPair(
                centerline=centerline,
                thickness_px=sep,
                thickness_in=(sep * in_per_px) if in_per_px else None,
                cavity_ink=cavity,
                overlap=overlap_val,
                orientation=oa,
                face_a=a,
                face_b=b,
                face_a_id=a.id,
                face_b_id=b.id,
                thickness_consistent=thickness_consistent,
            )
        )
    return pairs


def _point_to_line_dist(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """Perpendicular distance from point (px, py) to the infinite line through (x1,y1)→(x2,y2)."""
    dx, dy = x2 - x1, y2 - y1
    denom = math.hypot(dx, dy)
    if denom < 1e-6:
        return math.hypot(px - x1, py - y1)
    return abs(dy * px - dx * py + x2 * y1 - y2 * x1) / denom


def _check_thickness_consistency(
    a: Segment, b: Segment, orientation: str, in_per_px: float | None, samples: int = 5
) -> bool:
    """Sample perpendicular thickness at `samples` evenly-spaced points along
    face A; return True when the coefficient of variation is ≤ 35%.

    Uses the perpendicular from face A to the infinite line of face B, so
    slight non-parallelism (real-world drafting drift) still passes while
    converging or fan-shaped strokes (furniture) fail.
    """
    MAX_THICKNESS_CV = 0.35  # coefficient of variation threshold

    thicknesses = []
    for k in range(samples):
        t = k / max(1, samples - 1)
        if orientation == "H":
            px = a.x1 + t * (a.x2 - a.x1)
            py = (a.y1 + a.y2) / 2.0
        else:
            px = (a.x1 + a.x2) / 2.0
            py = a.y1 + t * (a.y2 - a.y1)
        d = _point_to_line_dist(px, py, b.x1, b.y1, b.x2, b.y2)
        thicknesses.append(d)

    if not thicknesses or max(thicknesses) < 1e-6:
        return True  # can't measure → don't reject

    mean_t = sum(thicknesses) / len(thicknesses)
    if mean_t < 1e-6:
        return True
    variance = sum((t - mean_t) ** 2 for t in thicknesses) / len(thicknesses)
    cv = math.sqrt(variance) / mean_t
    return cv <= MAX_THICKNESS_CV


def wall_pairs_to_mask(pairs: list[WallPair], image_shape: tuple[int, int]) -> np.ndarray | None:
    """Paint detected walls as a band mask, for use as INDEPENDENT wall
    evidence. Returns None when nothing was detected, so callers can tell
    "no evidence" apart from "empty evidence" and avoid certifying
    candidates against a blank mask.
    """
    if not pairs:
        return None
    mask = np.zeros(image_shape, dtype=np.uint8)
    thickness = band_thickness_px(image_shape)
    for pair in pairs:
        c = pair.centerline
        # Paint the wall at its measured thickness, not a nominal one, so
        # the band corresponds to the wall actually drawn.
        band = max(thickness, int(round(pair.thickness_px)))
        cv2.line(mask, (int(round(c.x1)), int(round(c.y1))), (int(round(c.x2)), int(round(c.y2))), 255, band)
    return mask
