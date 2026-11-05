"""Enhanced Geometry Topology Correction Engine for Architectural Floor Plans.
Phase 6C: Geometry Topology Correction.
"""
from __future__ import annotations

import math
from typing import Any, Optional
from pydantic import BaseModel, Field

def pt_to_segment_dist(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> tuple[float, float]:
    dx = x2 - x1
    dy = y2 - y1
    l2 = dx*dx + dy*dy
    if l2 == 0:
        return math.hypot(px - x1, py - y1), 0.0
    t = max(0.0, min(1.0, ((px - x1)*dx + (py - y1)*dy) / l2))
    nx = x1 + t * dx
    ny = y1 + t * dy
    return math.hypot(px - nx, py - ny), t

class WallPairing(BaseModel):
    id: str
    line1_id: str
    line2_id: str
    centerline_start: tuple[float, float]
    centerline_end: tuple[float, float]
    length_pt: float
    length_ft: float
    thickness_pt: float
    thickness_in: float
    thickness_type: str  # "INTERIOR_PARTITION_4.5IN", "EXTERIOR_MASONRY_9IN", "UNKNOWN_UNRESOLVED"
    orientation: str  # "HORIZONTAL", "VERTICAL", "ANGLED"
    source_vector_ids: list[str]
    connected_wall_ids: list[str] = Field(default_factory=list)
    host_openings: list[str] = Field(default_factory=list)

class DoorAssembly(BaseModel):
    id: str
    swing_arc_id: str
    leaf_line_id: Optional[str] = None
    hinge_point: tuple[float, float]
    opening_point: tuple[float, float]
    width_in: float
    width_ft: float
    host_wall_id: Optional[str] = None
    position_along_wall_ft: float = 0.0
    source_vector_ids: list[str]
    classification_status: str = "VERIFIED"

class WindowAssembly(BaseModel):
    id: str
    sill_line_ids: list[str]
    start_pt: tuple[float, float]
    end_pt: tuple[float, float]
    width_in: float
    width_ft: float
    sill_lines_count: int
    host_wall_id: Optional[str] = None
    position_along_wall_ft: float = 0.0
    source_vector_ids: list[str]
    classification_status: str = "VERIFIED"

class ValidatedRoom(BaseModel):
    id: str
    name: str
    label_point: tuple[float, float]
    callout_dimensions: str
    callout_area_sqft: float
    boundary_points_pdf: list[list[float]]
    gross_area_sqft: float
    excluded_area_sqft: float
    net_area_sqft: float
    is_enclosed: bool
    enclosure_gap_pt: float
    boundary_wall_ids: list[str]
    is_interior: bool
    classification_status: str

class DimensionAudit(BaseModel):
    id: str
    displayed_text: str
    parsed_ft: float
    measured_pt: float
    measured_ft: float
    relative_error: float
    absolute_error_in: float
    tolerance_relative: float = 0.05
    tolerance_absolute_in: float = 3.5
    validation_status: str

class DrywallWallItem(BaseModel):
    id: str
    description: str
    centerline_lf: float
    clear_height_ft: float = 10.0
    faces: int
    gross_area_sf: float
    opening_deductions_sf: float
    net_area_sf: float
    source_vector_ids: list[str]

class TopologyCorrectionEngine:
    def __init__(self, ft_per_pt: float = 1.0/9.0):
        self.ft_per_pt = ft_per_pt
        self.pt_per_ft = 1.0 / ft_per_pt if ft_per_pt > 0 else 9.0

    def reconstruct_wall_centerlines(self, segments: list[dict[str, Any]]) -> list[WallPairing]:
        """Pair parallel casing strokes into single structural centerlines."""
        pairings: list[WallPairing] = []
        used_indices = set()
        
        cand_lines = []
        for idx, s in enumerate(segments):
            dx = s['p2'][0] - s['p1'][0]
            dy = s['p2'][1] - s['p1'][1]
            length = math.hypot(dx, dy)
            if length >= 12.0:
                angle = math.atan2(dy, dx) % math.pi
                is_h = abs(math.sin(angle)) < 0.06
                is_v = abs(math.cos(angle)) < 0.06
                if is_h or is_v:
                    cand_lines.append((idx, s, length, "HORIZONTAL" if is_h else "VERTICAL"))

        for i, (idx1, s1, len1, ori1) in enumerate(cand_lines):
            if idx1 in used_indices:
                continue
            best_match = None
            best_score = float('inf')
            
            for j in range(i + 1, len(cand_lines)):
                idx2, s2, len2, ori2 = cand_lines[j]
                if idx2 in used_indices or ori1 != ori2:
                    continue
                
                if ori1 == "HORIZONTAL":
                    y1 = (s1['p1'][1] + s1['p2'][1]) / 2.0
                    y2 = (s2['p1'][1] + s2['p2'][1]) / 2.0
                    dist = abs(y2 - y1)
                    x1_min, x1_max = min(s1['p1'][0], s1['p2'][0]), max(s1['p1'][0], s1['p2'][0])
                    x2_min, x2_max = min(s2['p1'][0], s2['p2'][0]), max(s2['p1'][0], s2['p2'][0])
                    overlap = min(x1_max, x2_max) - max(x1_min, x2_min)
                else:
                    x1 = (s1['p1'][0] + s1['p2'][0]) / 2.0
                    x2 = (s2['p1'][0] + s2['p2'][0]) / 2.0
                    dist = abs(x2 - x1)
                    y1_min, y1_max = min(s1['p1'][1], s1['p2'][1]), max(s1['p1'][1], s1['p2'][1])
                    y2_min, y2_max = min(s2['p1'][1], s2['p2'][1]), max(s2['p1'][1], s2['p2'][1])
                    overlap = min(y1_max, y2_max) - max(y1_min, y2_min)
                
                if 2.5 <= dist <= 14.0 and overlap > 10.0:
                    score = abs(dist - 4.4) if dist < 6.0 else abs(dist - 8.9)
                    if score < best_score:
                        best_score = score
                        best_match = (idx2, s2, dist, overlap, ori1)

            if best_match:
                idx2, s2, dist, overlap, ori = best_match
                used_indices.add(idx1)
                used_indices.add(idx2)
                
                thickness_in = dist * (12.0 / self.pt_per_ft)
                if dist < 6.0:
                    ttype = "INTERIOR_PARTITION_4.5IN"
                elif dist <= 12.0:
                    ttype = "EXTERIOR_MASONRY_9IN"
                else:
                    ttype = "UNKNOWN_UNRESOLVED"
                
                if ori == "HORIZONTAL":
                    yc = ((s1['p1'][1] + s1['p2'][1]) / 2.0 + (s2['p1'][1] + s2['p2'][1]) / 2.0) / 2.0
                    x_start = min(s1['p1'][0], s1['p2'][0], s2['p1'][0], s2['p2'][0])
                    x_end = max(s1['p1'][0], s1['p2'][0], s2['p1'][0], s2['p2'][0])
                    c_start = (x_start, yc)
                    c_end = (x_end, yc)
                    c_len = x_end - x_start
                else:
                    xc = ((s1['p1'][0] + s1['p2'][0]) / 2.0 + (s2['p1'][0] + s2['p2'][0]) / 2.0) / 2.0
                    y_start = min(s1['p1'][1], s1['p2'][1], s2['p1'][1], s2['p2'][1])
                    y_end = max(s1['p1'][1], s1['p2'][1], s2['p1'][1], s2['p2'][1])
                    c_start = (xc, y_start)
                    c_end = (xc, y_end)
                    c_len = y_end - y_start
                
                pairings.append(
                    WallPairing(
                        id=f"WALL-CL-{len(pairings)+1:03d}",
                        line1_id=s1.get('id', f"VEC-{idx1}"),
                        line2_id=s2.get('id', f"VEC-{idx2}"),
                        centerline_start=c_start,
                        centerline_end=c_end,
                        length_pt=round(c_len, 2),
                        length_ft=round(c_len * self.ft_per_pt, 2),
                        thickness_pt=round(dist, 2),
                        thickness_in=round(thickness_in, 1),
                        thickness_type=ttype,
                        orientation=ori,
                        source_vector_ids=[s1.get('id', f"VEC-{idx1}"), s2.get('id', f"VEC-{idx2}")]
                    )
                )

        # Build wall-to-wall connectivity
        for w1 in pairings:
            for w2 in pairings:
                if w1.id == w2.id:
                    continue
                # Check endpoint proximity within 3.0 pt
                p1_starts = [w1.centerline_start, w1.centerline_end]
                p2_starts = [w2.centerline_start, w2.centerline_end]
                connected = False
                for p_a in p1_starts:
                    for p_b in p2_starts:
                        if math.hypot(p_a[0] - p_b[0], p_a[1] - p_b[1]) < 3.5:
                            connected = True
                            break
                    if connected:
                        break
                # Also check T-junction (endpoint of w1 touches w2 line)
                if not connected:
                    for p_a in p1_starts:
                        d, t = pt_to_segment_dist(p_a[0], p_a[1], w2.centerline_start[0], w2.centerline_start[1], w2.centerline_end[0], w2.centerline_end[1])
                        if d < 3.5:
                            connected = True
                            break
                if connected and w2.id not in w1.connected_wall_ids:
                    w1.connected_wall_ids.append(w2.id)

        return pairings

    def reconstruct_doors(self, arcs: list[dict[str, Any]], walls: list[WallPairing]) -> list[DoorAssembly]:
        """Identifies door swing assemblies and associates with host walls."""
        doors: list[DoorAssembly] = []
        for idx, a in enumerate(arcs):
            p1 = a['p1']
            p4 = a['p4']
            chord_pt = math.hypot(p4[0] - p1[0], p4[1] - p1[1])
            if 18.0 <= chord_pt <= 45.0:
                width_ft = chord_pt * self.ft_per_pt
                width_in = width_ft * 12.0
                
                # Find host wall via point-to-segment distance
                host_wall = None
                best_pos_ft = 0.0
                min_wall_dist = float('inf')
                for w in walls:
                    d1, t1 = pt_to_segment_dist(p1[0], p1[1], w.centerline_start[0], w.centerline_start[1], w.centerline_end[0], w.centerline_end[1])
                    d4, t4 = pt_to_segment_dist(p4[0], p4[1], w.centerline_start[0], w.centerline_start[1], w.centerline_end[0], w.centerline_end[1])
                    m_dist = min(d1, d4)
                    if m_dist < min_wall_dist and m_dist < 20.0:
                        min_wall_dist = m_dist
                        host_wall = w.id
                        best_pos_ft = (t1 if d1 < d4 else t4) * w.length_ft
                        
                door_id = f"DOOR-ASM-{len(doors)+1:03d}"
                if host_wall:
                    # Link to wall host_openings
                    for w in walls:
                        if w.id == host_wall:
                            w.host_openings.append(door_id)
                            break
                            
                doors.append(
                    DoorAssembly(
                        id=door_id,
                        swing_arc_id=a.get('id', f"ARC-{idx}"),
                        hinge_point=p1,
                        opening_point=p4,
                        width_in=round(width_in, 1),
                        width_ft=round(width_ft, 2),
                        host_wall_id=host_wall,
                        position_along_wall_ft=round(best_pos_ft, 2),
                        source_vector_ids=[a.get('id', f"ARC-{idx}")],
                        classification_status="VERIFIED"
                    )
                )
        return doors

    def reconstruct_windows(self, lines: list[dict[str, Any]], walls: list[WallPairing]) -> list[WindowAssembly]:
        """Detects multi-line parallel window sill assemblies."""
        windows: list[WindowAssembly] = []
        h_sills = []
        v_sills = []
        for l in lines:
            dx = l['p2'][0] - l['p1'][0]
            dy = l['p2'][1] - l['p1'][1]
            length = math.hypot(dx, dy)
            if 18.0 <= length <= 75.0:
                if abs(dy) < 0.5:
                    h_sills.append((l, min(l['p1'][0], l['p2'][0]), max(l['p1'][0], l['p2'][0]), (l['p1'][1] + l['p2'][1])/2.0))
                elif abs(dx) < 0.5:
                    v_sills.append((l, min(l['p1'][1], l['p2'][1]), max(l['p1'][1], l['p2'][1]), (l['p1'][0] + l['p2'][0])/2.0))

        h_clusters = []
        for l, x0, x1, y in h_sills:
            matched = False
            for c in h_clusters:
                if abs(c['y'] - y) < 8.0 and abs(c['x0'] - x0) < 5.0 and abs(c['x1'] - x1) < 5.0:
                    c['lines'].append(l)
                    matched = True
                    break
            if not matched:
                h_clusters.append({'x0': x0, 'x1': x1, 'y': y, 'lines': [l]})

        v_clusters = []
        for l, y0, y1, x in v_sills:
            matched = False
            for c in v_clusters:
                if abs(c['x'] - x) < 8.0 and abs(c['y0'] - y0) < 5.0 and abs(c['y1'] - y1) < 5.0:
                    c['lines'].append(l)
                    matched = True
                    break
            if not matched:
                v_clusters.append({'y0': y0, 'y1': y1, 'x': x, 'lines': [l]})

        for c in h_clusters:
            if len(c['lines']) >= 3:
                w_pt = c['x1'] - c['x0']
                w_ft = w_pt * self.ft_per_pt
                mid_x = (c['x0'] + c['x1']) / 2.0
                host_wall = None
                best_pos_ft = 0.0
                min_d = float('inf')
                for w in walls:
                    d, t = pt_to_segment_dist(mid_x, c['y'], w.centerline_start[0], w.centerline_start[1], w.centerline_end[0], w.centerline_end[1])
                    if d < min_d and d < 18.0:
                        min_d = d
                        host_wall = w.id
                        best_pos_ft = t * w.length_ft
                
                win_id = f"WIN-ASM-{len(windows)+1:03d}"
                if host_wall:
                    for w in walls:
                        if w.id == host_wall:
                            w.host_openings.append(win_id)
                            break
                            
                windows.append(
                    WindowAssembly(
                        id=win_id,
                        sill_line_ids=[li.get('id', 'LINE') for li in c['lines']],
                        start_pt=(c['x0'], c['y']),
                        end_pt=(c['x1'], c['y']),
                        width_in=round(w_ft * 12.0, 1),
                        width_ft=round(w_ft, 2),
                        sill_lines_count=len(c['lines']),
                        host_wall_id=host_wall,
                        position_along_wall_ft=round(best_pos_ft, 2),
                        source_vector_ids=[li.get('id', 'LINE') for li in c['lines']],
                        classification_status="VERIFIED"
                    )
                )

        for c in v_clusters:
            if len(c['lines']) >= 3:
                w_pt = c['y1'] - c['y0']
                w_ft = w_pt * self.ft_per_pt
                mid_y = (c['y0'] + c['y1']) / 2.0
                host_wall = None
                best_pos_ft = 0.0
                min_d = float('inf')
                for w in walls:
                    d, t = pt_to_segment_dist(c['x'], mid_y, w.centerline_start[0], w.centerline_start[1], w.centerline_end[0], w.centerline_end[1])
                    if d < min_d and d < 18.0:
                        min_d = d
                        host_wall = w.id
                        best_pos_ft = t * w.length_ft
                        
                win_id = f"WIN-ASM-{len(windows)+1:03d}"
                if host_wall:
                    for w in walls:
                        if w.id == host_wall:
                            w.host_openings.append(win_id)
                            break

                windows.append(
                    WindowAssembly(
                        id=win_id,
                        sill_line_ids=[li.get('id', 'LINE') for li in c['lines']],
                        start_pt=(c['x'], c['y0']),
                        end_pt=(c['x'], c['y1']),
                        width_in=round(w_ft * 12.0, 1),
                        width_ft=round(w_ft, 2),
                        sill_lines_count=len(c['lines']),
                        host_wall_id=host_wall,
                        position_along_wall_ft=round(best_pos_ft, 2),
                        source_vector_ids=[li.get('id', 'LINE') for li in c['lines']],
                        classification_status="VERIFIED"
                    )
                )

        return windows

    def audit_dimensions(self, dims: list[tuple[str, float, float]]) -> list[DimensionAudit]:
        """Dual-tolerance dimension audit (relative + absolute)."""
        audits = []
        for idx, (txt, parsed_ft, meas_pt) in enumerate(dims):
            meas_ft = meas_pt * self.ft_per_pt
            abs_err_in = abs(meas_ft - parsed_ft) * 12.0
            rel_err = abs(meas_ft - parsed_ft) / parsed_ft if parsed_ft > 0 else 0.0
            
            is_verified = (rel_err <= 0.05) and (abs_err_in <= 3.5)
            audits.append(
                DimensionAudit(
                    id=f"DIM-AUDIT-{idx+1:03d}",
                    displayed_text=txt,
                    parsed_ft=parsed_ft,
                    measured_pt=round(meas_pt, 2),
                    measured_ft=round(meas_ft, 3),
                    relative_error=round(rel_err, 4),
                    absolute_error_in=round(abs_err_in, 2),
                    tolerance_relative=0.05,
                    tolerance_absolute_in=3.5,
                    validation_status="VERIFIED" if is_verified else "REVIEW_REQUIRED"
                )
            )
        return audits
