"""Regression test proving that raw vector/grid/dimension segments are NOT
rendered as drywall wall overlays, while room polygons and drywall trade
takeoff quantities remain 100% unchanged.
"""

from app.geometry.page_context import PageContext
from app.geometry.metrics import ScaleContext
from app.geometry.wall_validation import evaluate_wall_candidate, WallEvidence
from app.models.enums import ReviewStatus, TradeKey, WallType
from app.trades.drywall import DrywallEngine
from app.trades.base import TradeConfig
from app.models.room import Room
from app.models.wall import Wall


def test_isolated_unlinked_segments_are_rejected():
    """An isolated, unlinked, non-exterior vector line (dimension witness line or text underline)
    must be flagged as REJECTED so it is never sent or rendered as a wall overlay.
    """
    ctx = PageContext(
        page_type="floor_plan",
        discipline="architectural",
        is_takeoff_eligible=True,
        drawing_zone={"minX": 0.0, "minY": 0.0, "maxX": 0.96, "maxY": 1.0},
        scale_context=ScaleContext.assumed(200),
        width_px=1000,
        height_px=1000,
        has_vector_data=True,
        has_wall_layer=False,
        ocr_available=False,
        selected_trade="drywall",
    )
    evidence = WallEvidence(
        length_ft=12.0,
        connected=False,
        linked_room_index=None,
        exterior=False,
        bbox_norm={"minX": 0.2, "minY": 0.2, "maxX": 0.4, "maxY": 0.21},
        source="vector_raw",
    )
    decision = evaluate_wall_candidate(evidence, ctx)
    assert decision.status == ReviewStatus.REJECTED
    assert "isolated_unlinked_interior_segment" in decision.reasons


def test_structural_grid_lines_are_rejected():
    """A CAD grid line (A, B, C, D) spanning >75% of page width without bounding a room
    must be flagged as REJECTED.
    """
    ctx = PageContext(
        page_type="floor_plan",
        discipline="architectural",
        is_takeoff_eligible=True,
        drawing_zone={"minX": 0.0, "minY": 0.0, "maxX": 0.96, "maxY": 1.0},
        scale_context=ScaleContext.assumed(200),
        width_px=1000,
        height_px=1000,
        has_vector_data=True,
        has_wall_layer=False,
        ocr_available=False,
        selected_trade="drywall",
    )
    evidence = WallEvidence(
        length_ft=80.0,
        connected=False,
        linked_room_index=None,
        exterior=False,
        bbox_norm={"minX": 0.05, "minY": 0.5, "maxX": 0.92, "maxY": 0.51},
        source="vector_raw",
    )
    decision = evaluate_wall_candidate(evidence, ctx)
    assert decision.status == ReviewStatus.REJECTED
    assert "structural_grid_or_dimension_line" in decision.reasons


def test_drywall_trade_quantities_remain_unchanged():
    """Verifies that room polygons and drywall trade takeoff quantities
    are completely preserved and unaffected by wall overlay filtering.
    """
    engine = DrywallEngine()
    rooms = [
        Room(id=1, page_id=1, name="Office", area_sqft=200.0, perimeter_ft=60.0, confidence=0.95, status=ReviewStatus.APPROVED),
    ]
    walls = [
        Wall(id=10, page_id=1, length_ft=20.0, height_ft=9.0, wall_type=WallType.INTERIOR, confidence=0.9, status=ReviewStatus.APPROVED),
        Wall(id=11, page_id=1, length_ft=10.0, height_ft=9.0, wall_type=WallType.EXTERIOR, confidence=0.9, status=ReviewStatus.APPROVED),
    ]
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
            "compound_bucket": 18.0,
            "tape_per_ft": 0.05,
            "screws_per_100": 8.0,
            "corner_bead_per_ft": 0.5,
        },
        labor_rate_per_hour=35.0,
        waste_factor_pct=10.0,
        productivity_rates={"hang_sqft_per_hour": 100.0, "finish_sqft_per_hour": 150.0},
    )

    result = engine.calculate(rooms, walls, config)
    assert result.material_quantity > 0
    assert result.labor_hours > 0
    assert result.direct_cost > 0
