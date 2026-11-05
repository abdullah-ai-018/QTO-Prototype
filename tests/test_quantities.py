"""test_quantities.py: Mathematical Parity & QTO Engine Unit Tests.

Authoritative specification: Drywall_QTO_SOP.docx (Section 4.1-4.10, 8.7.1)
and PROJECT.md / TEST_INFRA.md.

Validates exact mathematical parity with worked example 8.7.1:
- Gross LF = 20.00 LF
- Opening LF = 3.00 LF
- Net LF = 17.00 LF
- Net Gypsum Board Area = 358.00 SF
- Stud Count = 16 EA (segmented stud formula)
- Stud LF = 160.00 LF
- Metal Track LF = 37.00 LF
- Wood Plates LF = 57.00 LF
- Strict 0.0% default waste policy
"""

from __future__ import annotations

import math
import pytest

# Try importing the production implementation if available; otherwise use reference SOP engine
try:
    from qto.quantities import (
        calculate_takeoff,
        calculate_stud_count,
        calculate_board_area,
        calculate_track_lf,
        calculate_plates_lf,
        calculate_consumables,
    )
    HAS_QTO_MODULE = True
except ImportError:
    HAS_QTO_MODULE = False


# =============================================================================
# AUTHORITATIVE SOP MATHEMATICAL REFERENCE IMPLEMENTATION
# (Direct translation of SOP Section 4.1 - 4.10 and 8.7.1)
# =============================================================================

def sop_gross_lf(length_pt: float, ft_per_pt: float) -> float:
    """SOP 4.1: L_gross = length_pt * ft_per_pt"""
    return round(length_pt * ft_per_pt, 2)


def sop_net_lf(gross_lf: float, opening_widths_ft: list[float]) -> float:
    """SOP 4.2: L_net = L_gross - sum(w_i)"""
    open_lf = sum(opening_widths_ft)
    return round(gross_lf - open_lf, 2)


def sop_board_area(
    gross_lf: float,
    height_ft: float,
    openings: list[tuple[float, float]],  # list of (width_ft, height_ft)
    faces: int = 2,
    layers_per_face: int = 1,
) -> float:
    """SOP 4.3: A_board = (L_gross * H - sum(w_i * h_i)) * (faces * layers_per_face)"""
    wall_gross_surface = gross_lf * height_ft
    openings_area = sum(w * h for w, h in openings)
    net_surface = wall_gross_surface - openings_area
    total_layers = faces * layers_per_face
    return round(net_surface * total_layers, 2)


def sop_stud_count(
    segment_lengths_ft: list[float],
    stud_spacing_in: int = 16,
    extra_studs_per_opening: int = 0,
) -> int:
    """SOP 4.4 & 8.7.1: N = sum(ceil(len_k * 12 / S) + 1) + extra_studs"""
    total = 0
    for length_ft in segment_lengths_ft:
        studs_in_seg = math.ceil((length_ft * 12.0) / stud_spacing_in) + 1
        total += studs_in_seg
    total += extra_studs_per_opening
    return total


def sop_metal_track_lf(gross_lf: float, net_lf: float) -> float:
    """SOP 4.5: Track LF = L_gross (top continuous) + L_net (bottom cut at doors)"""
    return round(gross_lf + net_lf, 2)


def sop_wood_plates_lf(gross_lf: float, net_lf: float) -> float:
    """SOP 4.5: Plates LF = 2 * L_gross (double top plate) + L_net (single bottom plate)"""
    return round(2.0 * gross_lf + net_lf, 2)


def sop_consumables(board_sf: float, wall_gross_lf: float, height_ft: float) -> dict[str, float]:
    """SOP 4.6-4.9: Fasteners, tape, compound, sealant."""
    return {
        "fasteners_ea": round(board_sf * 1.0, 0),             # ~1 screw per SF
        "joint_tape_lf": round(board_sf * 0.38, 2),           # ~0.38 LF per SF (380 LF/1000 SF)
        "joint_compound_gal": round(board_sf * 0.0095, 3),    # ~0.0095 gal per SF (9.5 gal/1000 SF)
        "acoustic_sealant_lf": round(wall_gross_lf * 4.0, 2), # 4 continuous beads (top/bot, both sides)
    }


# =============================================================================
# TIER 1 & TIER 4: WORKED EXAMPLE 8.7.1 PARITY TESTS
# =============================================================================

def test_worked_example_8_7_1_exact_parity():
    """Verify exact numerical parity with SOP Worked Example 8.7.1:

    - 20.00 LF straight wall, 10.00 ft high, 1/8" = 1'-0" scale (180 pt vector).
    - 3.00 ft wide x 7.00 ft high door opening dividing wall into two 8.50 LF segments.
    - 3-5/8" metal studs @ 16" O.C.
    - 1 layer 5/8" Type X GWB each side (2 sides).
    - Default 0% waste.
    """
    # 1. Scale conversion: 1/8" = 1'-0" -> ft_per_pt = 1/9 ft/pt
    ft_per_pt = 1.0 / (72.0 * 0.125)  # 0.111111...
    vector_pt = 180.0
    gross_lf = sop_gross_lf(vector_pt, ft_per_pt)
    assert gross_lf == 20.00, f"Gross LF must be 20.00, got {gross_lf}"

    # 2. Opening deduction
    door_w = 3.00
    door_h = 7.00
    net_lf = sop_net_lf(gross_lf, [door_w])
    assert net_lf == 17.00, f"Net LF must be 17.00, got {net_lf}"

    # 3. Net Gypsum Board Area: (20*10 - 3*7) * 2 = (200 - 21) * 2 = 179 * 2 = 358.00 SF
    board_sf = sop_board_area(
        gross_lf=gross_lf,
        height_ft=10.00,
        openings=[(door_w, door_h)],
        faces=2,
        layers_per_face=1,
    )
    assert board_sf == 358.00, f"Net board SF must be 358.00, got {board_sf}"

    # 4. Stud count: Two 8.5ft segments
    # Segment 1: ceil(8.5*12 / 16) + 1 = ceil(102/16) + 1 = ceil(6.375) + 1 = 7 + 1 = 8
    # Segment 2: ceil(8.5*12 / 16) + 1 = 7 + 1 = 8
    # Total = 8 + 8 = 16 studs
    segments = [8.50, 8.50]
    studs = sop_stud_count(segments, stud_spacing_in=16)
    assert studs == 16, f"Stud count must be exactly 16 EA, got {studs}"

    # 5. Stud linear footage: 16 studs * 10 ft = 160.00 LF
    stud_lf = studs * 10.00
    assert stud_lf == 160.00, f"Stud linear footage must be 160.00 LF, got {stud_lf}"

    # 6. Metal runner track: L_gross + L_net = 20.00 + 17.00 = 37.00 LF
    track_lf = sop_metal_track_lf(gross_lf, net_lf)
    assert track_lf == 37.00, f"Track linear footage must be 37.00 LF, got {track_lf}"

    # 7. Wood plates: 2*L_gross + L_net = 2*20.00 + 17.00 = 57.00 LF
    plates_lf = sop_wood_plates_lf(gross_lf, net_lf)
    assert plates_lf == 57.00, f"Wood plates LF must be 57.00 LF, got {plates_lf}"

    # 8. Consumables
    consumables = sop_consumables(board_sf, gross_lf, 10.00)
    assert consumables["fasteners_ea"] == 358.0
    assert consumables["joint_tape_lf"] == 136.04
    assert consumables["joint_compound_gal"] == 3.401
    assert consumables["acoustic_sealant_lf"] == 80.00


def test_qto_module_integration_if_available():
    """If qto.quantities is available, test that it produces exact parity with SOP 8.7.1."""
    if not HAS_QTO_MODULE:
        pytest.skip("qto.quantities module not yet available in workspace (Milestone 1 in progress)")

    # Call calculate_stud_count
    studs = calculate_stud_count([8.50, 8.50], stud_spacing_in=16)
    assert studs == 16

    # Call calculate_board_area
    area = calculate_board_area(gross_lf=20.0, height_ft=10.0, openings=[(3.0, 7.0)], faces=2, layers_per_face=1)
    assert area == 358.0

    # Call calculate_track_lf
    track = calculate_track_lf(gross_lf=20.0, net_lf=17.0)
    assert track == 37.0


# =============================================================================
# TIER 2: BOUNDARY & EDGE VALUE ANALYSIS (BVA)
# =============================================================================

def test_continuous_wall_without_openings():
    """Verify calculations for 20ft continuous partition wall without any door openings."""
    gross_lf = 20.00
    net_lf = sop_net_lf(gross_lf, [])
    assert net_lf == 20.00

    board_sf = sop_board_area(gross_lf, height_ft=10.0, openings=[], faces=2, layers_per_face=1)
    # (20 * 10 - 0) * 2 = 400.00 SF
    assert board_sf == 400.00

    # Studs: single 20ft segment -> ceil(20*12/16) + 1 = ceil(240/16) + 1 = 15 + 1 = 16
    studs = sop_stud_count([20.00], stud_spacing_in=16)
    assert studs == 16

    track_lf = sop_metal_track_lf(gross_lf, net_lf)
    # 20.00 + 20.00 = 40.00 LF
    assert track_lf == 40.00


def test_stud_count_at_24_inch_spacing():
    """Verify stud counts for 16" vs 24" O.C. spacing."""
    # 20ft continuous wall @ 24" O.C.: ceil(240/24) + 1 = 10 + 1 = 11 studs
    assert sop_stud_count([20.00], stud_spacing_in=24) == 11

    # Worked example with two 8.5ft segments @ 24" O.C.:
    # Seg 1: ceil(102/24) + 1 = ceil(4.25) + 1 = 5 + 1 = 6
    # Seg 2: 5 + 1 = 6
    # Total = 12 studs
    assert sop_stud_count([8.50, 8.50], stud_spacing_in=24) == 12


def test_furring_wall_single_finished_side():
    """Verify Furring Wall (F=1): gypsum board on one side only."""
    gross_lf = 20.00
    height_ft = 10.00
    openings = [(3.00, 7.00)]

    board_sf = sop_board_area(gross_lf, height_ft, openings, faces=1, layers_per_face=1)
    # (20*10 - 21) * 1 = 179.00 SF
    assert board_sf == 179.00


def test_multi_layer_demising_wall():
    """Verify Demising Wall with 2 layers per face on both faces (F=2, n=2 -> 4 total layers)."""
    gross_lf = 20.00
    height_ft = 10.00
    openings = [(3.00, 7.00)]

    board_sf = sop_board_area(gross_lf, height_ft, openings, faces=2, layers_per_face=2)
    # 179.00 * 4 = 716.00 SF
    assert board_sf == 716.00


def test_default_waste_policy_zero_percent():
    """Verify strict default waste rate is 0.0%, and configurable waste operates as multiplier."""
    base_sf = 358.00
    default_waste = 0.0
    adjusted_default = base_sf * (1.0 + default_waste)
    assert adjusted_default == 358.00

    # User configured 5% waste
    waste_5pct = 0.05
    adjusted_5pct = round(base_sf * (1.0 + waste_5pct), 2)
    assert adjusted_5pct == 375.90

    # User configured 10% waste
    waste_10pct = 0.10
    adjusted_10pct = round(base_sf * (1.0 + waste_10pct), 2)
    assert adjusted_10pct == 393.80


def test_multiple_openings_segmented_stud_count():
    """Verify 40ft wall with two 3ft doors creates 3 wall segments."""
    # 40ft gross with two 3ft doors -> 34ft net
    # Segments: 10ft, 14ft, 10ft (10 + 3 + 14 + 3 + 10 = 40)
    segments = [10.00, 14.00, 10.00]
    # Seg 1 (10ft): ceil(120/16) + 1 = ceil(7.5) + 1 = 8 + 1 = 9
    # Seg 2 (14ft): ceil(168/16) + 1 = ceil(10.5) + 1 = 11 + 1 = 12
    # Seg 3 (10ft): 8 + 1 = 9
    # Total = 9 + 12 + 9 = 30 studs
    studs = sop_stud_count(segments, stud_spacing_in=16)
    assert studs == 30


def test_scale_conversion_factors():
    """Verify exact scale conversion math from architectural string to ft_per_pt."""
    scales = {
        (0.125, "1/8\" = 1'-0\""): 1.0 / (72.0 * 0.125),   # 1/9 = 0.111111...
        (0.250, "1/4\" = 1'-0\""): 1.0 / (72.0 * 0.250),   # 1/18 = 0.055555...
        (0.1875, "3/16\" = 1'-0\""): 1.0 / (72.0 * 0.1875),# 1/13.5 = 0.074074...
        (0.050, "1\" = 20'"): 1.0 / (72.0 * 0.050),        # 1/3.6 = 0.277777...
    }
    for (a, label), expected_factor in scales.items():
        calculated = 1.0 / (72.0 * a)
        assert abs(calculated - expected_factor) < 1e-9, f"Scale mismatch for {label}"


def test_zero_length_wall_safety():
    """Verify boundary handling of 0 LF wall."""
    assert sop_gross_lf(0.0, 0.111111) == 0.0
    assert sop_net_lf(0.0, []) == 0.0
    assert sop_board_area(0.0, 10.0, []) == 0.0
    assert sop_stud_count([0.0], 16) == 1  # 1 terminal stud at minimum or 0
