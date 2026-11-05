"""
qto.quantities: Mathematical Takeoff Engine adhering to SOP 4.1-4.10, 8.7, and 8.7.1.

Computes:
- Gross Linear Footage (LF)
- Opening Deductions (LF)
- Net Linear Footage (LF)
- Net Gypsum Board Area (SF) per face and layer: A_board = (L_gross * H - sum(w_i * h_i)) * faces * layers
- Segmented Stud Counts: N = sum(ceil(len_k * 12 / S) + 1) + extra_studs
- Stud Linear Footage: LF = N * H
- Metal Runner Track LF: L_gross (top) + L_net (bottom)
- Wood Plates LF: 2 * L_gross (double top) + L_net (single bottom)
- Consumables: Fasteners, Joint Tape, Joint Compound, Corner Beads, Acoustic Sealant
- Strict 0% Default Waste Policy (with separate waste multiplier)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from qto.dedup import WallRun
from qto.openings import Opening


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class QtoLine:
    """Individual line item in the drywall quantity takeoff (SOP 8.8)."""
    line_id: str
    tag: str
    item: str
    quantity: float
    unit: str
    formula: str
    inputs: str
    wall_run_ids: List[str]
    status: str = "OK"
    assumptions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "line_id": self.line_id,
            "tag": self.tag,
            "item": self.item,
            "quantity": round(self.quantity, 2),
            "unit": self.unit,
            "formula": self.formula,
            "inputs": self.inputs,
            "wall_run_ids": self.wall_run_ids,
            "status": self.status,
            "assumptions": self.assumptions,
        }


@dataclass
class TagTakeoffSummary:
    """Consolidated takeoff metrics for a single partition wall type tag."""
    tag: str
    description: str = ""
    runs_count: int = 0
    gross_lf: float = 0.0
    opening_deduction_lf: float = 0.0
    net_lf: float = 0.0
    height_ft: float = 10.0
    height_source: str = "HEIGHT_DEFAULT_ASSUMED"
    faces: int = 2
    layers_per_face: int = 1
    net_board_sf: float = 0.0
    studs_ea: int = 0
    stud_lf: float = 0.0
    track_lf: float = 0.0
    plates_lf: float = 0.0
    status: str = "OK"
    assumptions_count: int = 0
    stud_material: str = "Metal"
    stud_spacing_in: int = 16
    board_type: str = "Type X"
    board_thickness_in: str = "5/8\""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tag": self.tag,
            "description": self.description,
            "runs_count": self.runs_count,
            "gross_lf": round(self.gross_lf, 2),
            "opening_deduction_lf": round(self.opening_deduction_lf, 2),
            "net_lf": round(self.net_lf, 2),
            "height_ft": round(self.height_ft, 2),
            "height_source": self.height_source,
            "faces": self.faces,
            "layers_per_face": self.layers_per_face,
            "net_board_sf": round(self.net_board_sf, 2),
            "studs_ea": self.studs_ea,
            "stud_lf": round(self.stud_lf, 2),
            "track_lf": round(self.track_lf, 2),
            "plates_lf": round(self.plates_lf, 2),
            "status": self.status,
            "assumptions_count": self.assumptions_count,
            "stud_material": self.stud_material,
            "stud_spacing_in": self.stud_spacing_in,
            "board_type": self.board_type,
            "board_thickness_in": self.board_thickness_in,
        }


@dataclass
class TakeoffResult:
    """Complete quantity takeoff result adhering to SOP 8.7 and 8.8."""
    runs: List[WallRun]
    openings: List[Opening]
    by_tag: Dict[str, TagTakeoffSummary]
    lines: List[QtoLine]
    total_gross_lf: float
    total_opening_deduction_lf: float
    total_net_lf: float
    total_board_sf: float
    total_studs_ea: int
    total_stud_lf: float
    total_track_lf: float
    total_plates_lf: float
    consumables: Dict[str, float]
    assumptions: List[Dict[str, Any]]
    review_items: List[Dict[str, Any]]
    waste_percent: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_gross_lf": round(self.total_gross_lf, 2),
            "total_opening_deduction_lf": round(self.total_opening_deduction_lf, 2),
            "total_net_lf": round(self.total_net_lf, 2),
            "total_board_sf": round(self.total_board_sf, 2),
            "total_studs_ea": self.total_studs_ea,
            "total_stud_lf": round(self.total_stud_lf, 2),
            "total_track_lf": round(self.total_track_lf, 2),
            "total_plates_lf": round(self.total_plates_lf, 2),
            "consumables": self.consumables,
            "waste_percent": self.waste_percent,
            "by_tag": {k: v.to_dict() for k, v in self.by_tag.items()},
            "lines": [line.to_dict() for line in self.lines],
            "runs": [r.to_dict() for r in self.runs],
            "openings": [op.to_dict() for op in self.openings],
            "assumptions": self.assumptions,
            "review_items": self.review_items,
        }


# =============================================================================
# PURE MATHEMATICAL FUNCTIONS (SOP 4.1-4.10, 8.7.1)
# =============================================================================

def calculate_gross_lf(length_pt: float, ft_per_pt: float) -> float:
    """SOP 4.1 & 8.7: L_gross = length_pt * ft_per_pt."""
    return round(length_pt * ft_per_pt, 2)


def calculate_net_lf(gross_lf: float, opening_widths_ft: List[float]) -> float:
    """SOP 4.2 & 8.7: L_net = max(0.0, L_gross - sum(w_i))."""
    open_lf = sum(opening_widths_ft)
    return round(max(0.0, gross_lf - open_lf), 2)


def calculate_board_area(
    gross_lf: float,
    height_ft: float,
    openings: List[Tuple[float, float]],
    faces: int = 2,
    layers_per_face: int = 1,
) -> float:
    """
    SOP 4.3 & 8.7: A_board = (L_gross * H - sum(w_i * h_i)) * (faces * layers_per_face).
    openings is a list of (width_ft, height_ft).
    """
    wall_gross_surface = gross_lf * height_ft
    openings_area = sum(w * h for w, h in openings)
    net_surface = max(0.0, wall_gross_surface - openings_area)
    total_layers = faces * layers_per_face
    return round(net_surface * total_layers, 2)


def calculate_stud_count(
    segment_lengths_ft: List[float],
    stud_spacing_in: int = 16,
    extra_studs_per_opening: int = 0,
) -> int:
    """
    SOP 4.4 & 8.7.1: N = sum(ceil(len_k * 12 / S) + 1) + extra_studs.
    Computes exact segmented stud counts across straight physical wall spans between openings.
    """
    if not segment_lengths_ft:
        return 0
    total = 0
    for length_ft in segment_lengths_ft:
        if length_ft <= 0.0:
            continue
        studs_in_seg = math.ceil((length_ft * 12.0) / stud_spacing_in) + 1
        total += studs_in_seg
    total += extra_studs_per_opening
    return total if total > 0 else 1


def calculate_track_lf(gross_lf: float, net_lf: float) -> float:
    """SOP 4.5 & 8.7: Metal track LF = L_gross (top continuous) + L_net (bottom cut at openings)."""
    return round(gross_lf + net_lf, 2)


def calculate_plates_lf(gross_lf: float, net_lf: float) -> float:
    """SOP 4.5 & 8.7: Wood plates LF = 2 * L_gross (double top plate) + L_net (single bottom plate)."""
    return round(2.0 * gross_lf + net_lf, 2)


def calculate_consumables(
    board_sf: float,
    wall_gross_lf: float,
    height_ft: float = 10.0,
) -> Dict[str, float]:
    """
    SOP 4.6-4.9: Fasteners, joint tape, compound, corner beads, and acoustic sealant.
    - Fasteners: ~1 screw per SF of board
    - Joint tape: ~0.38 LF per SF (380 LF per 1,000 SF)
    - Joint compound: ~0.0095 gal per SF (9.5 gal per 1,000 SF)
    - Acoustic sealant: 4 continuous beads (top and bottom on both sides) -> 4 * L_gross
    """
    return {
        "fasteners_ea": round(board_sf * 1.0, 0),
        "joint_tape_lf": round(board_sf * 0.38, 2),
        "joint_compound_gal": round(board_sf * 0.0095, 3),
        "acoustic_sealant_lf": round(wall_gross_lf * 4.0, 2),
        "corner_beads_lf": 0.0,
    }


def split_run_into_segments(run: WallRun, ft_per_pt: float) -> List[float]:
    """
    Splits a WallRun into continuous wall segment lengths (ft) separated by openings.
    If no openings exist, returns a single segment with net_length_ft.
    """
    if not run.openings:
        return [run.net_length_ft]

    # Local axis spans along wall run
    # Opening spans along primary face
    sorted_ops = sorted(run.openings, key=lambda op: op.t_start)
    segments = []
    curr_t = min(run.spine.x1, run.spine.x2)  # reference start or 0.0
    # In run geometry, t is relative to ox:
    # Use opening t_start and t_end relative to traced primary face
    prev_t = sorted_ops[0].t_start - (sorted_ops[0].t_start - min(sorted_ops[0].t_start, 0.0))
    # Approximate segment lengths based on opening widths and run gross length
    # If run has exact openings:
    total_open_lf = sum(op.width_ft for op in sorted_ops)
    net_lf = max(0.0, run.gross_length_ft - total_open_lf)

    # For standard doors (like worked example 8.7.1), if door divides run in equal parts:
    # We compute physical spans from opening.t_start and t_end
    spans_ft = []
    # If opening provides exact t_start and t_end:
    # Segment before first opening
    t_run_start = getattr(run, "t_start", 0.0)
    t_run_end = getattr(run, "t_end", run.gross_length_pt)

    # First segment
    first_seg_len = (sorted_ops[0].t_start - t_run_start) * ft_per_pt
    if first_seg_len > 0.1:
        spans_ft.append(round(first_seg_len, 2))

    # Intermediate segments between openings
    for i in range(len(sorted_ops) - 1):
        inter_len = (sorted_ops[i + 1].t_start - sorted_ops[i].t_end) * ft_per_pt
        if inter_len > 0.1:
            spans_ft.append(round(inter_len, 2))

    # Last segment after final opening
    last_seg_len = (t_run_end - sorted_ops[-1].t_end) * ft_per_pt
    if last_seg_len > 0.1:
        spans_ft.append(round(last_seg_len, 2))

    if not spans_ft:
        # Fallback to dividing remaining net length evenly
        count = len(sorted_ops) + 1
        seg_len = round(net_lf / count, 2)
        spans_ft = [seg_len] * count

    return spans_ft


# =============================================================================
# MAIN ORCHESTRATION FUNCTION
# =============================================================================

def calculate_takeoff(
    runs: List[WallRun],
    openings: Optional[List[Opening]] = None,
    scale_ft_per_pt: float = 0.111111,
    default_height_ft: float = 10.0,
    stud_spacing_in: int = 16,
    waste_percent: float = 0.0,
    assembly_attributes: Optional[Dict[str, Dict[str, Any]]] = None,
    scale_status: Optional[str] = None,
    extra_review_items: Optional[List[Dict[str, Any]]] = None,
) -> TakeoffResult:
    """
    Computes complete drywall quantity takeoff across all wall runs.
    Enforces exact SOP 8.7 formulas and strict 0% default waste policy.
    """
    assembly_attributes = assembly_attributes or {}
    all_openings = openings if openings is not None else []
    if openings is None:
        for r in runs:
            all_openings.extend(r.openings)

    # Waste multiplier: SOP 4.12
    waste_multiplier = 1.0 + (waste_percent / 100.0 if waste_percent > 1.0 else waste_percent)

    by_tag: Dict[str, TagTakeoffSummary] = {}
    lines: List[QtoLine] = []
    assumptions: List[Dict[str, Any]] = []
    review_items: List[Dict[str, Any]] = []

    unverified_tags = sorted(list({r.tag for r in runs if not getattr(r, "is_height_verified", False)}))
    unverified_affected = f"Tags: {', '.join(unverified_tags)}" if unverified_tags else "All default height runs"

    # Record baseline assumptions
    assumptions.append({
        "assumption_id": "ASSUMP-01",
        "category": "Wall Height",
        "parameter": "default_height_ft",
        "default_value_used": f"{default_height_ft:.2f}'",
        "justification": "SOP 8.7 default partition height when elevation/section text is unspecified",
        "affected_runs": unverified_affected,
    })
    assumptions.append({
        "assumption_id": "ASSUMP-02",
        "category": "Waste Allowance",
        "parameter": "waste_percent",
        "default_value_used": f"{waste_percent:.1f}%",
        "justification": "SOP 4.12 strict 0% default waste policy for baseline quantity takeoff",
        "affected_runs": "All runs",
    })
    if scale_status == "DEFAULT_ASSUMED":
        assumptions.append({
            "assumption_id": f"ASSUMP-{len(assumptions)+1:02d}",
            "category": "Architectural Scale",
            "parameter": "scale_string",
            "default_value_used": "1/8\" = 1'-0\" (ASSUMED)",
            "justification": "Drawing lacked scale notes; dependent quantities flagged QTY_BLOCKED for estimator review",
            "affected_runs": "All runs",
            "status": "QTY_BLOCKED",
        })

    total_gross_lf = 0.0
    total_open_lf = 0.0
    total_net_lf = 0.0
    total_board_sf = 0.0
    total_studs_ea = 0
    total_stud_lf = 0.0
    total_track_lf = 0.0
    total_plates_lf = 0.0

    line_counter = 1

    for run in runs:
        tag = run.tag
        attrs = assembly_attributes.get(tag, {})

        # Height priority: run override -> assembly attribute -> default_height_ft
        run_height = getattr(run, "height_ft", None)
        run_height_src = getattr(run, "height_source", None)
        if run_height is not None and run_height > 0:
            height_ft = float(run_height)
            if run_height_src and run_height_src != "UNVERIFIED_HEIGHT_DEFAULT":
                height_source = run_height_src
            elif getattr(run, "is_manual", False):
                height_source = "ESTIMATOR_OVERRIDE"
            elif run_height_src:
                height_source = run_height_src
            else:
                height_source = "HEIGHT_RUN_SPECIFIED"
        else:
            height_ft = float(attrs.get("height_ft", default_height_ft))
            height_source = attrs.get("height_source", "HEIGHT_DEFAULT_ASSUMED")

        # Framing attributes
        spacing = int(attrs.get("stud_spacing_in", stud_spacing_in))
        layers = int(attrs.get("layers_per_face", 1))
        faces = int(attrs.get("finished_faces", 2))
        material = attrs.get("stud_material", "Metal")
        board_type = attrs.get("board_type", "Type X")
        board_thick = attrs.get("board_thickness_in", "5/8\"")
        desc = attrs.get("description", f"{material} Stud Partition Tag {tag}")

        # Linear footage
        gross_lf = run.gross_length_ft
        open_lf = run.opening_deduction_ft
        net_lf = run.net_length_ft

        # Openings on this run
        op_tuples = [(op.width_ft, op.height_ft) for op in run.openings]
        board_sf = calculate_board_area(gross_lf, height_ft, op_tuples, faces=faces, layers_per_face=layers)

        # Stud count across segments
        run_scale = getattr(run, "ft_per_pt", None) or scale_ft_per_pt
        segments_ft = split_run_into_segments(run, run_scale)
        studs_ea = calculate_stud_count(segments_ft, stud_spacing_in=spacing)
        stud_lf = round(studs_ea * height_ft, 2)

        # Track and plates
        track_lf = calculate_track_lf(gross_lf, net_lf)
        plates_lf = calculate_plates_lf(gross_lf, net_lf)

        # Accumulate totals
        total_gross_lf += gross_lf
        total_open_lf += open_lf
        total_net_lf += net_lf
        total_board_sf += board_sf
        total_studs_ea += studs_ea
        total_stud_lf += stud_lf
        total_track_lf += track_lf
        total_plates_lf += plates_lf

        # Check for review items
        if run.status == "CONFLICT":
            review_items.append({
                "review_id": f"REV-{run.run_id}",
                "category": "Tag Conflict",
                "page": run.page_num,
                "sheet": run.sheet_label,
                "target_id": run.run_id,
                "description": f"Overlaps with conflict tags: {run.conflict_tags}",
                "measured_values": f"Gross: {gross_lf:.2f} LF",
                "required_action": "Estimator must confirm tag assignment",
            })

        # Rollup by tag
        if tag not in by_tag:
            by_tag[tag] = TagTakeoffSummary(
                tag=tag,
                description=desc,
                height_ft=height_ft,
                height_source=height_source,
                faces=faces,
                layers_per_face=layers,
                stud_material=material,
                stud_spacing_in=spacing,
                board_type=board_type,
                board_thickness_in=board_thick,
                status=run.status,
            )

        tag_summary = by_tag[tag]
        tag_summary.runs_count += 1
        if getattr(run, "is_height_verified", False):
            tag_summary.height_ft = height_ft
            tag_summary.height_source = height_source
        if run.status == "REVIEW" and tag_summary.status == "OK":
            tag_summary.status = "REVIEW"
        tag_summary.gross_lf += gross_lf
        tag_summary.opening_deduction_lf += open_lf
        tag_summary.net_lf += net_lf
        tag_summary.net_board_sf += board_sf
        tag_summary.studs_ea += studs_ea
        tag_summary.stud_lf += stud_lf
        tag_summary.track_lf += track_lf
        tag_summary.plates_lf += plates_lf
        if run.status != "OK" and tag_summary.status != "REVIEW":
            tag_summary.status = run.status

    # Generate QTO Line items (SOP 8.8)
    for tag, t_sum in by_tag.items():
        # Line 1: Gypsum board
        lines.append(QtoLine(
            line_id=f"LINE-{line_counter:03d}",
            tag=tag,
            item=f"Gypsum Board ({t_sum.board_type} {t_sum.board_thickness_in})",
            quantity=t_sum.net_board_sf,
            unit="SF",
            formula="(L_gross * H - A_open) * faces * layers",
            inputs=f"L_gross={t_sum.gross_lf:.2f}, H={t_sum.height_ft:.2f}, faces={t_sum.faces}, layers={t_sum.layers_per_face}",
            wall_run_ids=[r.run_id for r in runs if r.tag == tag],
            status=t_sum.status,
        ))
        line_counter += 1

        # Line 2: Studs
        lines.append(QtoLine(
            line_id=f"LINE-{line_counter:03d}",
            tag=tag,
            item=f"{t_sum.stud_material} Studs @ {t_sum.stud_spacing_in}\" O.C.",
            quantity=float(t_sum.studs_ea),
            unit="EA",
            formula="sum(ceil(len_k * 12 / S) + 1)",
            inputs=f"spacing={t_sum.stud_spacing_in}\", runs={t_sum.runs_count}",
            wall_run_ids=[r.run_id for r in runs if r.tag == tag],
            status=t_sum.status,
        ))
        line_counter += 1

        # Line 3: Stud Linear Footage
        lines.append(QtoLine(
            line_id=f"LINE-{line_counter:03d}",
            tag=tag,
            item=f"{t_sum.stud_material} Stud Length",
            quantity=t_sum.stud_lf,
            unit="LF",
            formula="N * H",
            inputs=f"N={t_sum.studs_ea}, H={t_sum.height_ft:.2f}",
            wall_run_ids=[r.run_id for r in runs if r.tag == tag],
            status=t_sum.status,
        ))
        line_counter += 1

        # Line 4: Track or plates
        if "wood" in t_sum.stud_material.lower():
            lines.append(QtoLine(
                line_id=f"LINE-{line_counter:03d}",
                tag=tag,
                item="Wood Plates (Double Top + Single Bottom)",
                quantity=t_sum.plates_lf,
                unit="LF",
                formula="2 * L_gross + L_net",
                inputs=f"L_gross={t_sum.gross_lf:.2f}, L_net={t_sum.net_lf:.2f}",
                wall_run_ids=[r.run_id for r in runs if r.tag == tag],
                status=t_sum.status,
            ))
        else:
            lines.append(QtoLine(
                line_id=f"LINE-{line_counter:03d}",
                tag=tag,
                item="Metal Runner Track (Top continuous + Bottom cut)",
                quantity=t_sum.track_lf,
                unit="LF",
                formula="L_gross + L_net",
                inputs=f"L_gross={t_sum.gross_lf:.2f}, L_net={t_sum.net_lf:.2f}",
                wall_run_ids=[r.run_id for r in runs if r.tag == tag],
                status=t_sum.status,
            ))
        line_counter += 1

    # Aggregate extra review items (e.g. from S13B height verification)
    if extra_review_items:
        for rev in extra_review_items:
            review_items.append(rev)

    # Ensure any REVIEW status wall run is logged in review_items
    logged_targets = {r.get("target_id") or r.get("run_id") for r in review_items}
    for r in runs:
        if r.status == "REVIEW" and r.run_id not in logged_targets:
            issue_msg = r.notes[0] if r.notes else f"Unverified wall height for Tag {r.tag}: No section callout found on floor plan. Using standard {default_height_ft:.1f} ft fallback."
            review_items.append({
                "run_id": r.run_id,
                "target_id": r.run_id,
                "review_id": f"REV-HGT-{r.run_id}",
                "tag": r.tag,
                "page": r.page_num,
                "sheet": r.sheet_label,
                "category": "Unverified Wall Height",
                "issue": issue_msg,
                "description": issue_msg,
                "action_required": "Estimator review required to confirm wall height against architectural elevations.",
                "required_action": "Estimator review required to confirm wall height against architectural elevations.",
                "measured_values": f"Default Height: {getattr(r, 'height_ft', default_height_ft) or default_height_ft:.2f} ft | Gross: {r.gross_length_ft:.2f} LF",
            })
            logged_targets.add(r.run_id)

    # Consumables calculation across total board area and gross LF
    consumables = calculate_consumables(total_board_sf, total_gross_lf, default_height_ft)

    return TakeoffResult(
        runs=runs,
        openings=all_openings,
        by_tag=by_tag,
        lines=lines,
        total_gross_lf=round(total_gross_lf, 2),
        total_opening_deduction_lf=round(total_open_lf, 2),
        total_net_lf=round(total_net_lf, 2),
        total_board_sf=round(total_board_sf, 2),
        total_studs_ea=total_studs_ea,
        total_stud_lf=round(total_stud_lf, 2),
        total_track_lf=round(total_track_lf, 2),
        total_plates_lf=round(total_plates_lf, 2),
        consumables=consumables,
        assumptions=assumptions,
        review_items=review_items,
        waste_percent=waste_percent,
    )
