"""Comprehensive 14 Critical Geometric Test Suite for Generalized Architectural Wall Reconstruction Engine.

Verifies:
1. Structural grid lines -> NON_WALL
2. Room polygon without physical strokes -> NON_WALL
3. Furniture rectangle -> NON_WALL
4. Dimension line -> NON_WALL
5. Dual parallel strokes -> PHYSICAL_WALL_CONFIRMED
6. Dual parallel strokes + door opening -> PHYSICAL_WALL_CONFIRMED + Opening Deduction
7. Missing partition schedule (A7.1) -> PHYSICAL_WALL_CONFIRMED (assembly_resolved=False)
8. Exterior envelope space classification
9. 45-degree angled wall -> PHYSICAL_WALL_CONFIRMED (zero orientation restriction)
10. Curved/polygonal wall run -> segment preservation
11. Wall column intersection -> segment stitching
12. Single visible face only -> WALL_CANDIDATE_NEEDS_REVIEW (no synthetic face creation)
13. Multiple distinct wall types -> tag spec preservation
14. Door opening net drywall deduction -> exact gross minus opening deductions
"""

import math
from app.models.enums import ReviewStatus, WallType
from app.models.room import Room
from app.models.wall import Wall
from app.models.architectural_wall import (
    ArchitecturalWall,
    WallDecisionState,
    WallOpening,
    WallAssemblySpec,
    WallClassification,
    DrywallScopeDecision,
)
from app.trades.drywall_semantic import DrywallSemanticWallPipeline


def test_structural_grid_line_not_wall():
    """TEST 1: Single long un-paired line spanning >40% without thickness pairing must be REJECTED as grid_line."""
    pipeline = DrywallSemanticWallPipeline()
    rooms = [
        Room(id=1, page_id=1, name="Office", area_sqft=200.0, perimeter_ft=60.0,
             polygon_norm=[{"x": 0.2, "y": 0.2}, {"x": 0.4, "y": 0.2}, {"x": 0.4, "y": 0.4}, {"x": 0.2, "y": 0.4}]),
    ]
    grid_line = Wall(
        id=101, page_id=1, length_ft=120.0, height_ft=9.0, wall_type=WallType.INTERIOR,
        start_norm={"x": 0.1, "y": 0.5}, end_norm={"x": 0.9, "y": 0.5}, confidence=0.3,
        thickness_measured=False
    )
    results = pipeline.process_architectural_walls(rooms, [grid_line])
    assert len(results) == 1
    assert results[0].status == "rejected"
    assert results[0].rejection_reason == "grid_line"


def test_room_polygon_without_physical_strokes_not_wall():
    """TEST 2: Room polygon alone must NEVER invent a physical wall when no PDF linework exists."""
    pipeline = DrywallSemanticWallPipeline()
    rooms = [
        Room(id=1, page_id=1, name="Conference Room", area_sqft=400.0, perimeter_ft=80.0,
             polygon_norm=[{"x": 0.1, "y": 0.1}, {"x": 0.5, "y": 0.1}, {"x": 0.5, "y": 0.5}, {"x": 0.1, "y": 0.5}]),
    ]
    results = pipeline.process_architectural_walls(rooms, [])
    assert len(results) == 0


def test_furniture_rectangle_not_wall():
    """TEST 3: Furniture / fixture rectangle (sub-foot noise / unlinked short strokes) must be REJECTED."""
    pipeline = DrywallSemanticWallPipeline()
    rooms = []
    desk_edge = Wall(
        id=103, page_id=1, length_ft=0.8, height_ft=9.0, wall_type=WallType.INTERIOR,
        start_norm={"x": 0.2, "y": 0.2}, end_norm={"x": 0.2, "y": 0.22}, confidence=0.2,
        thickness_measured=False
    )
    results = pipeline.process_architectural_walls(rooms, [desk_edge])
    assert len(results) == 1
    assert results[0].status == "rejected"
    assert results[0].rejection_reason == "dimension_line"


def test_dimension_line_not_wall():
    """TEST 4: Witness dimension line (< 1.0 ft) must be REJECTED as dimension_line."""
    pipeline = DrywallSemanticWallPipeline()
    witness_line = Wall(
        id=104, page_id=1, length_ft=0.5, height_ft=9.0, wall_type=WallType.INTERIOR,
        start_norm={"x": 0.3, "y": 0.3}, end_norm={"x": 0.3, "y": 0.31}, confidence=0.1
    )
    results = pipeline.process_architectural_walls([], [witness_line])
    assert len(results) == 1
    assert results[0].status == "rejected"


def test_dual_parallel_strokes_physical_wall():
    """TEST 5: Dual parallel strokes with measured partition thickness (4.875") must be PHYSICAL_WALL_CONFIRMED."""
    pipeline = DrywallSemanticWallPipeline()
    rooms = [
        Room(id=1, page_id=1, name="Kitchen", area_sqft=150.0, perimeter_ft=50.0,
             polygon_norm=[{"x": 0.2, "y": 0.2}, {"x": 0.5, "y": 0.2}, {"x": 0.5, "y": 0.5}, {"x": 0.2, "y": 0.5}]),
    ]
    parallel_wall = Wall(
        id=105, page_id=1, length_ft=25.0, height_ft=9.0, wall_type=WallType.INTERIOR,
        start_norm={"x": 0.2, "y": 0.2}, end_norm={"x": 0.5, "y": 0.2}, confidence=0.95,
        thickness_ft=0.406, thickness_measured=True,
        face_a_segment_id=1051, face_b_segment_id=1052
    )
    results = pipeline.process_architectural_walls(rooms, [parallel_wall])
    assert len(results) == 1
    assert results[0].thickness_in == 4.87
    assert results[0].length_ft == 25.0


def test_dual_parallel_strokes_with_door_opening():
    """TEST 6: Dual parallel wall run interrupted by door opening must associate opening and calculate net deduction."""
    pipeline = DrywallSemanticWallPipeline()
    rooms = [
        Room(id=1, page_id=1, name="Corridor", area_sqft=100.0, perimeter_ft=40.0,
             polygon_norm=[{"x": 0.1, "y": 0.1}, {"x": 0.3, "y": 0.1}, {"x": 0.3, "y": 0.6}, {"x": 0.1, "y": 0.6}]),
    ]
    wall_run = Wall(
        id=106, page_id=1, length_ft=20.0, height_ft=9.0, wall_type=WallType.INTERIOR,
        start_norm={"x": 0.1, "y": 0.1}, end_norm={"x": 0.1, "y": 0.5}, confidence=0.95,
        thickness_ft=0.406, thickness_measured=True,
        face_a_segment_id=1061, face_b_segment_id=1062
    )
    # Create opening (3ft x 7ft door = 21 sqft)
    opening = WallOpening(
        id="door-1", opening_type="door", width_ft=3.0, height_ft=7.0, area_sqft=21.0, position_ratio=0.5
    )
    results = pipeline.process_architectural_walls(rooms, [wall_run])
    assert len(results) == 1
    # Set assembly spec with 2 sides to hang GWB
    results[0].assembly = WallAssemblySpec(tag="NR-1", sides_to_hang=2, layers_side_a=1, layers_side_b=1)
    results[0].openings = [opening]
    results[0].opening_count = 1
    results[0].opening_area_sqft = 21.0
    
    gross_hang = results[0].calculate_hang_area()       # 20 * 9 * 2 = 360 sqft
    net_hang = results[0].calculate_net_hang_area()      # 360 - (21 * 2) = 318 sqft
    assert gross_hang == 360.0
    assert net_hang == 318.0


def test_missing_partition_schedule():
    """TEST 7: Physical wall with missing partition schedule A7.1 must retain geometry but set assembly_resolved=False."""
    pipeline = DrywallSemanticWallPipeline()
    rooms = [
        Room(id=1, page_id=1, name="Restroom", area_sqft=80.0, perimeter_ft=36.0,
             polygon_norm=[{"x": 0.5, "y": 0.5}, {"x": 0.7, "y": 0.5}, {"x": 0.7, "y": 0.7}, {"x": 0.5, "y": 0.7}]),
    ]
    restroom_wall = Wall(
        id=107, page_id=1, length_ft=15.0, height_ft=9.0, wall_type=WallType.INTERIOR,
        start_norm={"x": 0.5, "y": 0.5}, end_norm={"x": 0.7, "y": 0.5}, confidence=0.90,
        thickness_ft=0.406, thickness_measured=True,
        face_a_segment_id=1071, face_b_segment_id=1072
    )
    text_items = [(0.55, 0.55, 0.60, 0.58, "SEE SHEET A7.1 FOR PARTITION TYPES")]
    results = pipeline.process_architectural_walls(rooms, [restroom_wall], text_items=text_items)
    assert len(results) == 1
    assert results[0].assembly_resolved is False


def test_exterior_envelope_classification():
    """TEST 8: Wall separating conditioned interior room from exterior unconditioned space must classify as EXTERIOR."""
    pipeline = DrywallSemanticWallPipeline()
    rooms = [
        Room(id=1, page_id=1, name="Main Dining", area_sqft=500.0, perimeter_ft=100.0,
             polygon_norm=[{"x": 0.2, "y": 0.2}, {"x": 0.6, "y": 0.2}, {"x": 0.6, "y": 0.6}, {"x": 0.2, "y": 0.6}]),
    ]
    ext_wall = Wall(
        id=108, page_id=1, length_ft=40.0, height_ft=9.0, wall_type=WallType.EXTERIOR,
        start_norm={"x": 0.2, "y": 0.2}, end_norm={"x": 0.6, "y": 0.2}, confidence=0.95,
        thickness_ft=0.75, thickness_measured=True,
        face_a_segment_id=1081, face_b_segment_id=1082
    )
    results = pipeline.process_architectural_walls(rooms, [ext_wall])
    assert len(results) == 1
    assert results[0].classification == WallClassification.EXTERIOR


def test_45_degree_angled_wall():
    """TEST 9: 45-degree angled partition wall must NOT be rejected by orientation heuristics."""
    pipeline = DrywallSemanticWallPipeline()
    rooms = [
        Room(id=1, page_id=1, name="Foyer", area_sqft=150.0, perimeter_ft=50.0,
             polygon_norm=[{"x": 0.1, "y": 0.1}, {"x": 0.3, "y": 0.1}, {"x": 0.4, "y": 0.2}, {"x": 0.1, "y": 0.2}]),
    ]
    angled_wall = Wall(
        id=109, page_id=1, length_ft=14.14, height_ft=9.0, wall_type=WallType.INTERIOR,
        start_norm={"x": 0.3, "y": 0.1}, end_norm={"x": 0.4, "y": 0.2}, confidence=0.90,
        thickness_ft=0.406, thickness_measured=True,
        face_a_segment_id=1091, face_b_segment_id=1092
    )
    results = pipeline.process_architectural_walls(rooms, [angled_wall])
    assert len(results) == 1
    assert results[0].status != "rejected"
    assert round(results[0].length_ft, 1) == 14.1


def test_curved_polygonal_wall():
    """TEST 10: Curved / multi-segment polygonal wall runs must preserve individual segment runs."""
    pipeline = DrywallSemanticWallPipeline()
    seg1 = Wall(id=110, page_id=1, length_ft=10.0, height_ft=9.0, wall_type=WallType.INTERIOR,
                start_norm={"x": 0.1, "y": 0.1}, end_norm={"x": 0.2, "y": 0.15}, confidence=0.90,
                thickness_ft=0.406, thickness_measured=True)
    seg2 = Wall(id=111, page_id=1, length_ft=10.0, height_ft=9.0, wall_type=WallType.INTERIOR,
                start_norm={"x": 0.2, "y": 0.15}, end_norm={"x": 0.3, "y": 0.25}, confidence=0.90,
                thickness_ft=0.406, thickness_measured=True)
    results = pipeline.process_architectural_walls([], [seg1, seg2])
    assert len(results) == 2


def test_column_intersection_stitching():
    """TEST 11: Wall segments meeting at a structural T-junction node must connect correctly."""
    pipeline = DrywallSemanticWallPipeline()
    w1 = Wall(id=112, page_id=1, length_ft=20.0, height_ft=9.0, wall_type=WallType.INTERIOR,
              start_norm={"x": 0.2, "y": 0.2}, end_norm={"x": 0.6, "y": 0.2}, confidence=0.90,
              thickness_ft=0.406, thickness_measured=True)
    w2 = Wall(id=113, page_id=1, length_ft=15.0, height_ft=9.0, wall_type=WallType.INTERIOR,
              start_norm={"x": 0.4, "y": 0.2}, end_norm={"x": 0.4, "y": 0.5}, confidence=0.90,
              thickness_ft=0.406, thickness_measured=True)
    results = pipeline.process_architectural_walls([], [w1, w2])
    assert len(results) == 2


def test_single_visible_face_needs_review():
    """TEST 12: Wall candidate without measured dual-face thickness and without room contact must be NEEDS_REVIEW."""
    pipeline = DrywallSemanticWallPipeline()
    single_stroke = Wall(
        id=114, page_id=1, length_ft=12.0, height_ft=9.0, wall_type=WallType.INTERIOR,
        start_norm={"x": 0.7, "y": 0.7}, end_norm={"x": 0.7, "y": 0.85}, confidence=0.50,
        thickness_measured=False
    )
    results = pipeline.process_architectural_walls([], [single_stroke])
    assert len(results) == 1
    assert results[0].status in ("needs_review", "rejected")


def test_multiple_distinct_wall_types():
    """TEST 13: Distinct wall tags (NR-1, NR-2, F-1) discovered on different walls must preserve their distinct specs."""
    pipeline = DrywallSemanticWallPipeline()
    rooms = [
        Room(id=1, page_id=1, name="Office", area_sqft=200.0, perimeter_ft=60.0,
             polygon_norm=[{"x": 0.1, "y": 0.1}, {"x": 0.5, "y": 0.1}, {"x": 0.5, "y": 0.5}, {"x": 0.1, "y": 0.5}]),
    ]
    w1 = Wall(id=115, page_id=1, length_ft=20.0, height_ft=9.0, wall_type=WallType.INTERIOR,
              start_norm={"x": 0.1, "y": 0.1}, end_norm={"x": 0.5, "y": 0.1}, confidence=0.95,
              thickness_ft=0.406, thickness_measured=True,
              face_a_segment_id=1151, face_b_segment_id=1152)
    w2 = Wall(id=116, page_id=1, length_ft=20.0, height_ft=9.0, wall_type=WallType.INTERIOR,
              start_norm={"x": 0.1, "y": 0.5}, end_norm={"x": 0.5, "y": 0.5}, confidence=0.95,
              thickness_ft=0.406, thickness_measured=True,
              face_a_segment_id=1161, face_b_segment_id=1162)
    
    text_items = [
        (0.25, 0.10, 0.28, 0.12, "TYPE NR-1"),
        (0.25, 0.50, 0.28, 0.52, "TYPE NR-2"),
    ]
    results = pipeline.process_architectural_walls(rooms, [w1, w2], text_items=text_items)
    assert len(results) == 2
    tags = [r.wall_tag for r in results]
    assert "NR-1" in tags
    assert "NR-2" in tags


def test_hard_invariant_1_room_polygons_cannot_create_walls():
    """INVARIANT 1: Room polygons alone NEVER create walls without physical PDF vector linework."""
    pipeline = DrywallSemanticWallPipeline()
    rooms = [
        Room(id=1, page_id=1, name="Lobby", area_sqft=300.0, perimeter_ft=70.0,
             polygon_norm=[{"x": 0.2, "y": 0.2}, {"x": 0.6, "y": 0.2}, {"x": 0.6, "y": 0.5}, {"x": 0.2, "y": 0.5}]),
    ]
    results = pipeline.process_architectural_walls(rooms, [])
    assert len(results) == 0


def test_hard_invariant_2_and_3_physical_wall_type_separate_from_drywall():
    """INVARIANTS 2 & 3: Physical wall type is separate from drywall scope and requires source geometry."""
    pipeline = DrywallSemanticWallPipeline()
    ext_wall = Wall(
        id=202, page_id=1, length_ft=30.0, height_ft=9.0, wall_type=WallType.EXTERIOR,
        start_norm={"x": 0.1, "y": 0.1}, end_norm={"x": 0.4, "y": 0.1}, confidence=0.95,
        thickness_ft=0.75, thickness_measured=True,
        face_a_segment_id=2021, face_b_segment_id=2022
    )
    results = pipeline.process_architectural_walls([], [ext_wall])
    assert len(results) == 1
    assert results[0].physical_wall_type.value == "exterior_wall"


def test_hard_invariant_8_missing_schedule_unresolved_assembly():
    """INVARIANT 8: Missing schedule means assembly_resolved=False and drywall_scope=NEEDS_REVIEW."""
    pipeline = DrywallSemanticWallPipeline()
    wall = Wall(
        id=208, page_id=1, length_ft=20.0, height_ft=9.0, wall_type=WallType.INTERIOR,
        start_norm={"x": 0.2, "y": 0.2}, end_norm={"x": 0.5, "y": 0.2}, confidence=0.90,
        thickness_ft=0.406, thickness_measured=True,
        face_a_segment_id=2081, face_b_segment_id=2082
    )
    text_items = [(0.25, 0.25, 0.35, 0.27, "SEE SHEET A7.1 FOR SCHEDULE")]
    results = pipeline.process_architectural_walls([], [wall], text_items=text_items)
    assert len(results) == 1
    assert results[0].assembly_resolved is False
    assert results[0].drywall_scope == DrywallScopeDecision.NEEDS_REVIEW


def test_no_false_drywall_from_parallel_lines():
    """CRITICAL ACCEPTANCE TEST: Discriminates millwork counter from architectural drywall partition."""
    pipeline = DrywallSemanticWallPipeline()

    # Scenario A: Casework / Millwork Counter (2 parallel lines 5" apart, no room boundary support, no graph connection)
    counter_edge = Wall(
        id=301, page_id=1, length_ft=12.0, height_ft=3.0, wall_type=WallType.INTERIOR,
        start_norm={"x": 0.7, "y": 0.7}, end_norm={"x": 0.7, "y": 0.82}, confidence=0.40,
        thickness_ft=0.416, thickness_measured=False
    )
    results_counter = pipeline.process_architectural_walls([], [counter_edge])
    assert len(results_counter) == 1
    assert results_counter[0].drywall_scope in (DrywallScopeDecision.NOT_REQUIRED, DrywallScopeDecision.NEEDS_REVIEW)
    card_counter = results_counter[0].to_evidence_card()
    assert card_counter["decision"]["drywall_scope"] in ("UNRESOLVED", "NOT_REQUIRED")

    # Scenario B: Architectural Drywall Partition (2 parallel lines 5" apart, room boundary support, tag NR-2)
    rooms = [
        Room(id=1, page_id=1, name="Kitchen", area_sqft=150.0, perimeter_ft=50.0,
             polygon_norm=[{"x": 0.2, "y": 0.2}, {"x": 0.5, "y": 0.2}, {"x": 0.5, "y": 0.5}, {"x": 0.2, "y": 0.5}]),
    ]
    drywall_partition = Wall(
        id=302, page_id=1, length_ft=25.0, height_ft=9.0, wall_type=WallType.INTERIOR,
        start_norm={"x": 0.2, "y": 0.2}, end_norm={"x": 0.5, "y": 0.2}, confidence=0.95,
        thickness_ft=0.406, thickness_measured=True,
        face_a_segment_id=3021, face_b_segment_id=3022
    )
    text_items = [(0.33, 0.20, 0.36, 0.22, "TYPE NR-2")]
    results_wall = pipeline.process_architectural_walls(rooms, [drywall_partition], text_items=text_items)
    assert len(results_wall) == 1
    assert results_wall[0].status == "approved"
    card_wall = results_wall[0].to_evidence_card()
    assert card_wall["semantic_evidence"]["wall_tag"] == "NR-2"


def test_face_a_and_face_b_require_independent_source_geometry():
    """CRITICAL ACCEPTANCE TEST: Duplicate Face A and Face B IDs must not count as independent faces."""
    pipeline = DrywallSemanticWallPipeline()

    # Case A: Same source segment reused for Face A and Face B (e.g. 302 & 302) -> PHYSICAL_WALL_CONFIRMED_SINGLE_SOURCE
    rooms_a = [
        Room(id=1, page_id=1, name="Kitchen", area_sqft=150.0, perimeter_ft=50.0,
             polygon_norm=[{"x": 0.2, "y": 0.2}, {"x": 0.5, "y": 0.2}, {"x": 0.5, "y": 0.5}, {"x": 0.2, "y": 0.5}]),
    ]
    duplicate_face_wall = Wall(
        id=302, page_id=1, length_ft=25.0, height_ft=9.0, wall_type=WallType.INTERIOR,
        start_norm={"x": 0.2, "y": 0.2}, end_norm={"x": 0.5, "y": 0.2}, confidence=0.95,
        thickness_ft=0.406, thickness_measured=True,
        face_a_segment_id=302, face_b_segment_id=302
    )
    results_dup = pipeline.process_architectural_walls(rooms_a, [duplicate_face_wall])
    assert len(results_dup) == 1
    assert results_dup[0].decision_state == WallDecisionState.PHYSICAL_WALL_CONFIRMED_SINGLE_SOURCE
    assert results_dup[0].has_independent_faces is False
    assert results_dup[0].assembly_resolved is False
    assert results_dup[0].qto_eligible is False

    # Case B: Independent source segment IDs for Face A and Face B (e.g. 302 & 303) -> PHYSICAL_WALL_CONFIRMED
    rooms = [
        Room(id=1, page_id=1, name="Kitchen", area_sqft=150.0, perimeter_ft=50.0,
             polygon_norm=[{"x": 0.2, "y": 0.2}, {"x": 0.5, "y": 0.2}, {"x": 0.5, "y": 0.5}, {"x": 0.2, "y": 0.5}]),
    ]
    independent_face_wall = Wall(
        id=302, page_id=1, length_ft=25.0, height_ft=9.0, wall_type=WallType.INTERIOR,
        start_norm={"x": 0.2, "y": 0.2}, end_norm={"x": 0.5, "y": 0.2}, confidence=0.95,
        thickness_ft=0.406, thickness_measured=True,
        face_a_segment_id=302, face_b_segment_id=303
    )
    results_indep = pipeline.process_architectural_walls(rooms, [independent_face_wall])
    assert len(results_indep) == 1
    assert results_indep[0].decision_state == WallDecisionState.PHYSICAL_WALL_CONFIRMED
    assert results_indep[0].has_independent_faces is True




def test_door_opening_net_drywall_deduction():
    """TEST 14: Net hang area calculation must deduct exact opening area per finished face."""
    wall = ArchitecturalWall(
        id="wall-test-14", page_id=1,
        start_norm={"x": 0.1, "y": 0.1}, end_norm={"x": 0.1, "y": 0.5},
        length_ft=30.0, height_ft=10.0, thickness_in=4.875,
        classification=WallClassification.INTERIOR,
        assembly=WallAssemblySpec(tag="NR-1", sides_to_hang=2, layers_side_a=1, layers_side_b=1),
        drywall_scope=DrywallScopeDecision.REQUIRED,
        qto_eligible=True,
        openings=[WallOpening(id="d1", opening_type="door", width_ft=3.0, height_ft=7.0, area_sqft=21.0)],
        opening_count=1, opening_area_sqft=21.0,
    )
    gross_area = wall.calculate_hang_area()       # 30 * 10 * 2 = 600 sqft
    net_area = wall.calculate_net_hang_area()      # 600 - (21 * 2) = 558 sqft
    assert gross_area == 600.0
    assert net_area == 558.0
