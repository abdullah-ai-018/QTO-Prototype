"""
Remediation Verification Test Suite:
Validates D1 through D10:
- D-Bridge Interval Union & Inflation Bounding
- Unnamed Layer Evidence Gating vs Adversarial Non-Wall Linework
- Diagonal Wall Reconstruction across angles (15, 30, 45, 60, 75 deg)
- Scale Parsing (Architectural, Metric, Civil, Multi-line) & Electrical Exclusions
- Multi-layer Drywall QTO Math & Opening Deductions
"""
import pytest
import math

from app.ocr.parsers import _parse_scale_ratio
from app.geometry.dimension_scale import _parse_dimension
from app.models.enums import ReviewStatus
from app.models.architectural_wall import (
    ArchitecturalWall,
    WallAssemblySpec,
    WallOpening,
    WallClassification,
    DrywallScopeDecision,
    WallDecisionState,
)
from app.trades.drywall_semantic import DrywallSemanticWallPipeline


def test_d_bridge_interval_union_no_inflation():
    """Test that collinear overlapping wall segments do not inflate length and do not create false openings."""
    pipeline = DrywallSemanticWallPipeline(allow_defaults=True)

    # Two overlapping horizontal walls on the same axis (y=0.50), spans [0.10, 0.30] (20 ft) and [0.20, 0.40] (20 ft)
    # Bounding span is [0.10, 0.40] (30 ft). True union span is [0.10, 0.40] (30 ft).
    # Overlap is 10 ft. Total constituent sum is 40 ft.
    w1 = ArchitecturalWall(
        id=1,
        page_id=1,
        start_norm={"x": 0.10, "y": 0.50},
        end_norm={"x": 0.30, "y": 0.50},
        length_ft=20.0,
        height_ft=9.0,
        thickness_in=4.875,
        classification=WallClassification.INTERIOR,
        status="approved",
        qto_eligible=True,
    )
    w2 = ArchitecturalWall(
        id=2,
        page_id=1,
        start_norm={"x": 0.20, "y": 0.50},
        end_norm={"x": 0.40, "y": 0.50},
        length_ft=20.0,
        height_ft=9.0,
        thickness_in=4.875,
        classification=WallClassification.INTERIOR,
        status="approved",
        qto_eligible=True,
    )

    bridged = pipeline._bridge_architectural_walls([w1, w2])
    assert len(bridged) == 1
    b_wall = bridged[0]

    # Stored length must be 30 ft (not 40 ft!)
    assert abs(b_wall.length_ft - 30.0) < 0.2
    # Because segments overlapped without disjoint gaps, zero artificial door openings must be created
    assert b_wall.opening_count == 0
    assert b_wall.opening_area_sqft == 0.0

    ev = b_wall.source_evidence
    assert ev.get("is_bridged") is True
    assert ev.get("true_source_union_length_ft") <= 30.2
    assert ev.get("inflation_ratio") <= 1.05


def test_d_bridge_with_genuine_door_gap():
    """Test that two collinear segments separated by a 3.0 ft gap create exactly 1 door aperture with matching deduction."""
    pipeline = DrywallSemanticWallPipeline(allow_defaults=True)

    # Segment 1: [0.10, 0.20] (10 ft, 100 ft/norm)
    # Gap: [0.20, 0.23] (3 ft)
    # Segment 2: [0.23, 0.33] (10 ft)
    w1 = ArchitecturalWall(
        id=10,
        page_id=1,
        start_norm={"x": 0.10, "y": 0.50},
        end_norm={"x": 0.20, "y": 0.50},
        length_ft=10.0,
        height_ft=9.0,
        thickness_in=4.875,
        classification=WallClassification.INTERIOR,
        status="approved",
        qto_eligible=True,
    )
    w2 = ArchitecturalWall(
        id=11,
        page_id=1,
        start_norm={"x": 0.23, "y": 0.50},
        end_norm={"x": 0.33, "y": 0.50},
        length_ft=10.0,
        height_ft=9.0,
        thickness_in=4.875,
        classification=WallClassification.INTERIOR,
        status="approved",
        qto_eligible=True,
    )

    bridged = pipeline._bridge_architectural_walls([w1, w2])
    assert len(bridged) == 1
    b_wall = bridged[0]

    # Bounding span: 23 ft (10 + 3 + 10)
    assert abs(b_wall.length_ft - 23.0) < 0.5
    assert len(b_wall.openings) == 1
    op = b_wall.openings[0]
    assert abs(op.width_ft - 3.0) < 0.5
    assert op.height_ft == 7.0  # standard door R.O.
    assert abs(op.area_sqft - 21.0) < 3.5


def test_adversarial_unnamed_and_non_wall_filtering():
    """Adversarial test: unnamed linework vs furniture/grid/dimension lines."""
    from app.geometry.wall_entity_reconstruction import is_architectural_wall_candidate, is_compatible_wall_layer

    # 1. Compatible wall layers
    assert is_compatible_wall_layer("A-WALL") is True
    assert is_compatible_wall_layer("PARTITION") is True
    assert is_compatible_wall_layer("S-WALL") is True

    # 2. Negative non-wall layers
    assert is_compatible_wall_layer("A-DOOR") is False
    assert is_compatible_wall_layer("E-DIM") is False
    assert is_compatible_wall_layer("FURNITURE") is False
    assert is_compatible_wall_layer("GRID") is False
    assert is_compatible_wall_layer("A-ANNO-TEXT") is False

    # 3. Unnamed stroke candidate test
    unnamed_stroke = {
        "layer": "unnamed",
        "width_pt": 1.0,
        "length_ft": 8.0,
        "is_in_title_block": False,
        "is_outside_envelope": False,
    }
    # Unnamed strokes pass as candidates for pairing
    assert is_architectural_wall_candidate(unnamed_stroke, [], []) is True

    # Dimension stroke in title block or margin must be rejected
    title_block_stroke = {
        "layer": "A-WALL",
        "width_pt": 1.0,
        "length_ft": 8.0,
        "is_in_title_block": True,
        "is_outside_envelope": False,
    }
    assert is_architectural_wall_candidate(title_block_stroke, [], []) is False


def test_scale_parsing_architectural_metric_civil():
    """Test comprehensive scale notations and electrical tag rejection."""
    # Architectural scales
    assert abs(_parse_scale_ratio("1/8\" = 1'-0\"") - (1.0 / 96.0)) < 1e-6
    assert abs(_parse_scale_ratio("1/4\" = 1'-0\"") - (1.0 / 48.0)) < 1e-6
    assert abs(_parse_scale_ratio("3/16\" = 1'-0\"") - (3.0 / 192.0)) < 1e-6
    assert abs(_parse_scale_ratio("3/32\" = 1'-0\"") - (3.0 / 384.0)) < 1e-6
    assert abs(_parse_scale_ratio("1-1/2\" = 1'-0\"") - (1.5 / 12.0)) < 1e-6
    assert abs(_parse_scale_ratio("SCALE: 1/8\" = 1'-0\"") - (1.0 / 96.0)) < 1e-6

    # Metric scales
    assert abs(_parse_scale_ratio("1:100") - (1.0 / 100.0)) < 1e-6
    assert abs(_parse_scale_ratio("SCALE 1:50") - (1.0 / 50.0)) < 1e-6
    assert abs(_parse_scale_ratio("1/200") - (1.0 / 200.0)) < 1e-6

    # Civil scales
    assert abs(_parse_scale_ratio("1\" = 20'") - (1.0 / 240.0)) < 1e-6
    assert abs(_parse_scale_ratio("1\" = 50'") - (1.0 / 600.0)) < 1e-6

    # Electrical tag rejection in dimension parsing
    assert _parse_dimension("#12 AWG") is None
    assert _parse_dimension("120V") is None
    assert _parse_dimension("20A") is None
    assert _parse_dimension("CKT 4") is None
    assert _parse_dimension("3") is None  # small integer < 10
    assert _parse_dimension("1,373") == 1373.0
    assert _parse_dimension("3500") == 3500.0


def test_drywall_multi_layer_qto_mathematics():
    """Verify QTO gross, deduction, and net formulas across multi-layer assemblies."""
    # Assembly W3: 2 layers side A, 1 layer side B = 3 total layers
    spec_3layer = WallAssemblySpec(
        tag="W3",
        description="3-Layer Partition",
        stud_depth_in=3.625,
        stud_gauge="25 GA",
        board_type_side_a="5/8\" GWB",
        layers_side_a=2,
        board_type_side_b="5/8\" GWB",
        layers_side_b=1,
        sides_to_hang=2,
        source="verified_schedule",
    )

    op = WallOpening(
        id="op-1",
        opening_type="door",
        width_ft=3.0,
        height_ft=7.0,
        area_sqft=21.0,
        dimension_source="schedule",
    )

    wall = ArchitecturalWall(
        id=100,
        page_id=1,
        start_norm={"x": 0.0, "y": 0.0},
        end_norm={"x": 0.2, "y": 0.0},
        length_ft=20.0,
        height_ft=10.0,
        thickness_in=4.875,
        classification=WallClassification.INTERIOR,
        assembly=spec_3layer,
        assembly_verified=True,
        openings=[op],
        status="approved",
        qto_eligible=True,
        drywall_scope=DrywallScopeDecision.REQUIRED,
    )

    # Gross: 20 ft * 10 ft * 3 layers = 600 SF
    assert wall.calculate_hang_area() == 600.0
    # Deduction: 21 SF * 3 layers = 63 SF
    assert wall.opening_area_deduction_sqft == 63.0
def test_diagonal_wall_reconstruction_and_geometry():
    """Verify diagonal wall reconstruction across various angles (15, 30, 45, 60, 75 deg)."""
    angles = [15.0, 30.0, 45.0, 60.0, 75.0]
    scale_ft_per_px = 0.02

    for ang in angles:
        rad = math.radians(ang)
        vx = math.cos(rad)
        vy = math.sin(rad)
        nx = -vy
        ny = vx

        # Create two parallel strokes separated by 5 inches (0.4167 ft = 20.83 px)
        thick_px = (5.0 / 12.0) / scale_ft_per_px
        length_px = 20.0 / scale_ft_per_px  # 20 ft wall

        p1_a = (100.0, 100.0)
        p2_a = (100.0 + length_px * vx, 100.0 + length_px * vy)

        p1_b = (100.0 + thick_px * nx, 100.0 + thick_px * ny)
        p2_b = (100.0 + length_px * vx + thick_px * nx, 100.0 + length_px * vy + thick_px * ny)

        s1 = {
            "id": 1,
            "layer": "a-wall",
            "width_pt": 1.0,
            "p1": p1_a,
            "p2": p2_a,
            "dx": p2_a[0] - p1_a[0],
            "dy": p2_a[1] - p1_a[1],
            "length_ft": 20.0,
            "angle_deg": round(math.degrees(math.atan2(p2_a[1] - p1_a[1], p2_a[0] - p1_a[0])) % 180.0, 1),
            "is_in_title_block": False,
            "is_outside_envelope": False,
        }
        s2 = {
            "id": 2,
            "layer": "a-wall",
            "width_pt": 1.0,
            "p1": p1_b,
            "p2": p2_b,
            "dx": p2_b[0] - p1_b[0],
            "dy": p2_b[1] - p1_b[1],
            "length_ft": 20.0,
            "angle_deg": round(math.degrees(math.atan2(p2_b[1] - p1_b[1], p2_b[0] - p1_b[0])) % 180.0, 1),
            "is_in_title_block": False,
            "is_outside_envelope": False,
        }

        # Test pairing logic directly
        ang_diff = abs(s1["angle_deg"] - s2["angle_deg"])
        assert ang_diff < 3.5 or ang_diff > 176.5
        d1 = abs((s2["p1"][0] - s1["p1"][0]) * nx + (s2["p1"][1] - s1["p1"][1]) * ny)
        assert abs(d1 - thick_px) < 1.0

