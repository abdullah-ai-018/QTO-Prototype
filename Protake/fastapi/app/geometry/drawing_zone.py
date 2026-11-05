"""Single, shared implementation of "is this candidate's bounding box
actually inside the sheet's drawing area" — majority-overlap against the
page classifier's `drawing_zone_bbox`, not strict containment (a real
candidate may legitimately sit right against the drawing area's edge,
while a title-block/legend box sits mostly or wholly beyond it).

Previously this exact check was implemented twice, independently, each
with its own hardcoded 0.85 constant: once for rooms in
app.geometry.engine, once for AI findings in
app.services.analysis_service. Neither wall detection (engine.py's wall
loop) nor any other caller could reuse either one without duplicating the
formula a third time. Both now import this module instead.
"""

# Share of a candidate's own bounding box that must fall inside the
# sheet's drawing area for it to count as architecture rather than
# documentation. Measured on a floor-finish sheet: the four title-block
# false rooms overlapped the drawing zone by 0.29-0.62 of their own area
# while every genuine drawing-area candidate was fully inside, so a simple
# majority test separates them without punishing a candidate drawn against
# the zone's own edge (which strict containment would).
MIN_DRAWING_ZONE_OVERLAP = 0.85


def zone_overlap_ratio(bbox_norm: dict, zone: dict) -> float:
    """Fraction of `bbox_norm`'s own area that falls inside `zone`, both
    normalized [0,1] boxes with minX/minY/maxX/maxY keys. Degrades cleanly
    for a zero-width/zero-height box (a wall segment's endpoint bbox is
    exactly this on its short axis, since a perfectly axis-aligned wall has
    no extent perpendicular to itself): the ratio reduces to the fraction
    of the segment's length inside the zone along its long axis.

    A raw min/max overlap computation gives 0/0 for a genuinely zero-width
    or zero-height box regardless of whether it sits inside the zone —
    `min(maxY, zoneMaxY) - max(minY, zoneMinY)` is exactly 0 whenever
    minY == maxY, which is the ordinary case for an axis-aligned wall
    segment, not an edge case. A symmetric epsilon inflation on both the
    candidate box and the overlap computation (not just the divisor) fixes
    this without measurably changing the result for any real 2D box —
    every room/AI-finding bbox in this codebase is orders of magnitude
    wider than the epsilon.
    """
    eps = 1e-6
    min_x, max_x = bbox_norm["minX"] - eps, bbox_norm["maxX"] + eps
    min_y, max_y = bbox_norm["minY"] - eps, bbox_norm["maxY"] + eps
    ox = max(0.0, min(max_x, zone["maxX"]) - max(min_x, zone["minX"]))
    oy = max(0.0, min(max_y, zone["maxY"]) - max(min_y, zone["minY"]))
    bw = max(1e-9, max_x - min_x)
    bh = max(1e-9, max_y - min_y)
    return (ox * oy) / (bw * bh)


def in_drawing_zone(bbox_norm: dict, zone: dict, min_overlap: float = MIN_DRAWING_ZONE_OVERLAP) -> bool:
    return zone_overlap_ratio(bbox_norm, zone) >= min_overlap


def segment_bbox_norm(x0: float, y0: float, x1: float, y1: float) -> dict:
    """Normalized bbox for a line segment's two endpoints — used to run a
    wall candidate through the same zone check a room polygon uses,
    without needing a closed polygon.
    """
    return {
        "minX": min(x0, x1),
        "minY": min(y0, y1),
        "maxX": max(x0, x1),
        "maxY": max(y0, y1),
    }
