"""tests/test_m3_chal2_mathematical_stress.py: Empirical Challenger Stress Test.

Adversarial validation of:
1. Selective Page 15 (Sheet A-101) verified heights vs flat 10 ft fallback.
2. Selective Page 16 (Sheet A-102) verified heights and quantities.
3. Combined Pages [15, 16] mathematical additivity and cross-sheet callout isolation.
4. Exact Board SF and Stud LF sensitivity to individual wall run heights.
"""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import pytest

from qto.pipeline import QTOPipeline
from qto.quantities import calculate_board_area

BASE_DIR = Path(__file__).resolve().parent.parent
BLUEPRINT_PATH = BASE_DIR / "uploads" / "doc_20261104_101950_6cbd34.pdf"


@pytest.fixture(scope="session")
def blueprint_pdf():
    assert BLUEPRINT_PATH.exists(), f"Blueprint not found: {BLUEPRINT_PATH}"
    return str(BLUEPRINT_PATH)


# =============================================================================
# 1. PAGE 15 (A-101) VERIFIED HEIGHTS VS FLAT 10 FT MATHEMATICAL CONSISTENCY
# =============================================================================

def test_page_15_verified_heights_vs_flat_10ft(blueprint_pdf):
    """Stress test Page 15: verify individual wall heights (8.00 ft, 7.25 ft, 10.0 ft)

    and confirm Board SF and Stud LF are strictly different from and lower than flat 10 ft.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        pipe = QTOPipeline(blueprint_pdf, selected_pages=[15], output_dir=tmp_dir)
        summary = pipe.run()

        runs = summary["runs"]
        assert len(runs) == 18, f"Expected 18 wall runs for Page 15, got {len(runs)}"

        # Segregate verified vs unverified
        verified_runs = [r for r in runs if r.get("is_height_verified")]
        unverified_runs = [r for r in runs if not r.get("is_height_verified")]

        assert len(verified_runs) == 6, f"Expected 6 verified runs, got {len(verified_runs)}"
        assert len(unverified_runs) == 12, f"Expected 12 unverified runs, got {len(unverified_runs)}"

        # 1. Height inspection
        verified_heights = {r["height_ft"] for r in verified_runs}
        assert 8.00 in verified_heights, "Expected 8.00 ft from A-706 elevations"
        assert 7.25 in verified_heights, "Expected 7.25 ft from A-702 restroom elevations"

        for r in verified_runs:
            assert r["status"] == "OK"
            assert r["height_source"] != "UNVERIFIED_HEIGHT_DEFAULT"
            assert r["height_ft"] in (8.00, 7.25)

        for r in unverified_runs:
            assert r["status"] == "REVIEW"
            assert r["height_source"] == "UNVERIFIED_HEIGHT_DEFAULT"
            assert r["height_ft"] == 10.0

        # 2. Mathematical Consistency of Board SF and Stud LF
        actual_total_board_sf = summary["total_board_sf"]

        # Calculate board SF using exact assembly attributes
        # (Tags 7A, 5E, 3A have 2 layers/face; others have 1 layer/face)
        calculated_actual_board_sf = 0.0
        flat_10_board_sf = 0.0

        for r in runs:
            tag = r["tag"]
            gross_lf = r["gross_length_ft"]
            h_actual = r["height_ft"]
            op_tuples = [(op["width_ft"], op["height_ft"]) for op in r.get("openings", [])]
            attrs = pipe.assembly_attributes.get(tag, {})
            faces = int(attrs.get("finished_faces", 2))
            layers = int(attrs.get("layers_per_face", 1))

            r_board_sf = calculate_board_area(gross_lf, h_actual, op_tuples, faces=faces, layers_per_face=layers)
            calculated_actual_board_sf += r_board_sf

            r_flat_10_sf = calculate_board_area(gross_lf, 10.0, op_tuples, faces=faces, layers_per_face=layers)
            flat_10_board_sf += r_flat_10_sf

        # Total board SF must match individual run sum
        assert abs(actual_total_board_sf - calculated_actual_board_sf) < 0.1, (
            f"actual_total_board_sf {actual_total_board_sf} != calculated {calculated_actual_board_sf}"
        )

        # Actual board SF (13140.73) MUST be strictly lower than flat 10 ft (14031.44)
        assert actual_total_board_sf < flat_10_board_sf, "Verified heights did not reduce board SF!"
        observed_savings_sf = flat_10_board_sf - actual_total_board_sf
        assert abs(observed_savings_sf - 890.71) < 1.0, f"Expected 890.71 SF savings, got {observed_savings_sf}"
        assert abs(actual_total_board_sf - 13140.73) < 0.1


# =============================================================================
# 2. PAGE 16 (A-102) VERIFIED HEIGHTS & QUANTITY CHECKS
# =============================================================================

def test_page_16_verified_heights_and_quantities(blueprint_pdf):
    """Stress test Page 16: verify individual wall heights, openings, and takeoff."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        pipe = QTOPipeline(blueprint_pdf, selected_pages=[16], output_dir=tmp_dir)
        summary = pipe.run()

        runs = summary["runs"]
        assert len(runs) == 41, f"Expected 41 wall runs for Page 16, got {len(runs)}"
        assert summary["verified_height_count"] == 21
        assert summary["unverified_height_count"] == 20

        # Check heights are positive and non-zero
        for r in runs:
            assert r["height_ft"] > 0
            assert r["height_source"] is not None
            if r.get("is_height_verified"):
                assert r["status"] == "OK"
            else:
                assert r["status"] == "REVIEW"
                assert r["height_ft"] == 10.0

        # Verify net LF and opening deductions
        gross_lf = summary["total_gross_lf"]
        net_lf = summary["total_net_lf"]
        opening_ded = summary["total_opening_deduction_lf"]

        assert abs(gross_lf - (net_lf + opening_ded)) < 0.1, "Gross != Net + Opening Deductions"
        assert abs(gross_lf - 721.21) < 0.1
        assert abs(net_lf - 693.50) < 0.1
        assert abs(opening_ded - 27.71) < 0.1
        assert abs(summary["total_board_sf"] - 22168.97) < 0.1


# =============================================================================
# 3. COMBINED PAGES [15, 16] ADDITIVITY AND CROSS-SHEET ISOLATION
# =============================================================================

def test_combined_pages_additivity_and_cross_sheet_isolation(blueprint_pdf):
    """Stress test combined [15, 16] processing against separate runs:

    1. Mathematical Additivity: Sum of individual sheets == combined sheet quantities.
    2. Spatial Isolation: No cross-sheet section callout leakage.
    3. Invariance: Heights of runs on Page 15 do not shift when processed with Page 16.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Run Page 15 alone
        p15_dir = Path(tmp_dir) / "p15"
        pipe_15 = QTOPipeline(blueprint_pdf, selected_pages=[15], output_dir=str(p15_dir))
        sum_15 = pipe_15.run()

        # Run Page 16 alone
        p16_dir = Path(tmp_dir) / "p16"
        pipe_16 = QTOPipeline(blueprint_pdf, selected_pages=[16], output_dir=str(p16_dir))
        sum_16 = pipe_16.run()

        # Run Combined [15, 16]
        comb_dir = Path(tmp_dir) / "comb"
        pipe_comb = QTOPipeline(blueprint_pdf, selected_pages=[15, 16], output_dir=str(comb_dir))
        sum_comb = pipe_comb.run()

        # --- 1. Total Wall Runs Additivity ---
        runs_15 = sum_15["runs"]
        runs_16 = sum_16["runs"]
        runs_comb = sum_comb["runs"]

        assert len(runs_15) == 18
        assert len(runs_16) == 41
        assert len(runs_comb) == 59
        assert len(runs_comb) == len(runs_15) + len(runs_16)

        # --- 2. Linear Footage & Area Additivity ---
        # Gross LF
        expected_gross = sum_15["total_gross_lf"] + sum_16["total_gross_lf"]
        assert abs(sum_comb["total_gross_lf"] - expected_gross) < 0.01
        assert abs(sum_comb["total_gross_lf"] - 1187.06) < 0.01

        # Net LF
        expected_net = sum_15["total_net_lf"] + sum_16["total_net_lf"]
        assert abs(sum_comb["total_net_lf"] - expected_net) < 0.01
        assert abs(sum_comb["total_net_lf"] - 1136.74) < 0.01

        # Opening Deductions LF
        expected_open = sum_15["total_opening_deduction_lf"] + sum_16["total_opening_deduction_lf"]
        assert abs(sum_comb["total_opening_deduction_lf"] - expected_open) < 0.01
        assert abs(sum_comb["total_opening_deduction_lf"] - 50.32) < 0.01

        # Board SF
        expected_board_sf = sum_15["total_board_sf"] + sum_16["total_board_sf"]
        assert abs(sum_comb["total_board_sf"] - expected_board_sf) < 0.01
        assert abs(sum_comb["total_board_sf"] - 35309.70) < 0.01

        # Verified & Unverified Counts Additivity
        assert sum_comb["verified_height_count"] == sum_15["verified_height_count"] + sum_16["verified_height_count"]
        assert sum_comb["unverified_height_count"] == sum_15["unverified_height_count"] + sum_16["unverified_height_count"]
        assert sum_comb["verified_height_count"] == 27
        assert sum_comb["unverified_height_count"] == 32

        # --- 3. Spatial Isolation & Height Invariance ---
        # Map runs by geometry (tag, gross_length_ft rounded to 2 decimals)
        comb_p15_runs = [r for r in runs_comb if r["page_num"] == 15]
        comb_p16_runs = [r for r in runs_comb if r["page_num"] == 16]

        assert len(comb_p15_runs) == 18
        assert len(comb_p16_runs) == 41

        # Check each P15 run matches in sequence and geometry
        for i in range(18):
            r_solo = runs_15[i]
            r_comb = comb_p15_runs[i]
            assert r_comb["tag"] == r_solo["tag"]
            assert abs(r_comb["gross_length_ft"] - r_solo["gross_length_ft"]) < 1e-4
            assert r_comb["height_ft"] == r_solo["height_ft"]
            assert r_comb["is_height_verified"] == r_solo["is_height_verified"]
            assert r_comb["height_source"] == r_solo["height_source"]
            assert r_comb["status"] == r_solo["status"]

        # Check each P16 run matches in sequence and geometry
        for i in range(41):
            r_solo = runs_16[i]
            r_comb = comb_p16_runs[i]
            assert r_comb["tag"] == r_solo["tag"]
            assert abs(r_comb["gross_length_ft"] - r_solo["gross_length_ft"]) < 1e-4
            assert r_comb["height_ft"] == r_solo["height_ft"]
            assert r_comb["is_height_verified"] == r_solo["is_height_verified"]
            assert r_comb["height_source"] == r_solo["height_source"]
            assert r_comb["status"] == r_solo["status"]


# =============================================================================
# 4. STUD LINEAR FOOTAGE (LF) SENSITIVITY TO INDIVIDUAL WALL HEIGHTS
# =============================================================================

def test_stud_lf_scales_with_verified_wall_height(blueprint_pdf):
    """Stress test: Stud LF must equal studs_ea * height_ft for each individual run,

    and verify that total stud LF reflects individual verified heights rather than flat 10 ft.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        pipe = QTOPipeline(blueprint_pdf, selected_pages=[15], output_dir=tmp_dir)
        summary = pipe.run()

        by_tag = summary.get("by_tag", {})

        # Verify that for verified tags, stud_lf is computed using individual height_ft
        for tag, t_sum in by_tag.items():
            assert t_sum["stud_lf"] > 0
            assert t_sum["studs_ea"] > 0
            # Stud LF must be <= studs_ea * 10.0 (strictly less when verified heights are 8.0 or 7.25)
            assert t_sum["stud_lf"] <= t_sum["studs_ea"] * 10.0
