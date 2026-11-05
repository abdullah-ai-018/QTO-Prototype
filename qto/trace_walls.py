"""
Wall tracing engine: Leader line endpoint detection, seed segment search,
and collinear chaining across valid joints (<0.5') with opening detection.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

from qto.geometry import (
    Point,
    Segment,
    BoundingBox,
    point_to_segment_distance,
    angle_diff,
    project_point_to_axis,
)
from qto.segments import DoorArc
from qto.openings import Opening, process_wall_gaps


@dataclass
class TracedWall:
    seed_segment: Segment
    leader_segment: Optional[Segment]
    traced_segments: List[Segment]
    collinear_segments: List[Segment]
    parallel_segments: List[Segment]
    twin_offsets: List[float]
    t_start: float
    t_end: float
    openings: List[Opening]
    ox: float
    oy: float
    ux: float
    uy: float
    metadata: dict[str, Any] = field(default_factory=dict)


def find_leader_endpoint(
    tc_x: float,
    tc_y: float,
    tag_radius: float,
    segments: List[Segment],
    max_search_dist: float = 130.0,
) -> Tuple[float, float, Optional[Segment]]:
    """
    Checks if a CAD leader line starts near the edge of the tag callout box
    and points outward toward a wall.
    Returns (anchor_x, anchor_y, leader_segment).
    """
    best_leader: Optional[Segment] = None
    best_score = float("inf")
    anchor_x, anchor_y = tc_x, tc_y

    min_start = max(3.0, tag_radius * 0.45)
    max_start = tag_radius + 16.0

    for seg in segments:
        if not (6.0 <= seg.length <= 110.0):
            continue

        # Quick bounding box proximity check around tag center
        if (
            seg.max_x < tc_x - max_search_dist
            or seg.min_x > tc_x + max_search_dist
            or seg.max_y < tc_y - max_search_dist
            or seg.min_y > tc_y + max_search_dist
        ):
            continue

        d1 = math.hypot(seg.x1 - tc_x, seg.y1 - tc_y)
        d2 = math.hypot(seg.x2 - tc_x, seg.y2 - tc_y)

        # Case 1: Endpoint 1 is on the tag callout border, Endpoint 2 points outward
        if min_start <= d1 <= max_start and d2 > d1 + 6.0:
            if d1 < best_score:
                best_score = d1
                best_leader = seg
                anchor_x, anchor_y = seg.x2, seg.y2

        # Case 2: Endpoint 2 is on the tag callout border, Endpoint 1 points outward
        elif min_start <= d2 <= max_start and d1 > d2 + 6.0:
            if d2 < best_score:
                best_score = d2
                best_leader = seg
                anchor_x, anchor_y = seg.x1, seg.y1

    return (anchor_x, anchor_y, best_leader)


def find_seed_segment(
    anchor_x: float,
    anchor_y: float,
    tc_x: float,
    tc_y: float,
    tag_radius: float,
    segments: List[Segment],
    leader_seg: Optional[Segment],
    search_radius_no_leader: float = 42.0,
) -> Optional[Segment]:
    """
    Finds the closest wall line segment to the anchor point.
    Filters out the leader line and segments inside the tag callout box.
    """
    search_radius = 24.0 if leader_seg is not None else search_radius_no_leader
    seed_seg: Optional[Segment] = None
    best_dist = search_radius

    for seg in segments:
        # Wall segment must be longer than 12pt and not be the leader line
        if seg.length < 12.0 or seg is leader_seg:
            continue

        # Ignore segments whose midpoint is inside the tag callout box
        mid_x = (seg.x1 + seg.x2) / 2.0
        mid_y = (seg.y1 + seg.y2) / 2.0
        if math.hypot(mid_x - tc_x, mid_y - tc_y) < tag_radius * 0.9 and seg.length < 22.0:
            continue

        # Quick bbox filter
        if (
            seg.max_x < anchor_x - search_radius
            or seg.min_x > anchor_x + search_radius
            or seg.max_y < anchor_y - search_radius
            or seg.min_y > anchor_y + search_radius
        ):
            continue

        dist, _, _, _ = point_to_segment_distance(
            anchor_x, anchor_y, seg.x1, seg.y1, seg.x2, seg.y2
        )
        if dist < best_dist:
            best_dist = dist
            seed_seg = seg

    return seed_seg


def trace_wall_from_seed(
    seed_seg: Segment,
    leader_seg: Optional[Segment],
    segments: List[Segment],
    door_arcs: List[DoorArc],
    ft_per_pt: float,
    page_num: int = 1,
    wall_run_id: str = "RUN",
    max_angle_tol_deg: float = 3.5,
) -> Optional[TracedWall]:
    """
    Traces a complete wall partition run from a seed segment:
    1. Projects candidate segments onto the seed segment's local 1D axis.
    2. Identifies collinear segments on the primary face and parallel segments on the opposite face.
    3. Chains collinear segments across valid joints (<0.5') and detects door openings (2'-8').
    4. Gathers opposite face parallel segments.
    """
    ox, oy = seed_seg.x1, seed_seg.y1
    ux, uy = seed_seg.ux, seed_seg.uy
    seed_angle = seed_seg.angle
    max_angle_tol = math.radians(max_angle_tol_deg)

    collinear_candidates: List[Tuple[float, float, float, Segment]] = []
    parallel_candidates: List[Tuple[float, float, float, Segment]] = []

    for seg in segments:
        if seg.length < 8.0 or seg is leader_seg:
            continue
        if angle_diff(seg.angle, seed_angle) > max_angle_tol:
            continue

        t1, d1 = project_point_to_axis(seg.x1, seg.y1, ox, oy, ux, uy)
        t2, d2 = project_point_to_axis(seg.x2, seg.y2, ox, oy, ux, uy)

        t_min, t_max = min(t1, t2), max(t1, t2)
        d_avg = 0.5 * (d1 + d2)

        if abs(d_avg) <= 0.75:
            collinear_candidates.append((t_min, t_max, d_avg, seg))
        elif 1.0 <= abs(d_avg) <= 13.0:
            parallel_candidates.append((t_min, t_max, d_avg, seg))

    if not collinear_candidates:
        collinear_candidates.append((0.0, seed_seg.length, 0.0, seed_seg))

    # Extract spans for collinear chaining
    collinear_spans = [(t_min, t_max) for t_min, t_max, _, _ in collinear_candidates]
    parallel_spans = [(t_min, t_max) for t_min, t_max, _, _ in parallel_candidates]

    # Process gaps with opening deduction engine
    t_start, t_end, openings, active_spans = process_wall_gaps(
        collinear_spans=collinear_spans,
        ox=ox,
        oy=oy,
        ux=ux,
        uy=uy,
        ft_per_pt=ft_per_pt,
        door_arcs=door_arcs,
        parallel_spans=parallel_spans,
        page_num=page_num,
        wall_run_id=wall_run_id,
    )

    # Collect traced collinear segments whose spans fall within [t_start - 2, t_end + 2]
    traced_collinear: List[Segment] = []
    for t_min, t_max, _, seg in collinear_candidates:
        if t_max >= t_start - 2.0 and t_min <= t_end + 2.0:
            if seg not in traced_collinear:
                traced_collinear.append(seg)

    # Collect parallel double-line segments (opposite face of the drywall assembly)
    traced_parallel: List[Segment] = []
    twin_offsets: List[float] = []

    for t_min, t_max, d_avg, seg in parallel_candidates:
        overlap = min(t_end, t_max) - max(t_start, t_min)
        if overlap >= 4.0:
            if seg not in traced_parallel:
                traced_parallel.append(seg)
                twin_offsets.append(d_avg)

    all_traced = list(traced_collinear) + list(traced_parallel)

    return TracedWall(
        seed_segment=seed_seg,
        leader_segment=leader_seg,
        traced_segments=all_traced,
        collinear_segments=traced_collinear,
        parallel_segments=traced_parallel,
        twin_offsets=twin_offsets,
        t_start=t_start,
        t_end=t_end,
        openings=openings,
        ox=ox,
        oy=oy,
        ux=ux,
        uy=uy,
    )
