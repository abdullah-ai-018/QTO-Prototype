"""Shapely wrappers: turn raw pixel polygons into normalized geometry +
real-world measurements, and expose adjacency/containment queries used
by the room/wall linking step.
"""

import math
from typing import Any

from shapely.geometry import Point, Polygon
from shapely.validation import make_valid

MIN_POLYGON_VERTICES = 3


def to_valid_polygon(points_px) -> Polygon:
    """Repair a self-intersecting contour into a valid polygon.

    When make_valid splits a bowtie into several pieces, the largest piece
    is the room; falling back to the convex hull instead (as this used to)
    silently inflates the area of every non-convex room — an L-shaped room
    would be reported as the full rectangle enclosing it.
    """
    poly = Polygon(points_px)
    if poly.is_valid:
        return poly

    fixed = make_valid(poly)
    if fixed.geom_type == "Polygon":
        return fixed

    candidates = [g for g in getattr(fixed, "geoms", []) if g.geom_type == "Polygon"]
    if candidates:
        return max(candidates, key=lambda g: g.area)
    return poly.convex_hull


def polygon_metrics(points_px: list[tuple[float, float]], scale_ft_per_px: float, image_w: int, image_h: int) -> dict:
    """Compute normalized geometry + real-world area/perimeter/centroid/bbox
    for one polygon, given the page's pixel-to-feet scale.
    """
    poly = to_valid_polygon(points_px)
    exterior = list(poly.exterior.coords)
    minx, miny, maxx, maxy = poly.bounds
    centroid = poly.centroid

    return {
        "polygon_norm": [[round(x / image_w, 5), round(y / image_h, 5)] for x, y in exterior],
        "bbox_norm": {
            "minX": round(minx / image_w, 5),
            "minY": round(miny / image_h, 5),
            "maxX": round(maxx / image_w, 5),
            "maxY": round(maxy / image_h, 5),
        },
        "centroid_norm": {"x": round(centroid.x / image_w, 5), "y": round(centroid.y / image_h, 5)},
        "area_sqft": round(poly.area * (scale_ft_per_px**2), 2),
        "perimeter_ft": round(poly.length * scale_ft_per_px, 2),
        "shapely_polygon": poly,
    }


# A room whose boundary was not fully derived from wall geometry — one or
# more of its edges is a synthetic cut between two OCR room-label positions
# (see room_detector._split_region_by_label_seeds) — is an approximation of
# where a wall probably is, not a measurement of where one is. It must never
# reach a reviewer looking as trustworthy as a wall-enclosed room: on the AUC
# sheet these were being reported at 0.95, indistinguishable from genuinely
# wall-bounded rooms, which is what let a visibly wrong diagonal cut through
# a rectangular room pass as high-confidence. Capped rather than merely
# penalised, so no combination of favourable area/vertex terms can push one
# back up into the band a real wall-derived room occupies.
UNVERIFIED_ROOM_CONFIDENCE_CAP = 0.45

# A real architectural room is overwhelmingly rectilinear. This is a general
# safety net against ANY code path emitting an implausible shape at high
# confidence — independent of which one produced it — so a future regression
# of this failure class is caught even if its specific cause is new.
RECTILINEAR_ANGLE_TOLERANCE_DEG = 10.0
MIN_RECTILINEAR_CORNER_SHARE = 0.7
NON_RECTILINEAR_CONFIDENCE_CAP = 0.6

# The single most important architectural question about a room candidate:
# what share of its outline is actually against wall ink. A real enclosed
# room is bounded by walls on nearly all of its perimeter; a title block, a
# notes box, and an open exterior slab are not bounded by walls at all,
# however clean and rectangular they look.
#
# Measured across the validation sheets, scored against INDEPENDENT wall
# evidence (see detect_room_polygons' wall_evidence_mask — scoring against
# the mask that produced the polygon is circular and does not discriminate):
#
#   real wall-bounded rooms (CAD sheet, vector wall layer):
#       0.575 0.575 0.689 0.690 0.736 0.756 0.765 0.827 0.827
#       0.837 0.855 0.909 0.926 0.926          -> min 0.575
#   exterior patio/slab polygons (raster sheet):   0.131 0.080 0.072
#   title-block / documentation boxes (raster sheet, empty wall band): 0.000
#
# 0.50 sits 4.4x above the worst false positive and 15% below the worst
# genuine room. Too high and a real room with wide cased openings or a
# doorway-heavy wall gets demoted; too low and a rectangle floating in open
# sheet keeps high confidence, which is the bug being fixed.
MIN_WALL_CONTACT_FOR_HIGH_CONFIDENCE = 0.50
LOW_WALL_SUPPORT_CONFIDENCE_CAP = 0.40

# A candidate outside the sheet's drawing area (page_classifier's
# drawing_zone_bbox, which until now was computed and never read by
# anything) is documentation — title block, revision table, key plan — not
# architecture. Capped rather than deleted so the geometry survives for
# review instead of vanishing silently.
OUTSIDE_DRAWING_ZONE_CONFIDENCE_CAP = 0.30


def rectilinear_corner_share(polygon_norm: list[list[float]]) -> float:
    """Share of a polygon's interior corners that are within
    RECTILINEAR_ANGLE_TOLERANCE_DEG of a right angle.

    Scale-free: uses normalized coordinates and only compares directions,
    so it is unaffected by page size, DPI, or a wrong scale assumption.
    """
    n = len(polygon_norm)
    if n < 3:
        return 0.0
    right = 0
    counted = 0
    for i in range(n):
        ax, ay = polygon_norm[i - 1]
        bx, by = polygon_norm[i]
        cx, cy = polygon_norm[(i + 1) % n]
        v1x, v1y = ax - bx, ay - by
        v2x, v2y = cx - bx, cy - by
        m1 = math.hypot(v1x, v1y)
        m2 = math.hypot(v2x, v2y)
        if m1 <= 1e-9 or m2 <= 1e-9:
            continue
        cos_theta = max(-1.0, min(1.0, (v1x * v2x + v1y * v2y) / (m1 * m2)))
        angle = math.degrees(math.acos(cos_theta))
        counted += 1
        if abs(angle - 90.0) <= RECTILINEAR_ANGLE_TOLERANCE_DEG:
            right += 1
    if counted == 0:
        return 0.0
    return right / counted


def room_confidence(
    area_sqft: float,
    num_vertices: int,
    wall_verified: bool = True,
    polygon_norm: list[list[float]] | None = None,
    wall_contact: float | None = None,
    in_drawing_zone: bool = True,
) -> float:
    """Deterministic plausibility score for a detected room polygon — not
    a fixed placeholder. A genuine architectural room is essentially never
    under ~12 sqft (even a mechanical closet/pantry is close to that floor)
    and is a fairly simple polygon; small slivers with many vertices are
    far more likely a false positive off decorative linework, hatching, or
    a title-block graphic than a real enclosed room. This is what lets a
    reviewer (or an automated QA gate) tell those apart instead of every
    detected polygon carrying the same fixed confidence regardless of how
    plausible it actually is.

    `wall_verified=False` marks a polygon at least one of whose edges is an
    approximated cut rather than a real wall — see
    UNVERIFIED_ROOM_CONFIDENCE_CAP.

    `polygon_norm`, when supplied, additionally gates on rectilinearity —
    see MIN_RECTILINEAR_CORNER_SHARE.
    """
    score = 0.95
    if area_sqft < 4:
        score -= 0.55
    elif area_sqft < 12:
        score -= 0.30 * (12 - area_sqft) / 8
    if area_sqft > 3000:
        # A polygon this large is usually the outer building envelope caught
        # whole because interior walls didn't fully close, not one real room.
        score -= 0.20
    if num_vertices > 16:
        score -= 0.15

    if not wall_verified:
        score = min(score, UNVERIFIED_ROOM_CONFIDENCE_CAP)

    if polygon_norm is not None:
        if rectilinear_corner_share(polygon_norm) < MIN_RECTILINEAR_CORNER_SHARE:
            score = min(score, NON_RECTILINEAR_CONFIDENCE_CAP)

    # The decisive architectural question: is this rectangle actually
    # bounded by walls? See MIN_WALL_CONTACT_FOR_HIGH_CONFIDENCE.
    if wall_contact is not None and wall_contact < MIN_WALL_CONTACT_FOR_HIGH_CONFIDENCE:
        score = min(score, LOW_WALL_SUPPORT_CONFIDENCE_CAP)

    # Outside the sheet's drawing area is documentation, not architecture.
    if not in_drawing_zone:
        score = min(score, OUTSIDE_DRAWING_ZONE_CONFIDENCE_CAP)

    return round(max(0.15, min(0.98, score)), 2)


def wall_touches_room(
    wall_start_px: tuple[float, float],
    wall_end_px: tuple[float, float],
    room_polygon: Polygon,
    tolerance_px: float = 6.0,
) -> bool:
    """True if a wall segment lies effectively on a room's boundary
    (within `tolerance_px`), used to link Wall rows to their bounding Room.
    """
    from shapely.geometry import LineString

    line = LineString([wall_start_px, wall_end_px])
    return line.distance(room_polygon.exterior) <= tolerance_px


def rooms_are_adjacent(poly_a: Polygon, poly_b: Polygon, tolerance_px: float = 8.0) -> bool:
    """True if two room polygons share (or nearly share) a boundary —
    i.e. they are separated by a single wall rather than open space."""
    return poly_a.distance(poly_b) <= tolerance_px


# Added past the wall's own thickness, past the half-thickness step that
# already gets the probe to the wall's face (see wall_orientation_by_topology's
# docstring) — a few extra pixels of slack so the probe lands safely inside
# the room polygon rather than exactly on its boundary, where floating-point/
# rasterization noise makes Polygon.contains() unreliable either way.
TOPOLOGY_PROBE_MARGIN_PX = 4.0


def _room_index_containing(point: Point, room_polygons: list[Polygon]) -> int | None:
    for idx, poly in enumerate(room_polygons):
        if poly.contains(point):
            return idx
    return None


def _majority_room_index(votes: list[int | None]) -> int | None:
    """The room index at least 2 of 3 probe samples agreed on, or None if
    no room got a majority (mixed doorway/gap samples, or genuinely no
    room on that side)."""
    counts: dict[int, int] = {}
    for v in votes:
        if v is not None:
            counts[v] = counts.get(v, 0) + 1
    if not counts:
        return None
    best_room, best_count = max(counts.items(), key=lambda kv: kv[1])
    return best_room if best_count >= 2 else None


def wall_orientation_by_topology(
    seg,
    room_shapely_polys: list[Polygon],
    wall_distance_px,
    probe_margin_px: float = TOPOLOGY_PROBE_MARGIN_PX,
    min_probe_dist_px: float = 2.0,
) -> tuple[str, list[str]]:
    """Classify a wall segment as exterior/interior by testing which room
    polygon (if any) lies on each side of it, instead of the older proxy of
    "is this segment near the building's bounding-box edge" — which fails
    on any non-rectangular footprint (L-shaped, courtyard) where an
    interior wall can sit just as close to the bbox edge as an exterior one.

    `seg` carries the wall's CENTERLINE coordinates (line_extraction's
    merge_collinear_segments collapses a wall's two drawn face-lines down
    to one centerline before a segment ever reaches this point), while a
    room polygon's boundary is traced at the wall's FACE — detect_room_polygons
    floods the *inverse* of the wall mask, so the room boundary coincides
    with the mask's own edge, some local half-thickness away from the
    centerline on each side.

    `wall_distance_px` (cv2.distanceTransform of the SAME wall mask room
    polygons were traced against — see metrics.measure_wall_thickness_ft,
    which reads the identical array) gives that half-thickness PER PIXEL
    rather than one page-wide guess. That distinction matters in practice:
    an earlier version of this function used a single page-level thickness
    constant, and on a real vector-layer floor plan 57% of walls came back
    "inconclusive" (no room found on either side) purely because the probe
    distance was too short near door/window openings, where engine.py seals
    the mask with a morphological closing far wider than the nominal wall
    stroke — the probe was landing inside the wall's own rasterized band
    instead of past it into the room. Sampling the actual local distance
    transform at each probe point's own location removes that mismatch
    entirely, since it queries the exact mask the room boundary came from
    instead of assuming a page-wide constant approximates it everywhere.

    Probes 3 points along the segment (25%/50%/75%) rather than just the
    midpoint and takes a 2-of-3 majority per side, so a wall run that
    happens to cross a doorway opening at its exact midpoint doesn't read
    as "no room on this side" from a single unlucky sample.

    Returns one of:
      "exterior"            - a room on exactly one side, nothing on the other
      "interior"             - a different room on each side
      "same_room_both_sides" - the same room polygon on both sides, which a
                                real dividing wall should never produce; kept
                                distinct from "interior" so a caller can log
                                it as a possible false-positive wall rather
                                than silently defaulting it to interior
      "inconclusive"          - no room detected on either side (missed room
                                detection, or genuinely outside all polygons
                                without a clear single-sided result) — caller
                                should fall back to the next signal in the
                                chain (thickness clustering, then bbox-margin)
    plus a `reasons` list for logging, matching this codebase's convention
    of never deciding something silently.
    """
    dx, dy = seg.x2 - seg.x1, seg.y2 - seg.y1
    length = math.hypot(dx, dy)
    if length == 0 or not room_shapely_polys:
        return "inconclusive", ["topology_no_data"]

    dist_h, dist_w = wall_distance_px.shape[:2] if wall_distance_px is not None else (0, 0)
    nx_, ny_ = -dy / length, dx / length

    side_a_votes: list[int | None] = []
    side_b_votes: list[int | None] = []
    for t in (0.25, 0.5, 0.75):
        px = seg.x1 + dx * t
        py = seg.y1 + dy * t

        local_half_width = None
        if wall_distance_px is not None:
            ix, iy = int(round(px)), int(round(py))
            if 0 <= ix < dist_w and 0 <= iy < dist_h:
                sample = float(wall_distance_px[iy, ix])
                if sample > 0:
                    local_half_width = sample
        probe_dist = (local_half_width if local_half_width is not None else min_probe_dist_px) + probe_margin_px

        point_a = Point(px + nx_ * probe_dist, py + ny_ * probe_dist)
        point_b = Point(px - nx_ * probe_dist, py - ny_ * probe_dist)
        side_a_votes.append(_room_index_containing(point_a, room_shapely_polys))
        side_b_votes.append(_room_index_containing(point_b, room_shapely_polys))

    room_a = _majority_room_index(side_a_votes)
    room_b = _majority_room_index(side_b_votes)

    if room_a is not None and room_b is not None:
        if room_a == room_b:
            return "same_room_both_sides", ["topology_same_room_both_sides"]
        return "interior", [f"topology_between_rooms:{room_a}:{room_b}"]

    if (room_a is None) != (room_b is None):
        return "exterior", ["topology_one_side_outside_footprint"]

    return "inconclusive", ["topology_no_room_either_side"]


def contour_raster_wall_contact(
    polygon_px: Polygon,
    raster_wall_segments: list,
    tolerance_px: float = 15.0,
    image_w: int = 8013,
    image_h: int = 5660,
) -> float:
    """Share of a room polygon's exterior boundary that lies within `tolerance_px`
    of detected raster Hough wall line segments (from engine.py's wall extraction).

    Completely separate metric from vector_wall_contact so vector wall layers
    and raster line evidence are evaluated distinctly without corrupting each other.
    """
    if polygon_px is None or not raster_wall_segments:
        return 0.0

    from shapely.geometry import MultiLineString, LineString

    lines = []
    for seg in raster_wall_segments:
        if hasattr(seg, "x1"):
            lines.append(LineString([(seg.x1, seg.y1), (seg.x2, seg.y2)]))
        elif hasattr(seg, "start_norm") and hasattr(seg, "end_norm"):
            sn = seg.start_norm
            en = seg.end_norm
            lines.append(LineString([(sn["x"] * image_w, sn["y"] * image_h), (en["x"] * image_w, en["y"] * image_h)]))
        elif isinstance(seg, (list, tuple)) and len(seg) == 4:
            lines.append(LineString([(seg[0], seg[1]), (seg[2], seg[3])]))

    if not lines:
        return 0.0

    wall_multiline = MultiLineString(lines)
    exterior = polygon_px.exterior
    if exterior.length <= 0:
        return 0.0

    # Sample 100 points along exterior boundary to compute exact contact ratio
    num_samples = 100
    touch_count = 0
    for i in range(num_samples):
        pt = exterior.interpolate(i / num_samples, normalized=True)
        if wall_multiline.distance(pt) <= tolerance_px:
            touch_count += 1

    return round(touch_count / num_samples, 3)


RECIPROCAL_DIRECTIONS = {
    "north": "south",
    "south": "north",
    "east": "west",
    "west": "east",
    "north_east": "south_west",
    "south_west": "north_east",
    "north_west": "south_east",
    "south_east": "north_west",
    "unknown": "unknown",
}


def classify_cardinal_direction(dx: float, dy: float) -> str:
    """Classifies a 2D direction vector into canonical cardinal directions.
    Normalized page coordinates: (0,0) is top-left, +x is East, +y is South (downward).
    """
    import math
    mag = math.hypot(dx, dy)
    if mag < 1e-7:
        return "unknown"
    nx, ny = dx / mag, dy / mag

    # Check primary 4 cardinal directions vs diagonals
    abs_x, abs_y = abs(nx), abs(ny)
    if abs_y >= 2.0 * abs_x:
        return "north" if ny < 0 else "south"
    elif abs_x >= 2.0 * abs_y:
        return "east" if nx > 0 else "west"
    else:
        # Diagonal quadrant
        v_part = "north" if ny < 0 else "south"
        h_part = "east" if nx > 0 else "west"
        return f"{v_part}_{h_part}"


def extract_room_boundary_segments(polygon_norm: list) -> list[dict]:
    """Decomposes a normalized room polygon into directed boundary edges with
    outward-facing normal vectors and classified cardinal directions.
    """
    import math
    if not polygon_norm or len(polygon_norm) < 3:
        return []

    # Clean pts
    pts: list[tuple[float, float]] = []
    for p in polygon_norm:
        if isinstance(p, dict) and "x" in p and "y" in p:
            pts.append((float(p["x"]), float(p["y"])))
        elif isinstance(p, (list, tuple)) and len(p) >= 2:
            pts.append((float(p[0]), float(p[1])))

    if len(pts) < 3:
        return []

    # Ensure closed loop
    if pts[0] != pts[-1]:
        pts.append(pts[0])

    # Compute polygon centroid
    poly_shapely = Polygon(pts)
    if not poly_shapely.is_valid:
        poly_shapely = poly_shapely.buffer(0)
    cx, cy = (poly_shapely.centroid.x, poly_shapely.centroid.y) if not poly_shapely.is_empty else (
        sum(p[0] for p in pts[:-1]) / len(pts[:-1]),
        sum(p[1] for p in pts[:-1]) / len(pts[:-1]),
    )

    boundaries = []
    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        edx, edy = x2 - x1, y2 - y1
        length = math.hypot(edx, edy)
        if length < 1e-5:
            continue

        mid_x = (x1 + x2) / 2.0
        mid_y = (y1 + y2) / 2.0

        # Vector from centroid to edge midpoint
        to_mid_x = mid_x - cx
        to_mid_y = mid_y - cy

        # Two candidate perpendicular unit normals
        n1_x, n1_y = -edy / length, edx / length
        n2_x, n2_y = edy / length, -edx / length

        # Pick the one pointing outward (positive dot product with centroid-to-midpoint)
        dot1 = n1_x * to_mid_x + n1_y * to_mid_y
        dot2 = n2_x * to_mid_x + n2_y * to_mid_y

        if dot1 >= dot2:
            out_nx, out_ny = n1_x, n1_y
        else:
            out_nx, out_ny = n2_x, n2_y

        direction = classify_cardinal_direction(out_nx, out_ny)
        boundaries.append({
            "edge_index": i,
            "start": {"x": round(x1, 5), "y": round(y1, 5)},
            "end": {"x": round(x2, 5), "y": round(y2, 5)},
            "midpoint": {"x": round(mid_x, 5), "y": round(mid_y, 5)},
            "length_norm": round(length, 5),
            "outward_normal": {"x": round(out_nx, 4), "y": round(out_ny, 4)},
            "direction": direction,
        })

    return boundaries


def compute_wall_face_directions(start_norm: dict | tuple, end_norm: dict | tuple) -> dict[str, Any]:
    """Computes the normal vectors and cardinal facing directions for a wall's Side A and Side B."""
    import math
    if isinstance(start_norm, dict):
        x1, y1 = float(start_norm["x"]), float(start_norm["y"])
    else:
        x1, y1 = float(start_norm[0]), float(start_norm[1])

    if isinstance(end_norm, dict):
        x2, y2 = float(end_norm["x"]), float(end_norm["y"])
    else:
        x2, y2 = float(end_norm[0]), float(end_norm[1])

    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return {
            "side_a_normal": {"x": 0.0, "y": 0.0},
            "side_a_direction": "unknown",
            "side_b_normal": {"x": 0.0, "y": 0.0},
            "side_b_direction": "unknown",
        }

    # Side A = left normal, Side B = right normal
    sa_nx, sa_ny = -dy / length, dx / length
    sb_nx, sb_ny = dy / length, -dx / length

    return {
        "side_a_normal": {"x": round(sa_nx, 4), "y": round(sa_ny, 4)},
        "side_a_direction": classify_cardinal_direction(sa_nx, sa_ny),
        "side_b_normal": {"x": round(sb_nx, 4), "y": round(sb_ny, 4)},
        "side_b_direction": classify_cardinal_direction(sb_nx, sb_ny),
    }


