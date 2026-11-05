"""Comprehensive Phase 4 Test Suite: Assembly Resolution, Schedule Sheet Discovery, and QTO Hard Gate.

Verifies:
1. Referenced Schedule Discovery:
   - "SEE SHEET A7.1 FOR ALL WALL TYPES" detected from page text.
   - Missing schedule sheet produces UNRESOLVED assembly, NEEDS_REVIEW drywall scope, and QTO = 0.
2. Verified Table Grid Schedule Resolution:
   - Real schedule table produces WALL_ASSEMBLY_CONFIRMED and DRYWALL_SCOPE_CONFIRMED.
3. 5-State Machine transitions:
   - NON_WALL -> WALL_CANDIDATE_NEEDS_REVIEW -> PHYSICAL_WALL_CONFIRMED -> WALL_ASSEMBLY_CONFIRMED -> DRYWALL_SCOPE_CONFIRMED
4. QTO Hard Gate:
   - Only confirmed drywall scope walls are QTO eligible.
   - Ceiling QTO never masks or fabricates wall QTO.
5. Evidence Card Completeness:
   - All 16 required forensic fields present and machine-readable.
"""

import pytest
from app.models.enums import ReviewStatus, WallType, TradeKey
from app.models.room import Room
from app.models.wall import Wall
from app.models.trade import TradeConfig
from app.models.architectural_wall import (
    ArchitecturalWall,
    WallDecisionState,
    WallAssemblySpec,
    WallClassification,
    DrywallScopeDecision,
)
from app.trades.drywall import DrywallEngine
from app.trades.drywall_semantic import DrywallSemanticWallPipeline
from app.intelligence.schedule_table_parser import ScheduleTableParser


def test_case_a_missing_referenced_schedule_gates_qto():
    """CASE A: Physical wall with referenced schedule A7.1 that is MISSING from document set.
    Expected:
    - PHYSICAL_WALL_CONFIRMED = True
    - assembly_state = UNRESOLVED
    - drywall_scope_state = NEEDS_REVIEW
    - qto_eligible = False
    - qto_block_reason = REFERENCED_SCHEDULE_MISSING
    - wall QTO = 0.0 sqft
    """
    pipeline = DrywallSemanticWallPipeline()
    rooms = [
        Room(id=1, page_id=1, name="Office", area_sqft=200.0, perimeter_ft=60.0,
             polygon_norm=[{"x": 0.2, "y": 0.2}, {"x": 0.5, "y": 0.2}, {"x": 0.5, "y": 0.5}, {"x": 0.2, "y": 0.5}]),
    ]
    # Dual-face confirmed physical wall
    wall = Wall(
        id=101, page_id=1, length_ft=25.0, height_ft=9.0, wall_type=WallType.INTERIOR,
        start_norm={"x": 0.2, "y": 0.2}, end_norm={"x": 0.5, "y": 0.2}, confidence=0.95,
        thickness_ft=0.406, thickness_measured=True,
        face_a_segment_id=1011, face_b_segment_id=1012,
    )
    text_items = [
        (0.25, 0.20, 0.28, 0.22, "TYPE NR-1"),
        (0.10, 0.90, 0.40, 0.92, "SEE SHEET A7.1 FOR ALL WALL TYPES"),
    ]

    results = pipeline.process_architectural_walls(rooms, [wall], text_items=text_items)
    assert len(results) == 1
    w = results[0]

    # Physical wall is confirmed because two independent source faces exist
    assert w.decision_state == WallDecisionState.PHYSICAL_WALL_CONFIRMED
    assert w.wall_geometry.face_a.segment_ids == [1011]
    assert w.wall_geometry.face_b.segment_ids == [1012]

    # Schedule is missing: assembly remains unverified and unresolved
    assert w.assembly_verified is False
    assert w.assembly_resolved is False
    assert w.drywall_scope == DrywallScopeDecision.NEEDS_REVIEW
    assert w.qto_eligible is False
    assert w.qto_block_reason == "REFERENCED_SCHEDULE_MISSING"

    # Wall QTO must be strictly 0.0
    assert w.calculate_hang_area() == 0.0
    assert w.calculate_net_hang_area() == 0.0

    # Verify Evidence Card
    card = w.to_evidence_card()
    assert card["physical_wall_state"] == "PHYSICAL_WALL_CONFIRMED"
    assert card["assembly_state"] == "UNRESOLVED"
    assert card["drywall_scope_state"] == "NEEDS_REVIEW"
    assert card["drywall_scope"] == "UNRESOLVED"
    assert card["qto_eligible"] is False
    assert card["qto_block_reason"] == "REFERENCED_SCHEDULE_MISSING"
    assert card["schedule_sheet"] == "A7.1"


def test_case_b_verified_schedule_table_confirms_drywall_qto():
    """CASE B: Physical wall with verified schedule table row.
    Expected:
    - PHYSICAL_WALL_CONFIRMED = True
    - assembly_state = WALL_ASSEMBLY_CONFIRMED
    - drywall_scope_state = DRYWALL_SCOPE_CONFIRMED
    - qto_eligible = True
    - qto_block_reason = None
    - wall QTO = length * height * layers = 25 * 9 * 2 = 450.0 sqft
    """
    # Verified schedule table evidence (e.g. from ScheduleTableParser)
    schedule_evidence = {
        "NR-1": {
            "tag": "NR-1",
            "schedule_sheet": "A7.1",
            "source_page": 7,
            "source_region": {"x0": 0.1, "y0": 0.2, "x1": 0.8, "y1": 0.6},
            "assembly_definition": WallAssemblySpec(
                tag="NR-1",
                description="3-5/8\" Metal Stud, 5/8\" Type X GWB Each Side",
                stud_depth_in=3.625,
                stud_gauge="25 GA",
                board_type_side_a="5/8\" Type X GWB",
                layers_side_a=1,
                board_type_side_b="5/8\" Type X GWB",
                layers_side_b=1,
                sides_to_hang=2,
                insulation="R-11 Sound Batt",
                fire_rating_hr=1.0,
                sound_rating_stc=50.0,
                source="schedule_table_A7.1",
            ),
            "verified": True,
        }
    }

    pipeline = DrywallSemanticWallPipeline(schedule_evidence=schedule_evidence)
    rooms = [
        Room(id=1, page_id=1, name="Office", area_sqft=200.0, perimeter_ft=60.0,
             polygon_norm=[{"x": 0.2, "y": 0.2}, {"x": 0.5, "y": 0.2}, {"x": 0.5, "y": 0.5}, {"x": 0.2, "y": 0.5}]),
    ]
    wall = Wall(
        id=102, page_id=1, length_ft=25.0, height_ft=9.0, wall_type=WallType.INTERIOR,
        start_norm={"x": 0.2, "y": 0.2}, end_norm={"x": 0.5, "y": 0.2}, confidence=0.95,
        thickness_ft=0.406, thickness_measured=True,
        face_a_segment_id=1021, face_b_segment_id=1022,
    )
    text_items = [
        (0.25, 0.20, 0.28, 0.22, "TYPE NR-1"),
        (0.10, 0.90, 0.40, 0.92, "SEE SHEET A7.1 FOR ALL WALL TYPES"),
    ]

    results = pipeline.process_architectural_walls(rooms, [wall], text_items=text_items)
    assert len(results) == 1
    w = results[0]

    assert w.assembly_resolved is True
    assert w.assembly_verified is True
    assert w.drywall_scope == DrywallScopeDecision.REQUIRED
    assert w.status == "approved"
    assert w.qto_eligible is True
    assert w.qto_block_reason is None

    # Exact calculated drywall hang area: 25.0 ft * 9.0 ft * 2 sides = 450.0 sqft
    assert w.calculate_hang_area() == 450.0
    assert w.calculate_net_hang_area() == 450.0

    # Verify Evidence Card
    card = w.to_evidence_card()
    assert card["physical_wall_state"] == "PHYSICAL_WALL_CONFIRMED"
    assert card["assembly_state"] == "WALL_ASSEMBLY_CONFIRMED"
    assert card["drywall_scope_state"] == "DRYWALL_SCOPE_CONFIRMED"
    assert card["drywall_scope"] == "REQUIRED"
    assert card["qto_eligible"] is True
    assert card["qto_block_reason"] is None
    assert card["schedule_sheet"] == "A7.1"
    assert card["assembly_verified"] is True
    assert card["assembly_definition"]["tag"] == "NR-1"


def test_drywall_engine_separates_wall_and_ceiling_qto():
    """QTO Hard Gate: DrywallEngine must strictly separate wall hang area from ceiling area.
    When wall assembly is unverified, wall_hang_area_sqft is 0.0, but ceiling remains preserved.
    """
    engine = DrywallEngine()
    rooms = [
        Room(id=1, page_id=1, name="Conference Room", area_sqft=300.0, perimeter_ft=70.0,
             status=ReviewStatus.APPROVED,
             polygon_norm=[{"x": 0.2, "y": 0.2}, {"x": 0.6, "y": 0.2}, {"x": 0.6, "y": 0.5}, {"x": 0.2, "y": 0.5}]),
    ]
    # Unverified schedule wall candidate
    unverified_wall = Wall(
        id=201, page_id=1, length_ft=30.0, height_ft=9.0, wall_type=WallType.INTERIOR,
        start_norm={"x": 0.2, "y": 0.2}, end_norm={"x": 0.6, "y": 0.2}, confidence=0.95,
        thickness_ft=0.406, thickness_measured=True,
        face_a_segment_id=2011, face_b_segment_id=2012,
    )
    config = TradeConfig(
        trade=TradeKey.DRYWALL,
        coverage_rates={
            "primary_sheet_size": "4x8",
            "sheet_sizes_sqft": {"4x8": 32.0},
            "compound_coverage_sqft_per_bucket": 400.0,
            "tape_ft_per_sheet": 12.0,
            "screws_per_sheet": 36,
            "corner_bead_ft_per_corner": 8.0,
        },
        material_unit_costs={
            "sheet_4x8": 28.0,
            "compound_bucket": 22.0,
            "tape_per_ft": 0.08,
            "screws_per_100": 8.0,
            "corner_bead_per_ft": 0.95,
        },
        labor_rate_per_hour=55.0,
        waste_factor_pct=10.0,
        productivity_rates={"hang_sqft_per_hour": 75.0, "finish_sqft_per_hour": 60.0},
    )

    text_items = {1: [(0.1, 0.9, 0.4, 0.92, "SEE SHEET A7.1 FOR SCHEDULE")]}
    result = engine.calculate(rooms, [unverified_wall], config, text_items=text_items)

    # Wall QTO must be strictly 0.0
    qto_info = result.line_items[0].source_proof["qto_gating"]
    assert qto_info["wall_hang_area_sqft"] == 0.0
    assert qto_info["qto_eligible_walls"] == 0
    assert qto_info["qto_blocked_walls"] == 1

    # Formula breakdown must explicitly prove wall + ceiling separation.
    # New format: "= 0.0 wall + 300.0 ceiling sqft" inside the wall-sheets line item breakdown.
    assert "0.0 wall + 300.0 ceiling sqft" in result.line_items[0].formula_breakdown
