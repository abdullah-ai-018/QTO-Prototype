"""
Door and opening deduction engine.
Detects, classifies, and deducts openings (2'-8' gaps with door swing arcs or deduction markers).
Enforces the critical SOP rule: NEVER measure through doors — deduct opening lengths!
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

from qto.geometry import Point, Segment, BoundingBox
from qto.segments import DoorArc


@dataclass
class Opening:
    opening_id: str
    wall_run_id: str
    page_num: int
    t_start: float  # In pt along wall
    t_end: float    # In pt along wall
    width_pt: float
    width_ft: float
    height_ft: float = 7.0
    classification: str = "CONFIRMED"  # "CONFIRMED" or "SUSPECTED"
    evidence: str = "DOOR_SWING_ARC"   # "DOOR_SWING_ARC" or "GAP_DIMENSION"
    center_pt: Optional[Point] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "opening_id": self.opening_id,
            "wall_run_id": self.wall_run_id,
            "page_num": self.page_num,
            "t_start": round(self.t_start, 4),
            "t_end": round(self.t_end, 4),
            "width_pt": round(self.width_pt, 4),
            "width_ft": round(self.width_ft, 4),
            "height_ft": round(self.height_ft, 2),
            "classification": self.classification,
            "evidence": self.evidence,
            "center_pt": self.center_pt.to_dict() if self.center_pt else None,
        }


def find_matching_door_arc(
    gap_p1: Point,
    gap_p2: Point,
    gap_pt: float,
    door_arcs: List[DoorArc],
    tolerance_pct: float = 0.35,
) -> Optional[DoorArc]:
    """
    Checks if any extracted door swing arc matches the opening gap.
    A door swing arc hinges at or near one of the gap jambs and has radius approximately equal to gap width.
    """
    mid_gap = Point((gap_p1.x + gap_p2.x) / 2.0, (gap_p1.y + gap_p2.y) / 2.0)
    search_dist = gap_pt * 1.5

    for arc in door_arcs:
        # Check distance from arc start or end (hinge) to either gap endpoint
        d_start_p1 = arc.start.distance_to(gap_p1)
        d_start_p2 = arc.start.distance_to(gap_p2)
        d_end_p1 = arc.end.distance_to(gap_p1)
        d_end_p2 = arc.end.distance_to(gap_p2)

        min_hinge_dist = min(d_start_p1, d_start_p2, d_end_p1, d_end_p2)

        # Hinge should be near one of the jambs (within ~12 pt)
        if min_hinge_dist <= max(12.0, gap_pt * 0.4):
            # Check arc radius or chord length vs gap width
            radius_diff = abs(arc.approx_radius - gap_pt)
            chord_ratio = arc.chord_length / gap_pt if gap_pt > 0 else 0

            # 90-degree swing arc has chord_length = radius * sqrt(2) ~ 1.414 * gap_pt
            if (radius_diff / gap_pt <= tolerance_pct) or (0.9 <= chord_ratio <= 1.8):
                return arc

        # Also check proximity to midpoint
        if arc.bbox.center.distance_to(mid_gap) <= search_dist:
            if abs(arc.approx_radius - gap_pt) / gap_pt <= tolerance_pct:
                return arc

    return None


def is_opposite_face_continuous(
    gap_t_start: float,
    gap_t_end: float,
    parallel_intervals: List[Tuple[float, float]],
    min_coverage_pct: float = 0.85,
) -> bool:
    """
    Checks if the opposite face of the wall is continuous across the gap.
    If the opposite face runs unbroken through the gap, this is an intersection (T-wall) rather than a door opening.
    """
    gap_len = gap_t_end - gap_t_start
    if gap_len <= 1e-6:
        return True

    for p_start, p_end in parallel_intervals:
        cov_start = max(gap_t_start, p_start)
        cov_end = min(gap_t_end, p_end)
        cov_len = max(0.0, cov_end - cov_start)
        if cov_len / gap_len >= min_coverage_pct:
            return True

    return False


def process_wall_gaps(
    collinear_spans: List[Tuple[float, float]],
    ox: float,
    oy: float,
    ux: float,
    uy: float,
    ft_per_pt: float,
    door_arcs: List[DoorArc],
    parallel_spans: List[Tuple[float, float]],
    page_num: int = 1,
    wall_run_id: str = "RUN",
    default_door_height_ft: float = 7.0,
) -> Tuple[float, float, List[Opening], List[Tuple[float, float]]]:
    """
    Evaluates all gaps between collinear wall segments along the wall axis.
    Returns:
    - total_t_start: float
    - total_t_end: float
    - openings: list of detected Opening instances (to be deducted from gross LF)
    - active_segments_spans: list of spans retained in this wall run
    """
    if not collinear_spans:
        return (0.0, 0.0, [], [])

    # Sort collinear segment spans by t_min
    sorted_spans = sorted(collinear_spans, key=lambda s: s[0])

    # Start chaining from the first span
    chained_spans: List[Tuple[float, float]] = [sorted_spans[0]]
    openings: List[Opening] = []
    opening_counter = 1

    for curr_start, curr_end in sorted_spans[1:]:
        prev_start, prev_end = chained_spans[-1]

        # Check for overlap or gap
        if curr_start <= prev_end:
            # Overlapping or touching segments: merge
            chained_spans[-1] = (prev_start, max(prev_end, curr_end))
            continue

        gap_pt = curr_start - prev_end
        gap_ft = gap_pt * ft_per_pt

        # Rule 1: Joint (< 0.5 ft) -> bridge without deduction
        if gap_ft < 0.5:
            chained_spans[-1] = (prev_start, curr_end)
            continue

        # Compute gap endpoints in world coordinates
        gap_p1 = Point(ox + prev_end * ux, oy + prev_end * uy)
        gap_p2 = Point(ox + curr_start * ux, oy + curr_start * uy)

        # Rule 2: Check for door swing arc (unambiguous opening evidence)
        matched_arc = find_matching_door_arc(gap_p1, gap_p2, gap_pt, door_arcs)

        if matched_arc is not None and (1.5 <= gap_ft <= 8.5):
            # Confirmed door opening!
            op_id = f"OP-{wall_run_id}-{opening_counter:02d}"
            opening_counter += 1
            op = Opening(
                opening_id=op_id,
                wall_run_id=wall_run_id,
                page_num=page_num,
                t_start=prev_end,
                t_end=curr_start,
                width_pt=gap_pt,
                width_ft=gap_ft,
                height_ft=default_door_height_ft,
                classification="CONFIRMED",
                evidence="DOOR_SWING_ARC",
                center_pt=Point((gap_p1.x + gap_p2.x) / 2.0, (gap_p1.y + gap_p2.y) / 2.0),
                metadata={"arc_radius": matched_arc.approx_radius},
            )
            openings.append(op)
            # Chain the wall across the opening (it is part of the wall run, deducted downstream)
            chained_spans.append((curr_start, curr_end))

        # Rule 3: T-intersection where opposite face is continuous (only when matched_arc is None)
        elif is_opposite_face_continuous(prev_end, curr_start, parallel_spans):
            chained_spans[-1] = (prev_start, curr_end)
            continue

        elif 2.0 <= gap_ft <= 4.0:
            # Standard single door width gap without explicit CAD arc: Suspected door opening
            op_id = f"OP-{wall_run_id}-{opening_counter:02d}"
            opening_counter += 1
            op = Opening(
                opening_id=op_id,
                wall_run_id=wall_run_id,
                page_num=page_num,
                t_start=prev_end,
                t_end=curr_start,
                width_pt=gap_pt,
                width_ft=gap_ft,
                height_ft=default_door_height_ft,
                classification="SUSPECTED",
                evidence="GAP_DIMENSION",
                center_pt=Point((gap_p1.x + gap_p2.x) / 2.0, (gap_p1.y + gap_p2.y) / 2.0),
            )
            openings.append(op)
            chained_spans.append((curr_start, curr_end))

        elif 4.0 < gap_ft <= 8.0 and any(abs(gap_ft - target) <= 0.5 for target in [5.0, 6.0, 7.0, 8.0]):
            # Standard double door opening width (5', 6', 7', 8')
            op_id = f"OP-{wall_run_id}-{opening_counter:02d}"
            opening_counter += 1
            op = Opening(
                opening_id=op_id,
                wall_run_id=wall_run_id,
                page_num=page_num,
                t_start=prev_end,
                t_end=curr_start,
                width_pt=gap_pt,
                width_ft=gap_ft,
                height_ft=default_door_height_ft,
                classification="SUSPECTED",
                evidence="DOUBLE_DOOR_GAP",
                center_pt=Point((gap_p1.x + gap_p2.x) / 2.0, (gap_p1.y + gap_p2.y) / 2.0),
            )
            openings.append(op)
            chained_spans.append((curr_start, curr_end))

        else:
            # Wall termination / corridor opening (> 4.0' without arc and not standard double door)
            # Wall run stops here!
            break

    total_start = chained_spans[0][0]
    total_end = chained_spans[-1][1]

    return (total_start, total_end, openings, chained_spans)
