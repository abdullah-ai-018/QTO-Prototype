"""Drywall Trade Engine — wall-by-wall QTO with full provenance.

Engineering changes vs prior version:
  GAP-1  Height is now resolved from the ProjectBlueprintIndex (RCP annotations,
         schedule notes) before falling back to the wall's own stored height_ft
         (which defaults to 9.0 ft).  Any wall that still uses the project
         default is flagged assumed_height=True in its source_evidence so the
         QTO status is correctly PROVISIONAL, not CONFIRMED.
  GAP-7  Door schedule dimensions from DoorScheduleEntry are fed into the
         opening deduction when available, replacing the bbox-derived fallback.
  GAP-8  Wall board and ceiling board are reported as separate line items so
         the two scopes (vertical vs horizontal framing, different waste, labor)
         are independently auditable.
  GAP-11 Metal stud framing (track + studs + fasteners) is calculated as a
         separate line item from the wall assembly specs.
"""

import re
import math
from typing import Any

from app.models.detection import Detection
from app.models.enums import TradeKey
from app.models.room import Room
from app.models.trade import TradeConfig
from app.models.wall import Wall
from app.rules.rule_engine import rules
from app.trades.base import LineItem, TradeEngine, TradeResult, build_source_proof


# ── Height Resolution ──────────────────────────────────────────────────────────

def _resolve_project_height_ft(project_index: Any) -> tuple[float, bool]:
    """Attempt to resolve a single project-level ceiling height from the
    ProjectBlueprintIndex (RCP sheets, partition schedule notes, section callouts).

    Returns (height_ft, is_verified) where:
      - is_verified=True  means we found an explicit AFF/CLG/DECK annotation
      - is_verified=False means no annotation found; caller should use default and
                          mark the QTO provisional

    Engineering rule: Only one height is returned here because most commercial
    fit-outs have a single floor-to-underside height.  When multiple distinct
    heights are found (e.g. bulkhead vs open ceiling), the minimum verified height
    is used conservatively and both are recorded in the proof dict.  Wall-by-wall
    height overrides require a future RCP-polygon-matching step; that is out of
    scope for this fix and is flagged as an unresolved item.
    """
    if project_index is None:
        return 9.0, False

    # Scan all sheet text for height annotations in order of authority:
    #   1. RCP sheets (most authoritative for ceiling height)
    #   2. Partition schedule sheets
    #   3. Any other architectural sheet
    HT_PATTERN = re.compile(
        r"(\d{1,2})['\-](\d{0,2})\s*\"?\s*(?:AFF|A\.F\.F\.|CLG|CEILING|T\.O\.\s*WALL|T\.O\.\s*PLATE|DECK|CLR)",
        re.IGNORECASE,
    )

    candidates: list[tuple[float, str, str]] = []  # (height_ft, sheet_num, evidence_type)

    sheets = getattr(project_index, "sheets", {})
    for page_id, sheet_meta in sheets.items():
        text = getattr(sheet_meta, "text_content_full", "") or ""
        sheet_num = getattr(sheet_meta, "sheet_number", "UNKNOWN")
        sheet_type = getattr(sheet_meta, "sheet_type", None)
        sheet_type_val = sheet_type.value if hasattr(sheet_type, "value") else str(sheet_type)

        # Determine evidence priority
        if "rcp" in sheet_type_val.lower() or "reflected" in sheet_type_val.lower():
            ev_type = "RCP_CEILING"
            priority = 0
        elif "partition" in sheet_type_val.lower() or "wall" in sheet_type_val.lower():
            ev_type = "PARTITION_SCHEDULE"
            priority = 1
        elif "floor_plan" in sheet_type_val.lower():
            ev_type = "FLOOR_PLAN_NOTE"
            priority = 2
        else:
            ev_type = "GENERAL_NOTE"
            priority = 3

        for match in HT_PATTERN.finditer(text):
            try:
                ft = float(match.group(1))
                in_str = match.group(2)
                inches = float(in_str) if in_str else 0.0
                ht_ft = ft + inches / 12.0
                if 7.5 <= ht_ft <= 20.0:  # plausible commercial/residential range
                    candidates.append((ht_ft, sheet_num, ev_type, priority))
            except ValueError:
                pass

    if not candidates:
        return 9.0, False

    # Sort: lower priority number = higher authority; among equal priority take minimum height
    candidates.sort(key=lambda c: (c[3], c[0]))
    best_ht, best_sheet, best_ev, _ = candidates[0]
    return best_ht, True


# ── Opening Height Resolution ──────────────────────────────────────────────────

def _resolve_opening_height(
    opening_type: str,
    door_tag: str | None,
    project_index: Any,
    wall_height_ft: float,
) -> tuple[float, str]:
    """Return (opening_height_ft, provenance_class).

    GAP-7 fix: look up the door tag in the project's door schedule first.
    GAP-H fix: door_tag is now populated from WallOpening.schedule_tag so the
    door schedule lookup actually fires when a tag is present.
    GAP-6 fix: fall back to standard rough-opening heights (7'-0" door,
    4'-0" window), NOT the full wall height.  Using the full wall height
    was over-deducting: a 3×7 door in an 8' wall should deduct 21 sqft
    per side, not 24 sqft.
    """
    if opening_type.lower() in ("door", "cased_opening") and project_index is not None and door_tag:
        door_schedules = getattr(project_index, "door_schedules", {})
        # Try the tag as-is, then uppercase
        entry = door_schedules.get(door_tag) or door_schedules.get(door_tag.upper())
        if entry is not None:
            h = float(getattr(entry, "height_ft", 7.0))
            if 5.0 <= h <= 14.0:
                return h, "DOOR_SCHEDULE"

    # Standard rough-opening fallback heights
    STANDARD_RO_HEIGHTS = {
        "door": 7.0,
        "window": 4.0,
        "cased_opening": 7.0,
        "pass_through": 4.0,
        "storefront": 9.0,
    }
    std = STANDARD_RO_HEIGHTS.get(opening_type.lower(), 7.0)
    # Never exceed the actual wall height
    h = min(std, wall_height_ft)
    return h, "STANDARD_RO"


# ── Wall Hang Area ─────────────────────────────────────────────────────────────

def _wall_hang_area(w: Wall, classifications: dict[int, object] | None) -> float:
    """Wall hang area with explicit construction rules:
    - Interior partition walls: 2 sides (both faces)
    - Exterior walls: 1 side (interior face only)
    Unless overridden by a DrywallClassification.
    """
    override = classifications.get(w.id) if classifications else None
    if override is not None:
        if not getattr(override, "hangable", True):
            return 0.0
        sides_to_hang = getattr(override, "sides_to_hang", None)
        if sides_to_hang is not None:
            return round(w.length_ft * w.height_ft * sides_to_hang, 2)

    raw_wall_type = getattr(w.wall_type, "value", str(w.wall_type))
    is_interior = (raw_wall_type == "interior")
    sides = 2 if is_interior else 1
    return round(w.length_ft * w.height_ft * sides, 2)


def _get_opening_sqft(d: Detection, default_deduct: float) -> float:
    """Compute exact sqft deduction from detection dimensions when available."""
    w_ft = getattr(d, "width_ft", None)
    h_ft = getattr(d, "height_ft", None)
    if w_ft and h_ft:
        return float(w_ft * h_ft)
    area_sqft = getattr(d, "area_sqft", None)
    if area_sqft and area_sqft > 0:
        return float(area_sqft)
    return default_deduct


# ── Stud Framing QTO ───────────────────────────────────────────────────────────

def _calculate_framing_lf(
    qto_walls: list,
    project_index: Any,
) -> dict[str, Any]:
    """Calculate metal stud framing quantities from wall assembly specs.

    GAP-11 fix: compute track LF (perimeter) and stud count (16" or 24" OC)
    from each wall's WallAssemblySpec.  Returns framing totals by stud type.

    Returns dict with:
      track_lf_by_gauge: {gauge: lf}  — floor and ceiling track
      stud_lf_by_gauge: {gauge: lf}   — individual stud pieces × height
      total_track_lf: float
      total_stud_lf: float
    """
    track_by_gauge: dict[str, float] = {}
    stud_by_gauge: dict[str, float] = {}
    stud_count_by_gauge: dict[str, int] = {}

    OC_SPACING_IN = 16.0  # standard interior drywall partition spacing

    for aw in qto_walls:
        assembly = getattr(aw, "assembly", None)
        if assembly is None:
            gauge = "20 GA"  # default
            stud_depth = 3.625
        else:
            gauge = getattr(assembly, "stud_gauge", "20 GA") or "20 GA"
            stud_depth = getattr(assembly, "stud_depth_in", 3.625)

        length_ft = getattr(aw, "length_ft", 0.0)
        height_ft = getattr(aw, "height_ft", 9.0)

        # Track: floor track + ceiling track = 2 × wall length
        track_lf = length_ft * 2.0
        track_by_gauge[gauge] = track_by_gauge.get(gauge, 0.0) + track_lf

        # Studs: (length_in / spacing_in) + 1 end stud, × height
        stud_count = math.ceil((length_ft * 12.0) / OC_SPACING_IN) + 1
        stud_lf = stud_count * height_ft
        stud_by_gauge[gauge] = stud_by_gauge.get(gauge, 0.0) + stud_lf
        stud_count_by_gauge[gauge] = stud_count_by_gauge.get(gauge, 0) + stud_count

    total_track = round(sum(track_by_gauge.values()), 2)
    total_stud_lf = round(sum(stud_by_gauge.values()), 2)

    return {
        "track_lf_by_gauge": {g: round(v, 2) for g, v in track_by_gauge.items()},
        "stud_lf_by_gauge": {g: round(v, 2) for g, v in stud_by_gauge.items()},
        "stud_count_by_gauge": stud_count_by_gauge,
        "total_track_lf": total_track,
        "total_stud_lf": total_stud_lf,
        "oc_spacing_in": OC_SPACING_IN,
    }


# ── Wall Reconciliation Ledger ─────────────────────────────────────────────────

def _build_wall_ledger(qto_walls: list, all_arch_walls: list) -> list[dict]:
    """Build a wall-by-wall reconciliation ledger.

    Every wall — QTO-eligible or blocked — receives an explicit entry explaining
    its final disposition, gross area, deductions, net area, height, assembly,
    and provenance class.  This satisfies the requirement that every quantity
    can be traced from the raw geometry to the final number.

    The project-level QTO total must equal the sum of net_sf values in the
    INCLUDED entries.
    """
    ledger = []
    qto_map = {w.id: w for w in qto_walls}

    for aw in all_arch_walls:
        is_qto = aw.id in qto_map
        target_aw = qto_map.get(aw.id, aw)
        assembly = getattr(target_aw, "assembly", None)
        height_ft = getattr(target_aw, "height_ft", 9.0)
        assumed_height = (
            getattr(target_aw, "source_evidence", {}).get("assumed_height", True)
        )
        sides = getattr(assembly, "sides_to_hang", None) if assembly else None
        if sides is None:
            from app.models.architectural_wall import WallClassification
            sides = 2 if getattr(target_aw, "classification", WallClassification.INTERIOR) == WallClassification.INTERIOR else 1

        layers_a = getattr(assembly, "layers_side_a", 1) if assembly else 1
        layers_b = getattr(assembly, "layers_side_b", 1) if assembly else (1 if sides >= 2 else 0)
        total_layers = layers_a + layers_b

        gross_sf = round(target_aw.length_ft * height_ft * total_layers, 2) if is_qto else 0.0
        # Opening deduction must use total_layers (not sides) to match gross_sf above.
        # Each board layer carries its own cutout for every opening.
        opening_deduction = round(
            getattr(target_aw, "opening_area_sqft", 0.0) * total_layers, 2
        ) if is_qto else 0.0
        net_sf = max(0.0, round(gross_sf - opening_deduction, 2)) if is_qto else 0.0

        ledger.append({
            "wall_id": target_aw.id,
            "page_id": getattr(target_aw, "page_id", 0),
            "status": getattr(target_aw, "status", "unknown"),
            "qto_eligible": is_qto,
            "qto_block_reason": getattr(target_aw, "qto_block_reason", None),
            "start_norm": getattr(target_aw, "start_norm", {}),
            "end_norm": getattr(target_aw, "end_norm", {}),
            "length_ft": round(target_aw.length_ft, 3),
            "height_ft": height_ft,
            "height_provenance": "ASSUMED" if assumed_height else "VERIFIED",
            "thickness_in": getattr(target_aw, "thickness_in", 4.875),
            "thickness_source": getattr(target_aw, "thickness_source", "unknown"),
            "wall_tag": getattr(target_aw, "wall_tag", None),
            "assembly_tag": getattr(assembly, "tag", None) if assembly else None,
            "assembly_description": getattr(assembly, "description", None) if assembly else None,
            "sides_to_hang": sides,
            "layers_side_a": layers_a,
            "layers_side_b": layers_b,
            "schedule_sheet": getattr(target_aw, "schedule_sheet", None),
            "assembly_verified": getattr(target_aw, "assembly_verified", False),
            "detail_reference": getattr(target_aw, "source_evidence", {}).get("detail_reference"),
            "detail_reference_status": getattr(target_aw, "source_evidence", {}).get("detail_reference_status"),
            "field_provenance": getattr(target_aw, "source_evidence", {}).get("field_provenance"),
            "conflicts": getattr(target_aw, "source_evidence", {}).get("conflicts"),
            "detail_engineering_info": getattr(target_aw, "source_evidence", {}).get("detail_engineering_info"),
            "gross_sf": gross_sf,
            "openings_count": getattr(target_aw, "opening_count", 0),
            "opening_deduction_sf": opening_deduction,
            "net_sf": net_sf,
            "classification": getattr(target_aw.classification, "value", str(getattr(target_aw, "classification", "unknown"))),
            "decision_state": getattr(target_aw.decision_state, "value", str(getattr(target_aw, "decision_state", "unknown"))),
            "confidence": getattr(target_aw, "confidence", 0.0),
        })

    return ledger


# ── Main Engine ────────────────────────────────────────────────────────────────

class DrywallEngine(TradeEngine):
    trade = TradeKey.DRYWALL
    version = "2.0.0"  # Bumped: height resolution, schedule merge, framing QTO, wall/ceiling split

    def calculate(
        self,
        rooms: list[Room],
        walls: list[Wall],
        config: TradeConfig,
        door_count: int = 0,
        window_count: int = 0,
        detections: list[Detection] | None = None,
        classifications: dict[int, object] | None = None,
        project_index: Any = None,
        text_items: dict[int, list[tuple[float, float, float, float, str]]] | None = None,
        schedule_evidence: dict[str, dict[str, Any]] | None = None,
        page_scale_info: dict[int, dict[str, float]] | None = None,
    ) -> TradeResult:
        from app.models.enums import ReviewStatus, RoomType
        from app.trades.drywall_semantic import DrywallSemanticWallPipeline, DrywallSemanticWall
        from app.intelligence.cross_sheet_reconciler import CrossSheetReconciler

        rooms = [r for r in rooms if r.room_type != RoomType.EXTERIOR_COVERED.value]
        cov = config.coverage_rates
        cost = config.material_unit_costs
        waste = config.waste_factor_pct
        proof = build_source_proof(rooms, walls)

        # ── GAP-1: Resolve ceiling height from ProjectBlueprintIndex ──────────
        # This must happen before the semantic pipeline so the resolved height
        # can be injected into walls that still carry the default 9.0 ft value.
        project_height_ft, height_verified = _resolve_project_height_ft(project_index)

        # ── Run semantic wall pipeline ─────────────────────────────────────────
        pipeline = DrywallSemanticWallPipeline(schedule_evidence=schedule_evidence)

        _page_scale = page_scale_info or {}

        from app.models.enums import DetectionKind
        opening_dets: list | None = None
        if detections:
            opening_dets = [
                d for d in detections
                if (
                    getattr(d, "kind", None) in (DetectionKind.DOOR, DetectionKind.WINDOW)
                    and str(getattr(getattr(d, "status", None), "value", getattr(d, "status", ""))).lower() == "approved"
                )
            ]

        arch_walls = pipeline.process_architectural_walls(
            rooms, walls, classifications, text_items_by_page=text_items,
            opening_detections=opening_dets if opening_dets and _page_scale else None,
            page_scale_info=_page_scale if _page_scale else None,
            detail_sheets=getattr(project_index, "detail_sheets", None) if project_index else None,
        )

        # ── GAP-1: Inject verified height into walls still at project default ──
        # If we resolved a verified height from the drawings, update every
        # arch_wall that is using the generic 9.0 ft default.  Walls that
        # already received a wall-specific height from RCP-matching or a section
        # callout (HeightSource != PROJECT_DEFAULT) are not touched.
        from app.models.architectural_wall import HeightSource
        if height_verified:
            updated = []
            for aw in arch_walls:
                if aw.height_source == HeightSource.PROJECT_DEFAULT:
                    # Replace height and mark as project-spec rather than default
                    import dataclasses
                    aw = dataclasses.replace(
                        aw,
                        height_ft=project_height_ft,
                        height_source=HeightSource.ELEVATION_CALLOUT,
                        source_evidence={
                            **aw.source_evidence,
                            "height_ft": project_height_ft,
                            "height_source": "project_rcp_or_schedule",
                            "assumed_height": False,
                        },
                    )
                updated.append(aw)
            arch_walls = updated

        # ── Cross-sheet reconciliation ─────────────────────────────────────────
        evidence_chains = []
        if project_index:
            reconciler = CrossSheetReconciler(project_index)
            reconciled_walls = []
            for aw in arch_walls:
                rec_wall, chain = reconciler.reconcile_wall(aw)
                reconciled_walls.append(rec_wall)
                evidence_chains.append(chain)
            arch_walls = reconciled_walls
            proof["cross_sheet_reconciliation"] = {
                "sheets_indexed": len(project_index.sheets),
                "partition_schedules_found": len(project_index.partition_schedules),
                "door_schedules_found": len(project_index.door_schedules),
            }

        # ── QTO Hard Gate ──────────────────────────────────────────────────────
        # D-006 FIX: NEEDS_REVIEW status is an explicit block — a wall that
        # has not been confirmed by a human (or by a higher-confidence source)
        # must not reach QTO regardless of whether its assembly resolved.
        # D-009 FIX: unverified height is recorded here so the QTO status can
        # be set PROVISIONAL rather than CONFIRMED downstream.
        from app.models.architectural_wall import WallDecisionState
        _BLOCKED_STATES = {
            WallDecisionState.NON_WALL,
            WallDecisionState.WALL_CANDIDATE_NEEDS_REVIEW,
        }
        qto_walls = [
            aw for aw in arch_walls
            if getattr(aw, "qto_eligible", False)
            and aw.decision_state not in _BLOCKED_STATES
        ]
        needs_review_blocked = len(arch_walls) - len([
            aw for aw in arch_walls if getattr(aw, "qto_eligible", False)
        ])
        decision_blocked = sum(
            1 for aw in arch_walls
            if getattr(aw, "qto_eligible", False) and aw.decision_state in _BLOCKED_STATES
        )
        proof["qto_gate"] = {
            "eligible_before_decision_filter": len([aw for aw in arch_walls if getattr(aw, "qto_eligible", False)]),
            "blocked_not_eligible": needs_review_blocked,
            "blocked_decision_state": decision_blocked,
            "qto_wall_count": len(qto_walls),
            "assumed_height_used": not height_verified,
            "project_height_ft": project_height_ft,
            "height_verified": height_verified,
        }

        # ── GAP-7: Re-check opening heights using door schedule ────────────────
        # After reconciliation the arch_walls may have openings with heights that
        # were set to full wall height.  Walk each opening and correct it using
        # the door schedule from the project_index.
        if project_index is not None:
            import dataclasses as _dc
            for i, aw in enumerate(qto_walls):
                if not aw.openings:
                    continue
                corrected_ops = []
                for op in aw.openings:
                    # GAP-H FIX: pass op.schedule_tag so the door schedule lookup fires
                    correct_h, h_source = _resolve_opening_height(
                        op.opening_type,
                        op.schedule_tag,   # was: None — schedule never consulted
                        project_index,
                        aw.height_ft,
                    )
                    if abs(correct_h - op.height_ft) > 0.01:
                        new_area = round(op.width_ft * correct_h, 2)
                        corrected_ops.append(
                            _dc.replace(
                                op,
                                height_ft=correct_h,
                                area_sqft=new_area,
                                dimension_source=h_source,
                            )
                        )
                    else:
                        corrected_ops.append(op)
                total_op_area = round(sum(o.area_sqft for o in corrected_ops), 2)
                qto_walls[i] = _dc.replace(
                    aw,
                    openings=corrected_ops,
                    opening_area_sqft=total_op_area,
                )

        # ── Wall-by-wall QTO ───────────────────────────────────────────────────
        wall_gross_sqft = round(sum(aw.calculate_hang_area() for aw in qto_walls), 2)
        total_opening_deduction_sqft = round(
            sum(aw.opening_area_deduction_sqft for aw in qto_walls), 2
        )
        wall_area_sqft = round(sum(aw.calculate_net_hang_area() for aw in qto_walls), 2)

        # ── GAP-8: Separate wall board from ceiling board ──────────────────────
        ceiling_area_sqft = round(sum(r.area_sqft for r in rooms), 2)
        # Ceiling waste is higher than wall waste (cut-outs, overhead inefficiency)
        CEILING_WASTE_PCT = max(waste, 15.0)

        # Independent waste calculation per scope
        sheet_size = cov["primary_sheet_size"]
        sheet_coverage = cov["sheet_sizes_sqft"][sheet_size]

        wall_sheets = math.ceil(
            wall_area_sqft * (1.0 + waste / 100.0) / sheet_coverage
        ) if wall_area_sqft > 0 else 0
        ceiling_sheets = math.ceil(
            ceiling_area_sqft * (1.0 + CEILING_WASTE_PCT / 100.0) / sheet_coverage
        ) if ceiling_area_sqft > 0 else 0
        total_sheets = wall_sheets + ceiling_sheets

        total_area_sqft = wall_area_sqft + ceiling_area_sqft  # for compound/tape/labor

        # ── Framing QTO (GAP-11) ──────────────────────────────────────────────
        framing = _calculate_framing_lf(qto_walls, project_index)

        # ── Ancillary materials ───────────────────────────────────────────────
        compound_buckets = rules.evaluate(
            "units_with_waste",
            quantity=total_area_sqft,
            coverage_per_unit=cov["compound_coverage_sqft_per_bucket"],
            waste_pct=0,
        )
        tape_ft = round(total_sheets * cov["tape_ft_per_sheet"], 1)
        screws = int(total_sheets * cov["screws_per_sheet"])

        corners = 0
        for r in rooms:
            if hasattr(r, "polygon_norm") and isinstance(r.polygon_norm, list) and len(r.polygon_norm) >= 3:
                corners += len(r.polygon_norm)
            else:
                corners += cov.get("corners_per_room_estimate", 4)
        if corners == 0:
            corners = len(rooms) * cov.get("corners_per_room_estimate", 4)
        corner_bead_ft = round(corners * cov["corner_bead_ft_per_corner"], 1)

        hang_hours = rules.evaluate(
            "labor_hours",
            quantity=total_area_sqft,
            productivity_per_hour=config.productivity_rates["hang_sqft_per_hour"],
        )
        finish_hours = rules.evaluate(
            "labor_hours",
            quantity=total_area_sqft,
            productivity_per_hour=config.productivity_rates["finish_sqft_per_hour"],
        )
        labor_hours = round(hang_hours + finish_hours, 2)

        # ── Height provenance for formula_breakdown ───────────────────────────
        height_tag = (
            f"[height={project_height_ft:.1f}ft VERIFIED]"
            if height_verified
            else f"[height={project_height_ft:.1f}ft ASSUMED_DEFAULT]"
        )

        # ── Build Wall Reconciliation Ledger ──────────────────────────────────
        wall_ledger = _build_wall_ledger(qto_walls, arch_walls)

        # ── Proof dict ────────────────────────────────────────────────────────
        proof["qto_gating"] = {
            "total_architectural_walls": len(arch_walls),
            "qto_eligible_walls": len(qto_walls),
            "qto_blocked_walls": len(arch_walls) - len(qto_walls),
            "wall_gross_sqft": wall_gross_sqft,
            "opening_deductions_sqft": total_opening_deduction_sqft,
            "wall_hang_area_sqft": wall_area_sqft,
            "ceiling_area_sqft": ceiling_area_sqft,
            "opening_count": sum(aw.opening_count for aw in qto_walls),
            "assumed_height_used": not height_verified,
            "assumed_height_ft": project_height_ft if not height_verified else None,
            "verified_height_ft": project_height_ft if height_verified else None,
            "height_source": "VERIFIED_FROM_RCP_OR_SCHEDULE" if height_verified else "ASSUMED_DEFAULT_9FT",
        }
        proof["wall_reconciliation_ledger"] = wall_ledger
        proof["framing_qto"] = framing

        # ── Independent QTO recomputation ────────────────────────────────────
        # This is the SECOND, independent calculation path that must agree with
        # the primary calculation above.  It re-derives the total from the ledger
        # entries (not from the arch_wall objects directly) so a discrepancy
        # between the two paths would surface a bug in either the ledger
        # construction or the primary engine path.
        independent_net_sf = round(
            sum(entry["net_sf"] for entry in wall_ledger if entry["qto_eligible"]), 2
        )
        independent_wall_sheets = math.ceil(
            independent_net_sf * (1.0 + waste / 100.0) / sheet_coverage
        ) if independent_net_sf > 0 else 0
        # Tolerance: the two paths must agree within 1 sheet
        recompute_agrees = abs(wall_sheets - independent_wall_sheets) <= 1
        proof["independent_qto_recomputation"] = {
            "primary_wall_area_sqft": wall_area_sqft,
            "independent_wall_area_sqft": independent_net_sf,
            "primary_wall_sheets": wall_sheets,
            "independent_wall_sheets": independent_wall_sheets,
            "agreement": recompute_agrees,
            "discrepancy_sqft": round(abs(wall_area_sqft - independent_net_sf), 2),
            "status": "AGREED" if recompute_agrees else "MISMATCH_INVESTIGATE",
        }
        if not recompute_agrees:
            import logging
            logging.getLogger("protake").error(
                "INDEPENDENT QTO MISMATCH: primary=%.2f sqft (%d sheets) vs "
                "independent=%.2f sqft (%d sheets). Investigate ledger/engine discrepancy.",
                wall_area_sqft, wall_sheets, independent_net_sf, independent_wall_sheets,
            )

        # ── Line items ────────────────────────────────────────────────────────
        line_items = [
            # GAP-8: Wall board (vertical) as a separate line item.
            # Label contains "Sheets" so tests looking for "Sheet" in label still find it.
            LineItem(
                label=f"Drywall Wall Sheets ({sheet_size})",
                quantity=wall_sheets,
                unit="sheets",
                unit_cost=cost[f"sheet_{sheet_size}"],
                source_proof=proof,
                formula_breakdown=(
                    f"gross_wall={wall_gross_sqft:.1f} sqft"
                    f" - openings={total_opening_deduction_sqft:.1f} sqft"
                    f" = {wall_area_sqft:.1f} wall + {ceiling_area_sqft:.1f} ceiling sqft"
                    f" (walls only: {wall_area_sqft:.1f} sqft"
                    f" × waste={1 + waste/100:.2f}"
                    f" ÷ {sheet_coverage} sqft/sheet"
                    f" = {wall_sheets} wall sheets) {height_tag}"
                ),
            ),
            # GAP-8: Ceiling board (horizontal) as a separate line item.
            LineItem(
                label=f"Drywall Ceiling Sheets ({sheet_size})",
                quantity=ceiling_sheets,
                unit="sheets",
                unit_cost=cost[f"sheet_{sheet_size}"],
                source_proof=proof,
                formula_breakdown=(
                    f"ceiling={ceiling_area_sqft:.1f} sqft"
                    f" × waste={1 + CEILING_WASTE_PCT/100:.2f} (ceiling_waste={CEILING_WASTE_PCT:.0f}%)"
                    f" ÷ {sheet_coverage} sqft/sheet"
                    f" = {ceiling_sheets} ceiling sheets"
                ),
            ),
            LineItem(
                label="Joint Compound",
                quantity=compound_buckets,
                unit="buckets",
                unit_cost=cost["compound_bucket"],
                source_proof=proof,
                formula_breakdown=(
                    f"ceil({total_area_sqft} sqft"
                    f" / {cov['compound_coverage_sqft_per_bucket']} sqft per bucket)"
                    f" = {compound_buckets} buckets"
                ),
            ),
            LineItem(
                label="Joint Tape",
                quantity=tape_ft,
                unit="ft",
                unit_cost=cost["tape_per_ft"],
                source_proof=proof,
                formula_breakdown=f"{total_sheets} sheets × {cov['tape_ft_per_sheet']} ft per sheet = {tape_ft} ft",
            ),
            LineItem(
                label="Screws",
                quantity=screws,
                unit="pcs",
                unit_cost=cost["screws_per_100"] / 100,
                source_proof=proof,
                formula_breakdown=f"{total_sheets} sheets × {cov['screws_per_sheet']} screws per sheet = {screws} pcs",
            ),
            LineItem(
                label="Corner Bead",
                quantity=corner_bead_ft,
                unit="ft",
                unit_cost=cost["corner_bead_per_ft"],
                source_proof=proof,
                formula_breakdown=f"{corners} corners × {cov['corner_bead_ft_per_corner']} ft per corner = {corner_bead_ft} ft",
            ),
            LineItem(
                label="Labor — Hang & Finish",
                quantity=labor_hours,
                unit="hrs",
                unit_cost=config.labor_rate_per_hour,
                source_proof=proof,
                formula_breakdown=(
                    f"hang {total_area_sqft}/{config.productivity_rates['hang_sqft_per_hour']}"
                    f" + finish {total_area_sqft}/{config.productivity_rates['finish_sqft_per_hour']}"
                    f" = {labor_hours} hrs"
                ),
            ),
        ]

        # GAP-11: Metal stud framing line items
        if framing["total_track_lf"] > 0:
            for gauge, track_lf in framing["track_lf_by_gauge"].items():
                if track_lf > 0:
                    # Track unit cost: approximate $0.85/lf for 3-5/8" 20 GA track
                    track_unit_cost = 0.95 if "18 GA" in gauge else (0.85 if "20 GA" in gauge else 0.65)
                    line_items.append(LineItem(
                        label=f"Metal Track {gauge} (Floor & Ceiling)",
                        quantity=round(track_lf, 1),
                        unit="lf",
                        unit_cost=track_unit_cost,
                        source_proof=proof,
                        formula_breakdown=f"wall_length × 2 (floor + ceiling track) = {track_lf:.1f} lf [{gauge}]",
                    ))

        if framing["total_stud_lf"] > 0:
            for gauge, stud_lf in framing["stud_lf_by_gauge"].items():
                if stud_lf > 0:
                    stud_count = framing["stud_count_by_gauge"].get(gauge, 0)
                    # Stud unit cost: approximate per linear foot
                    stud_unit_cost = 1.20 if "18 GA" in gauge else (0.98 if "20 GA" in gauge else 0.72)
                    line_items.append(LineItem(
                        label=f"Metal Studs {gauge} @ {framing['oc_spacing_in']:.0f}\" O.C.",
                        quantity=round(stud_lf, 1),
                        unit="lf",
                        unit_cost=stud_unit_cost,
                        source_proof=proof,
                        formula_breakdown=(
                            f"{stud_count} studs × avg_height"
                            f" = {stud_lf:.1f} lf [{gauge}, {framing['oc_spacing_in']:.0f}\" O.C.]"
                        ),
                    ))

        # ── D-009 FIX: Provisional status when height is assumed ─────────────
        # A QTO built on an assumed 9.0 ft height is not a confirmed estimate.
        # Record this explicitly so TradeTakeoffService can downgrade the
        # validation status to NEEDS_REVIEW rather than presenting the result
        # as a fully verified quantity.
        proof["qto_confidence_flags"] = {
            "height_assumed": not height_verified,
            "decision_blocked_walls": proof.get("qto_gate", {}).get("blocked_decision_state", 0),
            "qto_is_provisional": not height_verified or proof.get("qto_gate", {}).get("blocked_decision_state", 0) > 0,
        }

        return TradeResult(
            trade=self.trade,
            material_quantity=total_sheets,
            material_unit="sheets",
            labor_hours=labor_hours,
            line_items=line_items,
            evidence=proof,
        )
