"""
Comprehensive 17 Critical Unit Tests for Architectural Wall Continuity & Enclosure Engine.
"""

import math
import pytest
from app.geometry.wall_entity_reconstruction import (
    is_compatible_wall_layer,
    is_architectural_wall_candidate,
    classify_gap,
)

def make_stroke(overrides: dict) -> dict:
    base = {
        "id": 1,
        "layer": "wall",
        "width_pt": 0.55,
        "p1": (100.0, 200.0),
        "p2": (300.0, 200.0),
        "dx": 200.0,
        "dy": 0.0,
        "length_ft": 4.0,
        "angle_deg": 0.0,
        "floor": "Third Floor",
        "is_in_title_block": False,
        "is_outside_envelope": False,
    }
    base.update(overrides)
    return base

# 1. Single-face 2–4 ft interior partition
def test_single_face_interior_partition_candidate():
    stroke = make_stroke({"layer": "internal wall", "length_ft": 3.0})
    assert is_architectural_wall_candidate(stroke, [], []) is True

# 2. Wall -> structural layer transition compatibility
def test_wall_structural_layer_transition_compatibility():
    assert is_compatible_wall_layer("wall") is True
    assert is_compatible_wall_layer("structural - bearing") is True

# 3. Structural -> con transition compatibility
def test_structural_con_transition_compatibility():
    assert is_compatible_wall_layer("structural") is True
    assert is_compatible_wall_layer("con") is True
    assert is_compatible_wall_layer("ex-wall") is True

# 4. Door opening inside wall
def test_door_opening_gap_classification():
    openings = [{
        "type": "DOOR",
        "center": (250.0, 200.0),
        "bbox": (230.0, 190.0, 270.0, 210.0),
    }]
    # 4 ft gap (200px at scale 0.02)
    gap_type = classify_gap(gap_px=200.0, gap_mid=250.0, ax_val=200.0, orient="H", openings=openings, scale_ft_per_px=0.02)
    assert gap_type == "B_DOOR_OPENING"

# 5. Window opening inside exterior wall
def test_window_opening_gap_classification():
    openings = [{
        "type": "WINDOW",
        "center": (400.0, 200.0),
        "bbox": (370.0, 190.0, 430.0, 210.0),
    }]
    gap_type = classify_gap(gap_px=300.0, gap_mid=400.0, ax_val=200.0, orient="H", openings=openings, scale_ft_per_px=0.02)
    assert gap_type == "C_WINDOW_OPENING"

# 6. Column interruption gap classification
def test_column_interruption_gap_classification():
    gap_type = classify_gap(gap_px=75.0, gap_mid=300.0, ax_val=200.0, orient="H", openings=[], scale_ft_per_px=0.02)
    assert gap_type == "D_COLUMN_JUNCTION_GAP"

# 7. 1–2 ft junction gap classification
def test_junction_gap_classification():
    gap_type = classify_gap(gap_px=60.0, gap_mid=300.0, ax_val=200.0, orient="H", openings=[], scale_ft_per_px=0.02)
    assert gap_type == "D_COLUMN_JUNCTION_GAP"

# 8. 3–8 ft door opening bridging
def test_wide_door_opening_classification():
    openings = [{
        "type": "DOOR",
        "center": (500.0, 300.0),
        "bbox": (460.0, 290.0, 540.0, 310.0),
    }]
    gap_type = classify_gap(gap_px=350.0, gap_mid=500.0, ax_val=300.0, orient="H", openings=openings, scale_ft_per_px=0.02)
    assert gap_type == "B_DOOR_OPENING"

# 9. Stair tread multi-signal rejection
def test_stair_tread_rejection():
    stair_boxes = [(100.0, 100.0, 400.0, 400.0)]
    tread = make_stroke({
        "layer": "stair",
        "length_ft": 2.5,
        "angle_deg": 0.0,
        "dx": 100.0,
        "dy": 0.0,
        "p1": (200.0, 250.0),
        "p2": (300.0, 250.0),
        "width_pt": 0.25,
    })
    assert is_architectural_wall_candidate(tread, stair_boxes, []) is False

# 10. Stair-core vertical enclosure wall retention
def test_stair_core_enclosure_wall_retention():
    stair_boxes = [(100.0, 100.0, 400.0, 400.0)]
    enclosure_wall = make_stroke({
        "layer": "structural - bearing",
        "length_ft": 15.0,
        "angle_deg": 90.0,
        "dx": 0.0,
        "dy": 600.0,
        "p1": (100.0, 100.0),
        "p2": (100.0, 400.0),
        "width_pt": 0.56,
    })
    assert is_architectural_wall_candidate(enclosure_wall, stair_boxes, []) is True

# 11. Furniture rejection
def test_furniture_rejection():
    furniture = make_stroke({"layer": "50_furniture", "length_ft": 4.0})
    assert is_architectural_wall_candidate(furniture, [], []) is False
    assert is_compatible_wall_layer("50_furniture") is False

# 12. Fixture rejection
def test_fixture_rejection():
    fixture = make_stroke({"layer": "object", "length_ft": 3.0})
    assert is_architectural_wall_candidate(fixture, [], []) is False
    assert is_compatible_wall_layer("object") is False

# 13. Dimension/grid rejection
def test_dimension_grid_rejection():
    grid = make_stroke({"layer": "structural grid", "length_ft": 25.0})
    assert is_architectural_wall_candidate(grid, [], []) is False
    assert is_compatible_wall_layer("structural grid") is False

# 14. True wall termination separation
def test_true_wall_termination_separation():
    # Long 15 ft gap without opening is a true wall termination
    gap_type = classify_gap(gap_px=800.0, gap_mid=600.0, ax_val=200.0, orient="H", openings=[], scale_ft_per_px=0.02)
    assert gap_type == "G_TRUE_WALL_TERMINATION"

# 15. Snapped contiguous segments
def test_snapped_contiguous_gap():
    gap_type = classify_gap(gap_px=5.0, gap_mid=200.0, ax_val=200.0, orient="H", openings=[], scale_ft_per_px=0.02)
    assert gap_type == "A_CONTIGUOUS_SNAPPED"

# 16. Structural bearing lineweight threshold gating
def test_structural_bearing_lineweight_gating():
    light_hatch_stroke = make_stroke({"layer": "structural - bearing", "width_pt": 0.35, "length_ft": 3.0})
    assert is_architectural_wall_candidate(light_hatch_stroke, [], []) is False

# 17. Title block / outside envelope gating
def test_outside_envelope_gating():
    outside_stroke = make_stroke({"is_outside_envelope": True})
    assert is_architectural_wall_candidate(outside_stroke, [], []) is False
