"""Regression test for Phase 6 of the migration plan: opening host-wall
association must prefer a wall whose own span genuinely contains the
opening's projection over a merely-nearer wall whose span does not reach it.

Scenario: a short wall stub ("B") has an endpoint that sits closer, by raw
perpendicular distance, to a door than the door's true long host wall ("A")
does — but the door's projection onto B's own centerline falls well past
B's actual length (B is short; the overshoot is a large fraction of B's own
length even though it's numerically small), while the door's projection
onto A falls cleanly within A's span. Before the fix, nearest-distance-only
association would deduct this door from the wrong wall (B) instead of its
real host (A).
"""

from app.models.enums import ReviewStatus, DetectionKind, DetectionSource
from app.models.room import Room
from app.models.wall import Wall
from app.models.detection import Detection
from app.trades.drywall_semantic import DrywallSemanticWallPipeline

PAGE_ID = 500
SCALE_INFO = {
    PAGE_ID: {
        "scale_ft_per_px": 0.017217,
        "width_px": 8013,
        "height_px": 5660,
    }
}


def _wall(wall_id: int, start_norm: dict, end_norm: dict, length_ft: float) -> Wall:
    return Wall(
        id=wall_id,
        page_id=PAGE_ID,
        length_ft=length_ft,
        height_ft=9.0,
        start_norm=start_norm,
        end_norm=end_norm,
        confidence=0.95,
        thickness_ft=0.417,
        thickness_measured=False,
        face_a_segment_id=wall_id * 10,
        face_b_segment_id=wall_id * 10 + 1,
        status=ReviewStatus.APPROVED,
    )


def _door(det_id: int, cx: float, cy: float) -> Detection:
    half_w, half_h = 0.006, 0.003
    return Detection(
        id=det_id,
        page_id=PAGE_ID,
        kind=DetectionKind.DOOR,
        label="door",
        polygon_norm=[],
        bbox_norm={"minX": cx - half_w, "minY": cy - half_h, "maxX": cx + half_w, "maxY": cy + half_h},
        confidence=0.9,
        source=DetectionSource.YOLO,
        status=ReviewStatus.APPROVED,
    )


def test_opening_prefers_in_span_wall_over_nearer_out_of_span_stub():
    # Wall A: the door's true host — long, and the door's projection onto
    # A's centerline falls cleanly within A's own span.
    wall_a = _wall(1, {"x": 0.20, "y": 0.32}, {"x": 0.30, "y": 0.32}, length_ft=13.8)
    # Wall B: a short decoy stub whose endpoint is numerically closer to the
    # door than A is, but whose own span does not reach the door — the
    # overshoot (t_raw ~1.6) is large relative to B's own short length.
    wall_b = _wall(2, {"x": 0.240, "y": 0.30}, {"x": 0.245, "y": 0.30}, length_ft=0.69)

    rooms = [
        Room(id=1, page_id=PAGE_ID, name="Room", area_sqft=150.0, perimeter_ft=50.0,
             status=ReviewStatus.APPROVED,
             polygon_norm=[{"x": 0.20, "y": 0.20}, {"x": 0.30, "y": 0.20},
                            {"x": 0.30, "y": 0.32}, {"x": 0.20, "y": 0.32}]),
    ]

    door = _door(101, cx=0.248, cy=0.3003)

    pipeline = DrywallSemanticWallPipeline()
    results = pipeline.process_architectural_walls(
        rooms, [wall_a, wall_b],
        opening_detections=[door],
        page_scale_info=SCALE_INFO,
    )

    by_id = {aw.id: aw for aw in results}
    aw_a = next(aw for aw in results if aw.id.endswith("-1"))
    aw_b = next(aw for aw in results if aw.id.endswith("-2"))

    # Sanity: confirm the raw-distance premise this test is built on — B
    # really is numerically nearer to the door than A is, so a
    # nearest-distance-only association would have picked B.
    import math

    def _clamped_dist(px, py, x1, y1, x2, y2):
        dx, dy = x2 - x1, y2 - y1
        l2 = dx * dx + dy * dy
        t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
        return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))

    dist_to_a = _clamped_dist(0.248, 0.3003, 0.20, 0.32, 0.30, 0.32)
    dist_to_b = _clamped_dist(0.248, 0.3003, 0.240, 0.30, 0.245, 0.30)
    assert dist_to_b < dist_to_a, (
        "Test premise violated: B must be numerically nearer than A for this "
        "to demonstrate the span-projection fix has any effect."
    )

    # The actual regression check: the door must be deducted from A (the
    # in-span host), not B (the merely-nearer, out-of-span stub).
    assert aw_a.opening_count == 1, "Door should be deducted from wall A (in-span host)"
    assert aw_a.opening_area_sqft > 0.0
    assert aw_b.opening_count == 0, "Door must NOT be deducted from wall B (out-of-span decoy)"
    assert aw_b.opening_area_sqft == 0.0
