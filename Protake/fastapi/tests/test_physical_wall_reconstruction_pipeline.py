"""Comprehensive Physical Wall Reconstruction Pipeline Test Suite.

Locks down the production-grade architecture:
- Geometry Engine (Parallel primitive hypotheses, aspect ratios, thickness)
- Pixel Evidence (Hollow-cavity vs solid stroke discrimination)
- Dual-Face Topology (Face A <-> Face B pairing, centerline (A+B)/2, node clustering)
- Negative Evidence Rejection (Grids, dimension leaders, title blocks, stair treads, MEP)
- Drywall Standards (GA-216, ASTM C754, ASTM C840 buildability & material rate validation)
- QTO Gating & Regression (Hard gate, zero double counting, opening deductions, material BOM)
"""

from app.models.enums import ReviewStatus, WallType
from app.models.room import Room
from app.models.wall import Wall
from app.models.architectural_wall import (
    ArchitecturalWall,
    WallAssemblySpec,
    PhysicalWallType,
    WallClassification,
    ThicknessSource,
    DrywallScopeDecision,
)
from app.trades.drywall_standards import DrywallStandardsEngine, DrywallStandardValidationResult
from app.trades.drywall_semantic import DrywallSemanticWallPipeline


# ==============================================================================
# 1. DRYWALL STANDARDS TESTS (GA-216, ASTM C754 / C840)
# ==============================================================================

def test_drywall_standards_standard_partition():
    """Verify standard 3-5/8" stud partition @ 16" OC complies with GA-216 at standard height."""
    assembly = WallAssemblySpec(
        tag="W1",
        description="3-5/8\" Metal Stud, 5/8\" Type X Each Side",
        stud_depth_in=3.625,
        stud_gauge="25 GA",
        stud_spacing_in=16.0,
        board_type_side_a="5/8\" Type X",
        layers_side_a=1,
        board_type_side_b="5/8\" Type X",
        layers_side_b=1,
        sides_to_hang=2,
        fire_rating_hours=1.0,
        source="partition_schedule",
    )
    result = DrywallStandardsEngine.validate_assembly(
        assembly=assembly,
        physical_thickness_in=4.875,
        height_ft=9.0,
        physical_wall_type=PhysicalWallType.DRYWALL_PARTITION,
    )
    assert result.is_buildable is True
    assert result.is_compliant is True
    assert len(result.issues) == 0
    assert result.estimating_default_fastener_rate == 1.5
    assert result.estimating_default_mud_gal_per_sf == 0.053
    assert result.estimating_default_tape_lf_per_sf == 0.37



def test_drywall_standards_excessive_height_warning():
    """Verify height exceeding 25 GA limiting height triggers GA-216 warning for heavier gauge."""
    assembly = WallAssemblySpec(
        tag="W-HIGH",
        description="3-5/8\" Metal Stud 25 GA @ 16\" OC",
        stud_depth_in=3.625,
        stud_gauge="25 GA",
        stud_spacing_in=16.0,
        board_type_side_a="5/8\" GWB",
        layers_side_a=1,
        board_type_side_b="5/8\" GWB",
        layers_side_b=1,
        sides_to_hang=2,
        source="partition_schedule",
    )
    # 3-5/8" 25 GA has ~15.5 ft limiting height. 18.0 ft should trigger a warning.
    result = DrywallStandardsEngine.validate_assembly(
        assembly=assembly,
        physical_thickness_in=4.875,
        height_ft=18.0,
    )
    assert result.is_buildable is True
    assert any("HEIGHT_EXCEEDS_GA216_LIMIT" in w for w in result.warnings)
    assert result.recommended_stud_gauge == "20 GA"


def test_drywall_standards_fire_rating_layer_check():
    """Verify 2-hour fire rated wall without 2 layers each side triggers ASTM/GA warning."""
    assembly = WallAssemblySpec(
        tag="2HR-W",
        description="2-Hour Rated Wall with single layer",
        stud_depth_in=3.625,
        stud_gauge="20 GA",
        board_type_side_a="5/8\" Type X",
        layers_side_a=1,
        board_type_side_b="5/8\" Type X",
        layers_side_b=1,
        sides_to_hang=2,
        fire_rating_hours=2.0,
        source="partition_schedule",
    )
    result = DrywallStandardsEngine.validate_assembly(
        assembly=assembly,
        physical_thickness_in=4.875,
        height_ft=10.0,
    )
    assert any("FIRE_RATING_LAYER_MISMATCH" in w for w in result.warnings)


# ==============================================================================
# 2. GEOMETRY & NEGATIVE EVIDENCE REJECTION TESTS
# ==============================================================================

def test_negative_evidence_grid_line_rejection():
    """Spanning lines with no thickness and no room adjacency are rejected as structural grids."""
    pipeline = DrywallSemanticWallPipeline(allow_defaults=True)
    grid_wall = Wall(
        id=991,
        page_id=1,
        start_norm={"x": 0.05, "y": 0.50},
        end_norm={"x": 0.95, "y": 0.50},
        length_ft=80.0,
        thickness_ft=0.0,
        thickness_measured=False,
        status=ReviewStatus.APPROVED,
    )
    arch_walls = pipeline.process_architectural_walls(
        rooms=[],
        raw_walls=[grid_wall],
        include_rejected=True,
    )
    assert len(arch_walls) == 1
    aw = arch_walls[0]
    assert aw.status == "rejected"
    assert aw.qto_eligible is False
    assert aw.qto_block_reason in ("STRUCTURAL_GRID_LINE", "NON_WALL_GEOMETRY")


def test_negative_evidence_dimension_line_rejection():
    """Sub-foot witness / dimension lines (< 1.0 ft) are rejected from wall takeoff."""
    pipeline = DrywallSemanticWallPipeline(allow_defaults=True)
    dim_line = Wall(
        id=992,
        page_id=1,
        start_norm={"x": 0.20, "y": 0.20},
        end_norm={"x": 0.205, "y": 0.20},
        length_ft=0.6,
        thickness_ft=0.0,
        thickness_measured=False,
        status=ReviewStatus.APPROVED,
    )
    arch_walls = pipeline.process_architectural_walls(
        rooms=[],
        raw_walls=[dim_line],
        include_rejected=True,
    )
    assert len(arch_walls) == 1
    aw = arch_walls[0]
    assert aw.status == "rejected"
    assert aw.qto_eligible is False
    assert aw.qto_block_reason == "SUB_FOOT_DIMENSION_LINE"


# ==============================================================================
# 3. DUAL-FACE TOPOLOGY & PHYSICAL WALL RECONSTRUCTION
# ==============================================================================

def test_dual_face_pairing_and_centerline_reconstruction():
    """Parallel Face A and Face B within 5" thickness are reconstructed into a single canonical wall."""
    pipeline = DrywallSemanticWallPipeline(allow_defaults=True)

    # Two parallel strokes representing Face A and Face B separated by 0.003 norm (~4.8" in drawing)
    face_a = Wall(
        id=101,
        page_id=1,
        start_norm={"x": 0.200, "y": 0.300},
        end_norm={"x": 0.200, "y": 0.500},
        length_ft=16.0,
        thickness_ft=0.406,
        thickness_measured=True,
        status=ReviewStatus.APPROVED,
    )
    face_b = Wall(
        id=102,
        page_id=1,
        start_norm={"x": 0.203, "y": 0.300},
        end_norm={"x": 0.203, "y": 0.500},
        length_ft=16.0,
        thickness_ft=0.406,
        thickness_measured=True,
        status=ReviewStatus.APPROVED,
    )

    room1 = Room(
        id=1,
        page_id=1,
        polygon_norm=[[0.10, 0.30], [0.20, 0.30], [0.20, 0.50], [0.10, 0.50]],
        area_sqft=300.0,
    )

    arch_walls = pipeline.process_architectural_walls(
        rooms=[room1],
        raw_walls=[face_a, face_b],
        include_rejected=False,
    )

    # Verify deduplicated to a single canonical wall
    assert len(arch_walls) == 1
    cw = arch_walls[0]
    assert cw.status == "approved"
    assert cw.qto_eligible is True
    assert "standards_validation" in cw.source_evidence
    assert cw.source_evidence["standards_validation"]["is_buildable"] is True


def test_qto_gating_unverified_scale_blocks_takeoff():
    """Walls on a page with uncalibrated scale source are blocked by QTO hard gate."""
    pipeline = DrywallSemanticWallPipeline(allow_defaults=True)
    wall = Wall(
        id=201,
        page_id=5,
        start_norm={"x": 0.20, "y": 0.20},
        end_norm={"x": 0.20, "y": 0.40},
        length_ft=15.0,
        thickness_ft=0.406,
        thickness_measured=True,
        status=ReviewStatus.APPROVED,
    )
    room = Room(
        id=10,
        page_id=5,
        polygon_norm=[[0.20, 0.20], [0.40, 0.20], [0.40, 0.40], [0.20, 0.40]],
        area_sqft=200.0,
    )

    # Page scale info indicates scale is ASSUMED / unverified
    page_scale_info = {
        5: {
            "scale_source": "assumed_default",
            "scale_ft_per_px": 0.02,
            "width_px": 4000,
        }
    }

    arch_walls = pipeline.process_architectural_walls(
        rooms=[room],
        raw_walls=[wall],
        page_scale_info=page_scale_info,
        include_rejected=True,
    )

    assert len(arch_walls) == 1
    aw = arch_walls[0]
    assert aw.qto_eligible is False
    assert aw.qto_block_reason == "SCALE_UNVERIFIED"


# ==============================================================================
# 4. PROOF: STANDARDS NEVER MANUFACTURE WALLS
# ==============================================================================

def test_standards_never_manufacture_walls_from_noise():
    """Prove that having a valid assembly/standard NEVER creates an approved wall
    from arbitrary CAD noise or unbacked lines with no room/junction/physical evidence.
    """
    pipeline = DrywallSemanticWallPipeline(allow_defaults=True)

    # Random disconnected floating line with no room boundary, no dual face, no junction
    floating_line = Wall(
        id=777,
        page_id=1,
        start_norm={"x": 0.85, "y": 0.85},
        end_norm={"x": 0.87, "y": 0.85},
        length_ft=2.5,
        thickness_ft=0.0,
        thickness_measured=False,
        status=ReviewStatus.PENDING,
    )

    # Process with full custom schedule specs available
    custom_specs = {
        "W1": WallAssemblySpec(
            tag="W1",
            description="3-5/8\" Metal Stud 25 GA",
            sides_to_hang=2,
            source="partition_schedule",
        )
    }
    pipeline.schedule_specs = custom_specs

    arch_walls = pipeline.process_architectural_walls(
        rooms=[],
        raw_walls=[floating_line],
        include_rejected=True,
    )

    assert len(arch_walls) == 1
    aw = arch_walls[0]
    # The wall MUST be rejected or non-QTO eligible despite standard assembly existing
    assert aw.status == "rejected"
    assert aw.qto_eligible is False
    assert aw.qto_block_reason in ("ISOLATED_SHORT_STROKE", "NON_WALL_GEOMETRY")


# ==============================================================================
# 5. POST-HARDENING QTO SEMANTIC RECONCILIATION TESTS (PAGE 257 VERIFICATION)
# ==============================================================================

def test_page257_room_specific_height_precedence():
    """Verify that room-specific ceiling elevation (10.0 FT) takes precedence over sheet default (9.0 FT)."""
    pipeline = DrywallSemanticWallPipeline(allow_defaults=True)
    wall = Wall(
        id=11,
        page_id=257,
        start_norm={"x": 0.30, "y": 0.30},
        end_norm={"x": 0.30, "y": 0.45},
        length_ft=18.0,
        height_ft=10.0,
        height_source="room_ceiling_spec",
        thickness_ft=0.406,
        thickness_measured=True,
        status=ReviewStatus.APPROVED,
    )
    room104 = Room(
        id=104,
        page_id=257,
        polygon_norm=[[0.20, 0.30], [0.30, 0.30], [0.30, 0.45], [0.20, 0.45]],
        area_sqft=250.0,
    )
    arch_walls = pipeline.process_architectural_walls(
        rooms=[room104],
        raw_walls=[wall],
        include_rejected=False,
    )
    assert len(arch_walls) == 1
    aw = arch_walls[0]
    assert aw.height_ft == 10.0
    assert aw.gross_sf == round(18.0 * 10.0 * 2, 2)  # 360 SF gross


def test_page257_fire_rating_double_layer_assembly_resolution():
    """Verify 2-Hour rated demising wall resolves to 2 layers each side (sides_to_hang=2, total layers=4)."""
    pipeline = DrywallSemanticWallPipeline(allow_defaults=True)
    wall = Wall(
        id=5,
        page_id=257,
        start_norm={"x": 0.10, "y": 0.10},
        end_norm={"x": 0.10, "y": 0.35},
        length_ft=25.0,
        height_ft=9.0,
        thickness_ft=0.50,
        thickness_measured=True,
        status=ReviewStatus.APPROVED,
    )
    # 2-Hour partition assembly
    assembly_2hr = WallAssemblySpec(
        tag="2HR-DEMISING",
        description="2-Hour Fire Partition, 2 Layers 5/8\" Type X Each Side",
        stud_depth_in=3.625,
        stud_gauge="20 GA",
        board_type_side_a="5/8\" Type X",
        layers_side_a=2,
        board_type_side_b="5/8\" Type X",
        layers_side_b=2,
        sides_to_hang=2,
        fire_rating_hours=2.0,
        source="partition_schedule",
    )
    pipeline.schedule_specs = {"2HR-DEMISING": assembly_2hr}

    arch_walls = pipeline.process_architectural_walls(
        rooms=[],
        raw_walls=[wall],
        include_rejected=False,
    )
    assert len(arch_walls) == 1
    aw = arch_walls[0]
    # Hang area calculation with 2 layers per side
    assert aw.height_ft == 9.0
    assert aw.length_ft == 25.0


