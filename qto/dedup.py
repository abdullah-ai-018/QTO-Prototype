"""
Twin face matching, centerline spine generation, and wall run deduplication.
Synthesizes single centerline spines from parallel faces (1-13pt separation),
merges duplicate runs for the same tag, and flags conflicting tags on overlapping runs.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from qto.geometry import (
    Point,
    Segment,
    BoundingBox,
    angle_diff,
    project_point_to_axis,
    point_to_segment_distance,
)
from qto.openings import Opening
from qto.trace_walls import TracedWall


@dataclass
class WallRun:
    run_id: str
    tag: str
    page_num: int
    sheet_label: str
    spine: Segment
    gross_length_pt: float
    gross_length_ft: float
    opening_deduction_ft: float
    net_length_ft: float
    openings: List[Opening]
    segments: List[Segment]
    leader_segment: Optional[Segment] = None
    tag_instances: List[str] = field(default_factory=list)
    status: str = "OK"  # "OK", "REVIEW", "CONFLICT"
    conflict_tags: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    ft_per_pt: float = 0.111111
    is_manual: bool = False
    height_ft: Optional[float] = None
    thickness_pt: Optional[float] = None
    thickness_in: Optional[float] = None
    thickness_measured: bool = False
    section_callout_tag: Optional[str] = None
    is_height_verified: bool = False
    height_source: str = "UNVERIFIED_HEIGHT_DEFAULT"
    material_layers: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "tag": self.tag,
            "page_num": self.page_num,
            "sheet_label": self.sheet_label,
            "spine": self.spine.to_dict(),
            "ft_per_pt": round(self.ft_per_pt, 6),
            "gross_length_pt": round(self.gross_length_pt, 4),
            "gross_length_ft": round(self.gross_length_ft, 4),
            "opening_deduction_ft": round(self.opening_deduction_ft, 4),
            "net_length_ft": round(self.net_length_ft, 4),
            "openings_count": len(self.openings),
            "openings": [op.to_dict() for op in self.openings],
            "segment_count": len(self.segments),
            "has_leader": self.leader_segment is not None,
            "tag_instances": self.tag_instances,
            "status": self.status,
            "conflict_tags": self.conflict_tags,
            "notes": self.notes,
            "is_manual": self.is_manual,
            "height_ft": self.height_ft,
            "thickness_pt": round(self.thickness_pt, 4) if self.thickness_pt is not None else None,
            "thickness_in": round(self.thickness_in, 3) if self.thickness_in is not None else None,
            "thickness_measured": self.thickness_measured,
            "section_callout_tag": self.section_callout_tag,
            "is_height_verified": self.is_height_verified,
            "height_source": self.height_source,
            "material_layers": self.material_layers,
        }


def compute_centerline_spine(
    ox: float,
    oy: float,
    ux: float,
    uy: float,
    t_start: float,
    t_end: float,
    twin_offsets: List[float],
) -> Segment:
    """
    Calculates the true centerline spine of a double-line partition wall.
    Shifts the traced primary face line by half the average separation of the parallel opposite face.
    """
    valid_offsets = [d for d in twin_offsets if abs(d) > 1e-6]
    if valid_offsets:
        d_face2 = sum(valid_offsets) / len(valid_offsets)
        d_center = d_face2 / 2.0
    elif twin_offsets:
        d_center = (sum(twin_offsets) / len(twin_offsets)) / 2.0
    else:
        d_center = 0.0

    sx1 = ox + t_start * ux - d_center * uy
    sy1 = oy + t_start * uy + d_center * ux
    sx2 = ox + t_end * ux - d_center * uy
    sy2 = oy + t_end * uy + d_center * ux

    return Segment(x1=sx1, y1=sy1, x2=sx2, y2=sy2)


def create_wall_run(
    traced: TracedWall,
    tag: str,
    page_num: int,
    sheet_label: str,
    run_id: str,
    ft_per_pt: float,
    instance_id: str | None = None,
    assembly_attrs: Optional[Dict[str, Any]] = None,
    material_layers: Optional[List[Dict[str, str]]] = None,
) -> WallRun:
    """Creates a WallRun from a TracedWall result, calculating gross and net lengths and measured thickness."""
    spine = compute_centerline_spine(
        ox=traced.ox,
        oy=traced.oy,
        ux=traced.ux,
        uy=traced.uy,
        t_start=traced.t_start,
        t_end=traced.t_end,
        twin_offsets=traced.twin_offsets,
    )

    gross_pt = spine.length
    gross_ft = gross_pt * ft_per_pt
    open_ft = sum(op.width_ft for op in traced.openings)
    net_ft = max(0.0, gross_ft - open_ft)

    tag_insts = [instance_id] if instance_id else []

    # Wall Thickness Measurement (Feature F5, Requirement R3)
    valid_offsets = [d for d in traced.twin_offsets if abs(d) > 1e-6]
    if valid_offsets:
        d_face2 = sum(valid_offsets) / len(valid_offsets)
        thickness_pt = round(abs(d_face2), 4)
        thickness_in = round(abs(d_face2) * ft_per_pt * 12.0, 3)
        thickness_measured = True
    elif traced.twin_offsets:
        d_face2 = sum(traced.twin_offsets) / len(traced.twin_offsets)
        thickness_pt = round(abs(d_face2), 4)
        thickness_in = round(abs(d_face2) * ft_per_pt * 12.0, 3)
        thickness_measured = True
    else:
        # Single-line wall or casing not matched: nominal assembly thickness fallback
        thickness_measured = False
        thickness_pt = None
        if assembly_attrs:
            nominal = assembly_attrs.get("nominal_thickness_in")
            if nominal is None:
                stud_depth = float(assembly_attrs.get("stud_depth_in", 3.625))
                finished_faces = int(assembly_attrs.get("finished_faces", 2))
                layers_per_face = int(assembly_attrs.get("layers_per_face", 1))
                board_thick = float(assembly_attrs.get("board_thickness_in", 0.625))
                nominal = stud_depth + (finished_faces * layers_per_face * board_thick)
            thickness_in = round(float(nominal), 3)
        else:
            thickness_in = 4.875

    # Material layers resolution
    resolved_layers: List[Dict[str, str]] = []
    if material_layers:
        resolved_layers = list(material_layers)
    elif assembly_attrs and "material_layers" in assembly_attrs:
        resolved_layers = list(assembly_attrs["material_layers"])

    return WallRun(
        run_id=run_id,
        tag=tag,
        page_num=page_num,
        sheet_label=sheet_label,
        spine=spine,
        gross_length_pt=gross_pt,
        gross_length_ft=gross_ft,
        opening_deduction_ft=open_ft,
        net_length_ft=net_ft,
        openings=traced.openings,
        segments=traced.traced_segments,
        leader_segment=traced.leader_segment,
        tag_instances=tag_insts,
        status="OK",
        ft_per_pt=ft_per_pt,
        thickness_pt=thickness_pt,
        thickness_in=thickness_in,
        thickness_measured=thickness_measured,
        material_layers=resolved_layers,
    )


def are_runs_overlapping(
    run1: WallRun,
    run2: WallRun,
    ft_per_pt: float,
    max_angle_deg: float = 3.5,
    max_offset_in: float = 8.0,
    min_overlap_pct: float = 0.40,
) -> Tuple[bool, float]:
    """
    Determines whether two wall runs represent the same physical wall segment:
    - Must be on the same page.
    - Angle difference <= 3.5 degrees.
    - Perpendicular offset <= max_offset_in (converted to PDF points).
    - Longitudinal span overlap >= min_overlap_pct.
    """
    if run1.page_num != run2.page_num:
        return (False, 0.0)

    s1, s2 = run1.spine, run2.spine
    if angle_diff(s1.angle, s2.angle) > math.radians(max_angle_deg):
        return (False, 0.0)

    # Check perpendicular distance of s2 endpoints to s1 axis
    _, d1 = project_point_to_axis(s2.x1, s2.y1, s1.x1, s1.y1, s1.ux, s1.uy)
    _, d2 = project_point_to_axis(s2.x2, s2.y2, s1.x1, s1.y1, s1.ux, s1.uy)
    d_perp = 0.5 * (abs(d1) + abs(d2))

    # Convert max offset inches to points: 1 in = 72 pt, or via scale
    # In world points, 6-8 inches is ~ 4-10 points depending on scale
    max_offset_pt = (max_offset_in / 12.0) / ft_per_pt if ft_per_pt > 0 else 12.0
    if d_perp > max_offset_pt:
        return (False, 0.0)

    # Project spans onto s1 axis
    t1_a, _ = project_point_to_axis(s1.x1, s1.y1, s1.x1, s1.y1, s1.ux, s1.uy)
    t1_b, _ = project_point_to_axis(s1.x2, s1.y2, s1.x1, s1.y1, s1.ux, s1.uy)
    t2_a, _ = project_point_to_axis(s2.x1, s2.y1, s1.x1, s1.y1, s1.ux, s1.uy)
    t2_b, _ = project_point_to_axis(s2.x2, s2.y2, s1.x1, s1.y1, s1.ux, s1.uy)

    min_t1, max_t1 = min(t1_a, t1_b), max(t1_a, t1_b)
    min_t2, max_t2 = min(t2_a, t2_b), max(t2_a, t2_b)

    overlap = min(max_t1, max_t2) - max(min_t1, min_t2)
    min_len = min(max_t1 - min_t1, max_t2 - min_t2)
    if min_len <= 1e-6:
        return (False, 0.0)

    overlap_pct = overlap / min_len
    if overlap_pct >= min_overlap_pct:
        return (True, overlap_pct)

    return (False, 0.0)


def deduplicate_wall_runs(runs: List[WallRun], ft_per_pt: float) -> List[WallRun]:
    """
    Deduplicates wall runs:
    - Same tag overlapping runs are merged into a single consolidated WallRun.
    - Differing tag overlapping runs are flagged as CONFLICT for estimator review.
    """
    if not runs:
        return []

    deduped: List[WallRun] = []

    for new_run in runs:
        matched = False
        for idx, existing in enumerate(deduped):
            is_overlap, _ = are_runs_overlapping(existing, new_run, ft_per_pt)
            if is_overlap:
                matched = True
                if existing.tag == new_run.tag:
                    # Same tag: Merge into single consolidated run
                    # Project both onto existing spine axis to find union span
                    ox, oy, ux, uy = existing.spine.x1, existing.spine.y1, existing.spine.ux, existing.spine.uy
                    t1_a, _ = project_point_to_axis(existing.spine.x1, existing.spine.y1, ox, oy, ux, uy)
                    t1_b, _ = project_point_to_axis(existing.spine.x2, existing.spine.y2, ox, oy, ux, uy)
                    t2_a, _ = project_point_to_axis(new_run.spine.x1, new_run.spine.y1, ox, oy, ux, uy)
                    t2_b, _ = project_point_to_axis(new_run.spine.x2, new_run.spine.y2, ox, oy, ux, uy)

                    union_t_start = min(t1_a, t1_b, t2_a, t2_b)
                    union_t_end = max(t1_a, t1_b, t2_a, t2_b)

                    # Reconstruct merged spine
                    merged_sx1 = ox + union_t_start * ux
                    merged_sy1 = oy + union_t_start * uy
                    merged_sx2 = ox + union_t_end * ux
                    merged_sy2 = oy + union_t_end * uy
                    merged_spine = Segment(x1=merged_sx1, y1=merged_sy1, x2=merged_sx2, y2=merged_sy2)

                    # Merge segments (avoiding duplicates)
                    merged_segments = list(existing.segments)
                    for seg in new_run.segments:
                        if seg not in merged_segments:
                            merged_segments.append(seg)

                    # Merge openings (avoiding duplicates with same t_start)
                    merged_openings = list(existing.openings)
                    for op in new_run.openings:
                        if not any(abs(op.width_pt - e_op.width_pt) < 2.0 and abs(op.t_start - e_op.t_start) < 5.0 for e_op in merged_openings):
                            merged_openings.append(op)

                    gross_pt = merged_spine.length
                    gross_ft = gross_pt * ft_per_pt
                    open_ft = sum(op.width_ft for op in merged_openings)
                    net_ft = max(0.0, gross_ft - open_ft)

                    tag_insts = list(set(existing.tag_instances + new_run.tag_instances))
                    existing.spine = merged_spine
                    existing.gross_length_pt = gross_pt
                    existing.gross_length_ft = gross_ft
                    existing.opening_deduction_ft = open_ft
                    existing.net_length_ft = net_ft
                    existing.segments = merged_segments
                    existing.openings = merged_openings
                    existing.tag_instances = tag_insts

                    # Merge thickness metrics
                    if existing.thickness_measured and new_run.thickness_measured:
                        if existing.thickness_pt is not None and new_run.thickness_pt is not None:
                            avg_pt = (existing.thickness_pt + new_run.thickness_pt) / 2.0
                            existing.thickness_pt = round(avg_pt, 4)
                            existing.thickness_in = round(avg_pt * ft_per_pt * 12.0, 3)
                    elif new_run.thickness_measured:
                        existing.thickness_pt = new_run.thickness_pt
                        existing.thickness_in = new_run.thickness_in
                        existing.thickness_measured = True
                    elif not existing.thickness_measured and existing.thickness_in is None:
                        existing.thickness_in = new_run.thickness_in
                        existing.thickness_pt = new_run.thickness_pt

                    # Merge material layers
                    if not existing.material_layers and new_run.material_layers:
                        existing.material_layers = list(new_run.material_layers)

                    # Height / section callout propagation
                    if new_run.is_height_verified and not existing.is_height_verified:
                        existing.is_height_verified = True
                        existing.height_ft = new_run.height_ft
                        existing.height_source = new_run.height_source
                        existing.section_callout_tag = new_run.section_callout_tag
                    elif existing.section_callout_tag is None and new_run.section_callout_tag is not None:
                        existing.section_callout_tag = new_run.section_callout_tag

                    existing.notes.append(f"Merged duplicate run from {new_run.run_id}")
                else:
                    # Different tag: Flag tag conflict
                    existing.status = "CONFLICT"
                    if new_run.tag not in existing.conflict_tags:
                        existing.conflict_tags.append(new_run.tag)
                    existing.notes.append(
                        f"Overlaps with tag '{new_run.tag}' from {new_run.run_id}"
                    )
                break

        if not matched:
            deduped.append(new_run)

    return deduped
