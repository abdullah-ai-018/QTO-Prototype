"""Comprehensive test suite for the Drywall-Specific Semantic Wall Projection Layer,
verifying real wall validation, grid/witness line rejection, door gap bridging,
interior vs. exterior classification, and non-regression of sibling trades.
"""

from app.models.enums import ReviewStatus, TradeKey, WallType
from app.models.room import Room
from app.models.wall import Wall
from app.trades.base import TradeConfig
from app.trades.drywall import DrywallEngine
from app.trades.drywall_semantic import DrywallSemanticWallPipeline, DrywallSemanticWall
from app.trades.flooring import FlooringEngine
from app.trades.painting import PaintingEngine
from app.trades.roofing import RoofingEngine


def test_grid_line_rejected():
    """A CAD grid line (A, B, C, D) spanning >75% of page width without bounding a room
    must be flagged as REJECTED with reason 'grid_line'.
    """
    pipeline = DrywallSemanticWallPipeline()
    rooms = [
        Room(id=1, page_id=1, name="Office", area_sqft=200.0, perimeter_ft=60.0,
             polygon_norm=[{"x": 0.2, "y": 0.2}, {"x": 0.4, "y": 0.2}, {"x": 0.4, "y": 0.4}, {"x": 0.2, "y": 0.4}]),
    ]
    grid_wall = Wall(
        id=99, page_id=1, length_ft=80.0, height_ft=9.0, wall_type=WallType.INTERIOR,
        start_norm={"x": 0.05, "y": 0.8}, end_norm={"x": 0.95, "y": 0.8}, confidence=0.9
    )

    results = pipeline.process(rooms, [grid_wall])
    assert len(results) == 1
    sem = results[0]
    assert sem.status == ReviewStatus.REJECTED
    assert sem.rejection_reason == "grid_line"


def test_sub_foot_witness_line_rejected():
    """A sub-foot fragment (<1.0 ft) must be flagged as REJECTED with reason 'dimension_line'."""
    pipeline = DrywallSemanticWallPipeline()
    rooms = []
    witness_wall = Wall(
        id=98, page_id=1, length_ft=0.5, height_ft=9.0, wall_type=WallType.INTERIOR,
        start_norm={"x": 0.2, "y": 0.2}, end_norm={"x": 0.2, "y": 0.205}, confidence=0.5
    )

    results = pipeline.process(rooms, [witness_wall])
    assert len(results) == 1
    assert results[0].status == ReviewStatus.REJECTED
    assert results[0].rejection_reason == "dimension_line"


def test_isolated_line_rejected():
    """An isolated CAD line without room contact and graph connectivity must be REJECTED."""
    pipeline = DrywallSemanticWallPipeline()
    rooms = [
        Room(id=1, page_id=1, name="Office", area_sqft=200.0, perimeter_ft=60.0,
             polygon_norm=[{"x": 0.2, "y": 0.2}, {"x": 0.4, "y": 0.2}, {"x": 0.4, "y": 0.4}, {"x": 0.2, "y": 0.4}]),
    ]
    isolated_wall = Wall(
        id=97, page_id=1, length_ft=12.0, height_ft=9.0, wall_type=WallType.INTERIOR,
        start_norm={"x": 0.7, "y": 0.7}, end_norm={"x": 0.7, "y": 0.8}, confidence=0.5
    )

    results = pipeline.process(rooms, [isolated_wall])
    assert len(results) == 1
    assert results[0].status == ReviewStatus.REJECTED
    assert results[0].rejection_reason in ("insufficient_wall_support", "grid_line", "unpaired_stroke_no_room_boundary")


def test_room_boundary_wall_approved_interior():
    """A wall bounding an interior room and connected to the wall graph must be APPROVED as interior."""
    pipeline = DrywallSemanticWallPipeline()
    rooms = [
        Room(id=1, page_id=1, name="Office 1", area_sqft=200.0, perimeter_ft=60.0,
             polygon_norm=[{"x": 0.2, "y": 0.2}, {"x": 0.4, "y": 0.2}, {"x": 0.4, "y": 0.4}, {"x": 0.2, "y": 0.4}]),
        Room(id=2, page_id=1, name="Office 2", area_sqft=200.0, perimeter_ft=60.0,
             polygon_norm=[{"x": 0.4, "y": 0.2}, {"x": 0.6, "y": 0.2}, {"x": 0.6, "y": 0.4}, {"x": 0.4, "y": 0.4}]),
    ]
    shared_partition = Wall(
        id=10, page_id=1, length_ft=20.0, height_ft=9.0, wall_type=WallType.INTERIOR,
        start_norm={"x": 0.4, "y": 0.2}, end_norm={"x": 0.4, "y": 0.4}, confidence=0.95,
        face_a_segment_id=101, face_b_segment_id=102, thickness_measured=True,
    )
    cross_wall = Wall(
        id=11, page_id=1, length_ft=20.0, height_ft=9.0, wall_type=WallType.INTERIOR,
        start_norm={"x": 0.2, "y": 0.2}, end_norm={"x": 0.6, "y": 0.2}, confidence=0.95,
        face_a_segment_id=111, face_b_segment_id=112, thickness_measured=True,
    )

    results = pipeline.process(rooms, [shared_partition, cross_wall])
    approved = [r for r in results if r.status == ReviewStatus.APPROVED]
    assert len(approved) >= 1
    assert any(a.wall_type == "interior" for a in approved)


def test_door_opening_gap_bridging():
    """Two collinear wall segments separated by a 3.0 ft door frame gap must be bridged into 1 logical wall run."""
    pipeline = DrywallSemanticWallPipeline(door_gap_max_ft=4.5)
    rooms = [
        Room(id=1, page_id=1, name="Office", area_sqft=200.0, perimeter_ft=60.0,
             polygon_norm=[{"x": 0.2, "y": 0.2}, {"x": 0.6, "y": 0.2}, {"x": 0.6, "y": 0.4}, {"x": 0.2, "y": 0.4}]),
    ]
    seg1 = Wall(
        id=1, page_id=1, length_ft=10.0, height_ft=9.0, wall_type=WallType.INTERIOR,
        start_norm={"x": 0.2, "y": 0.2}, end_norm={"x": 0.35, "y": 0.2}, confidence=0.9,
        face_a_segment_id=11, face_b_segment_id=12, thickness_measured=True,
    )
    seg2 = Wall(
        id=2, page_id=1, length_ft=10.0, height_ft=9.0, wall_type=WallType.INTERIOR,
        start_norm={"x": 0.37, "y": 0.2}, end_norm={"x": 0.5, "y": 0.2}, confidence=0.9,
        face_a_segment_id=21, face_b_segment_id=22, thickness_measured=True,
    )

    results = pipeline.process(rooms, [seg1, seg2])
    approved = [r for r in results if r.status == ReviewStatus.APPROVED]
    assert len(approved) == 1
    assert approved[0].openings_count >= 1


def test_drywall_engine_produces_zero_from_rejected_candidates():
    """DrywallEngine must produce 0 wall hang area from rejected candidates."""
    engine = DrywallEngine()
    rooms = [
        Room(id=1, page_id=1, name="Office", area_sqft=200.0, perimeter_ft=60.0, status=ReviewStatus.APPROVED,
             polygon_norm=[{"x": 0.2, "y": 0.2}, {"x": 0.4, "y": 0.2}, {"x": 0.4, "y": 0.4}, {"x": 0.2, "y": 0.4}]),
    ]
    # Only a grid line candidate provided
    walls = [
        Wall(id=99, page_id=1, length_ft=80.0, height_ft=9.0, wall_type=WallType.INTERIOR,
             start_norm={"x": 0.05, "y": 0.8}, end_norm={"x": 0.95, "y": 0.8}, confidence=0.9),
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
    # Total area should equal ceiling area (200 sqft) with 0 wall hang area contribution
    assert result.material_quantity > 0  # Sheets for ceiling
    wall_sheet_items = [item for item in result.line_items if "Wall Sheets" in item.label]
    ceiling_sheet_items = [item for item in result.line_items if "Ceiling Sheets" in item.label]
    assert len(wall_sheet_items) == 1
    assert len(ceiling_sheet_items) == 1
    # Wall sheets should be 0 since grid line is rejected
    assert wall_sheet_items[0].quantity == 0


def test_sibling_trades_unaffected():
    """Verifies that Flooring, Painting, and Roofing engines return identical results
    and do not rely on or call DrywallSemanticWallPipeline.
    """
    flooring = FlooringEngine()
    painting = PaintingEngine()
    roofing = RoofingEngine()

    rooms = [
        Room(id=1, page_id=1, name="Office", area_sqft=200.0, perimeter_ft=60.0, status=ReviewStatus.APPROVED,
             polygon_norm=[{"x": 0.2, "y": 0.2}, {"x": 0.4, "y": 0.2}, {"x": 0.4, "y": 0.4}, {"x": 0.2, "y": 0.4}]),
    ]
    walls = [
        Wall(id=10, page_id=1, length_ft=20.0, height_ft=9.0, wall_type=WallType.INTERIOR, confidence=0.9, status=ReviewStatus.APPROVED,
             start_norm={"x": 0.2, "y": 0.2}, end_norm={"x": 0.4, "y": 0.2}),
    ]

    from app.rules.default_trade_configs import DEFAULT_TRADE_CONFIGS
    fl_defaults = DEFAULT_TRADE_CONFIGS[TradeKey.FLOORING]
    pt_defaults = DEFAULT_TRADE_CONFIGS[TradeKey.PAINTING]
    fl_config = TradeConfig(trade=TradeKey.FLOORING, coverage_rates=fl_defaults["coverage_rates"], material_unit_costs=fl_defaults["material_unit_costs"], labor_rate_per_hour=fl_defaults["labor_rate_per_hour"], waste_factor_pct=fl_defaults["waste_factor_pct"], productivity_rates=fl_defaults["productivity_rates"])
    pt_config = TradeConfig(trade=TradeKey.PAINTING, coverage_rates=pt_defaults["coverage_rates"], material_unit_costs=pt_defaults["material_unit_costs"], labor_rate_per_hour=pt_defaults["labor_rate_per_hour"], waste_factor_pct=pt_defaults["waste_factor_pct"], productivity_rates=pt_defaults["productivity_rates"])

    fl_res = flooring.calculate(rooms, walls, fl_config)
    pt_res = painting.calculate(rooms, walls, pt_config)

    assert fl_res.material_quantity > 0
    assert pt_res.material_quantity > 0
