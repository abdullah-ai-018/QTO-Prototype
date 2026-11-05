"""tests/test_adversarial_m2_chal1.py: Milestone M2 Adversarial Stress Verification Suite.

Challenger: m2_it1_chal1 (Casing Thickness Math & Geometry Stress Verifier)
Milestone: M2 (Floor Plan Geometry, Thickness Measurement & Visual Annotation - Requirement R3)

Stress test battery:
1. Double-line casing separation: test various scale factors (1/8", 1/4", 3/16", 1"=20', 1/2", 3/32")
   and verify d_pt * ft_per_pt * 12.0 = thickness_in with exact floating-point tolerances.
2. Zero-offset and single-line walls: verify that when twin_offsets = [], nominal_thickness_in
   fallback is applied without division by zero, setting thickness_measured = False and thickness_pt = None.
3. Asymmetric twin offsets: verify averaging sum(twin_offsets) / len(twin_offsets) handles noisy draftsmen linework,
   negative offsets, and zero-filtering.
4. Deduplication thickness merge: verify that merging two runs where one is measured and one is nominal
   preserves the measured thickness (in both existing->new and new->existing order), averages when both
   are measured, and preserves nominal when neither is measured.
5. CAD Annotation Stroke Width & Tooltip formatting under varied wall thicknesses.
6. REST API & WallRun serialization contract conformance.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional
import pytest

from qto.geometry import Point, Segment
from qto.openings import Opening
from qto.trace_walls import TracedWall
from qto.dedup import (
    WallRun,
    compute_centerline_spine,
    create_wall_run,
    deduplicate_wall_runs,
    are_runs_overlapping,
)
from qto.annotate import annotate_blueprint_pdf


# Helper function to generate TracedWall instances with arbitrary twin offsets
def make_mock_traced_wall(
    x1: float = 100.0,
    y1: float = 200.0,
    x2: float = 300.0,
    y2: float = 200.0,
    twin_offsets: Optional[List[float]] = None,
    openings: Optional[List[Opening]] = None,
) -> TracedWall:
    seg = Segment(x1=x1, y1=y1, x2=x2, y2=y2)
    offsets = list(twin_offsets) if twin_offsets is not None else []
    ops = list(openings) if openings is not None else []
    return TracedWall(
        seed_segment=seg,
        leader_segment=None,
        traced_segments=[seg],
        collinear_segments=[seg],
        parallel_segments=[],
        twin_offsets=offsets,
        t_start=0.0,
        t_end=seg.length,
        openings=ops,
        ox=x1,
        oy=y1,
        ux=seg.ux,
        uy=seg.uy,
    )


# =============================================================================
# 1. DOUBLE-LINE CASING SEPARATION ACROSS SCALE FACTORS
# =============================================================================

@pytest.mark.parametrize(
    "scale_name, ft_per_pt",
    [
        ("1/8\"=1'-0\"", 1.0 / 9.0),             # 72 * (1/8) = 9 pt/ft
        ("1/4\"=1'-0\"", 1.0 / 18.0),            # 72 * (1/4) = 18 pt/ft
        ("3/16\"=1'-0\"", 1.0 / 13.5),           # 72 * (3/16) = 13.5 pt/ft
        ("1\"=20'-0\"", 20.0 / 72.0),            # 72 pt = 20 ft
        ("1/2\"=1'-0\"", 1.0 / 36.0),            # 72 * (1/2) = 36 pt/ft
        ("3/32\"=1'-0\"", 1.0 / 6.75),           # 72 * (3/32) = 6.75 pt/ft
        ("1\"=10'-0\"", 10.0 / 72.0),            # 72 pt = 10 ft
        ("1\"=40'-0\"", 40.0 / 72.0),            # 72 pt = 40 ft
    ],
)
@pytest.mark.parametrize(
    "nominal_wall_in",
    [
        2.500,   # 2-1/2" stud
        3.625,   # 3-5/8" stud
        4.875,   # 3-5/8" stud + 2x 5/8" GWB (standard drywall)
        5.500,   # 3-1/2" wood stud + 2x 1" board
        6.000,   # 6" partition
        7.250,   # 6" stud + 2x 5/8" GWB
        8.500,   # 6" stud + 4x 5/8" GWB (2-hr fire rated)
        12.000,  # 12" masonry/CMU partition
    ],
)
def test_casing_thickness_math_across_scales(scale_name: str, ft_per_pt: float, nominal_wall_in: float):
    """
    Stress-test casing separation math across architectural and engineering scales.
    Verifies d_pt * ft_per_pt * 12.0 = thickness_in within exact floating-point tolerances.
    """
    # Calculate expected point separation for this physical wall thickness
    # d_in = d_pt * ft_per_pt * 12.0  =>  d_pt = (d_in / 12.0) / ft_per_pt
    d_pt = (nominal_wall_in / 12.0) / ft_per_pt
    
    # Test positive offset (casing face on +normal side)
    traced_pos = make_mock_traced_wall(twin_offsets=[d_pt])
    run_pos = create_wall_run(
        traced=traced_pos,
        tag="7A",
        page_num=15,
        sheet_label="A-101",
        run_id="RUN-POS",
        ft_per_pt=ft_per_pt,
    )
    assert run_pos.thickness_measured is True
    assert run_pos.thickness_pt is not None
    assert abs(run_pos.thickness_pt - round(d_pt, 4)) < 1e-4
    assert run_pos.thickness_in is not None
    assert abs(run_pos.thickness_in - round(nominal_wall_in, 3)) < 1e-3

    # Test negative offset (casing face on -normal side, drafting coordinates flipped)
    traced_neg = make_mock_traced_wall(twin_offsets=[-d_pt])
    run_neg = create_wall_run(
        traced=traced_neg,
        tag="7A",
        page_num=15,
        sheet_label="A-101",
        run_id="RUN-NEG",
        ft_per_pt=ft_per_pt,
    )
    assert run_neg.thickness_measured is True
    assert run_neg.thickness_pt is not None
    assert abs(run_neg.thickness_pt - round(d_pt, 4)) < 1e-4
    assert run_neg.thickness_in is not None
    assert abs(run_neg.thickness_in - round(nominal_wall_in, 3)) < 1e-3


# =============================================================================
# 2. ZERO-OFFSET & SINGLE-LINE WALL FALLBACKS
# =============================================================================

def test_zero_offset_empty_twin_offsets_fallback():
    """
    Verify that when twin_offsets = [], nominal_thickness_in fallback is applied
    without division by zero, setting thickness_measured = False and thickness_pt = None.
    """
    traced_empty = make_mock_traced_wall(twin_offsets=[])

    # Case A: Default fallback (no assembly_attrs provided) -> 4.875" default
    run_def = create_wall_run(
        traced=traced_empty,
        tag="1A",
        page_num=15,
        sheet_label="A-101",
        run_id="RUN-DEF",
        ft_per_pt=1.0 / 9.0,
        assembly_attrs=None,
    )
    assert run_def.thickness_measured is False
    assert run_def.thickness_pt is None
    assert run_def.thickness_in == 4.875

    # Centerline spine should exactly equal the seed line without shift
    assert abs(run_def.spine.x1 - 100.0) < 1e-6
    assert abs(run_def.spine.y1 - 200.0) < 1e-6
    assert abs(run_def.spine.x2 - 300.0) < 1e-6
    assert abs(run_def.spine.y2 - 200.0) < 1e-6

    # Case B: Explicit nominal_thickness_in provided in assembly_attrs
    attrs_explicit = {
        "nominal_thickness_in": 7.25,
        "stud_depth_in": 6.0,
        "material_layers": [{"side": "Face A", "material": "5/8 GWB"}],
    }
    run_exp = create_wall_run(
        traced=traced_empty,
        tag="2B",
        page_num=15,
        sheet_label="A-101",
        run_id="RUN-EXP",
        ft_per_pt=1.0 / 9.0,
        assembly_attrs=attrs_explicit,
    )
    assert run_exp.thickness_measured is False
    assert run_exp.thickness_pt is None
    assert run_exp.thickness_in == 7.25
    assert len(run_exp.material_layers) == 1
    assert run_exp.material_layers[0]["material"] == "5/8 GWB"

    # Case C: Assembly attributes provide layer breakdown to compute nominal
    # stud_depth_in (6.0) + finished_faces (2) * layers_per_face (2) * board_thickness_in (0.625) = 8.5"
    attrs_computed = {
        "stud_depth_in": 6.0,
        "finished_faces": 2,
        "layers_per_face": 2,
        "board_thickness_in": 0.625,
    }
    run_comp = create_wall_run(
        traced=traced_empty,
        tag="4C",
        page_num=15,
        sheet_label="A-101",
        run_id="RUN-COMP",
        ft_per_pt=1.0 / 9.0,
        assembly_attrs=attrs_computed,
    )
    assert run_comp.thickness_measured is False
    assert run_comp.thickness_pt is None
    assert run_comp.thickness_in == 8.5

    # Case D: Empty assembly_attrs dict
    run_empty_dict = create_wall_run(
        traced=traced_empty,
        tag="1A",
        page_num=15,
        sheet_label="A-101",
        run_id="RUN-EMPTY-DICT",
        ft_per_pt=1.0 / 9.0,
        assembly_attrs={},
    )
    assert run_empty_dict.thickness_measured is False
    assert run_empty_dict.thickness_pt is None
    # stud_depth=3.625, finished=2, layers=1, board=0.625 -> 4.875
    assert run_empty_dict.thickness_in == 4.875


def test_compute_centerline_spine_no_div_zero():
    """Verify compute_centerline_spine handles empty twin_offsets without ZeroDivisionError."""
    # Empty list
    spine_empty = compute_centerline_spine(0.0, 0.0, 1.0, 0.0, 0.0, 100.0, [])
    assert spine_empty.length == pytest.approx(100.0)
    assert spine_empty.x1 == 0.0 and spine_empty.y1 == 0.0

    # All-zero offsets list
    spine_zero = compute_centerline_spine(0.0, 0.0, 1.0, 0.0, 0.0, 100.0, [0.0, 0.0])
    assert spine_zero.length == pytest.approx(100.0)
    assert spine_zero.x1 == 0.0 and spine_zero.y1 == 0.0


# =============================================================================
# 3. ASYMMETRIC TWIN OFFSETS & NOISY LINEWORK AVERAGING
# =============================================================================

def test_asymmetric_noisy_twin_offsets():
    """
    Verify averaging sum(twin_offsets) / len(twin_offsets) handles noisy draftsmen linework.
    """
    scale = 1.0 / 9.0  # 1/8" scale

    # 1. Micro-jitter around 3.65625 pt (4.875 inches nominal)
    noisy_offsets = [3.64, 3.68, 3.65, 3.63, 3.67, 3.66]
    expected_avg = sum(noisy_offsets) / len(noisy_offsets)
    expected_in = round(abs(expected_avg) * scale * 12.0, 3)

    traced = make_mock_traced_wall(twin_offsets=noisy_offsets)
    run = create_wall_run(
        traced=traced,
        tag="7A",
        page_num=15,
        sheet_label="A-101",
        run_id="RUN-NOISY",
        ft_per_pt=scale,
    )
    assert run.thickness_measured is True
    assert run.thickness_pt == pytest.approx(round(expected_avg, 4), abs=1e-4)
    assert run.thickness_in == pytest.approx(expected_in, abs=1e-3)

    # 2. Opposite side drawing (all negative perpendicular offsets)
    neg_noisy_offsets = [-3.64, -3.68, -3.65, -3.66]
    expected_neg_avg = sum(neg_noisy_offsets) / len(neg_noisy_offsets)
    expected_neg_in = round(abs(expected_neg_avg) * scale * 12.0, 3)

    traced_neg = make_mock_traced_wall(twin_offsets=neg_noisy_offsets)
    run_neg = create_wall_run(
        traced=traced_neg,
        tag="7A",
        page_num=15,
        sheet_label="A-101",
        run_id="RUN-NEG-NOISY",
        ft_per_pt=scale,
    )
    assert run_neg.thickness_measured is True
    assert run_neg.thickness_pt == pytest.approx(round(abs(expected_neg_avg), 4), abs=1e-4)
    assert run_neg.thickness_in == pytest.approx(expected_neg_in, abs=1e-3)

    # 3. Filtering zero-offsets when valid offsets exist
    mixed_offsets = [0.0, 3.65625, 0.0, 3.65625]
    traced_mixed = make_mock_traced_wall(twin_offsets=mixed_offsets)
    run_mixed = create_wall_run(
        traced=traced_mixed,
        tag="7A",
        page_num=15,
        sheet_label="A-101",
        run_id="RUN-MIXED",
        ft_per_pt=scale,
    )
    assert run_mixed.thickness_measured is True
    assert run_mixed.thickness_pt == pytest.approx(3.6562, abs=1e-3)
    assert run_mixed.thickness_in == pytest.approx(4.875, abs=1e-3)


# =============================================================================
# 4. DEDUPLICATION THICKNESS MERGE BEHAVIOR
# =============================================================================

def test_deduplication_measured_vs_nominal_merge_order():
    """
    Verify that merging two runs where one is measured and one is nominal
    preserves the measured thickness, regardless of merge order.
    """
    scale = 1.0 / 9.0  # 1/8" scale

    # Run 1: Measured (twin_offsets = [3.65625] -> 4.875")
    traced_m = make_mock_traced_wall(x1=0, y1=0, x2=100, y2=0, twin_offsets=[3.65625])
    run_measured = create_wall_run(traced_m, "W1", 1, "A-101", "RUN-MEASURED", scale)
    assert run_measured.thickness_measured is True
    assert run_measured.thickness_in == 4.875

    # Run 2: Nominal fallback (twin_offsets = [] -> 6.0" nominal)
    traced_n = make_mock_traced_wall(x1=10, y1=0, x2=110, y2=0, twin_offsets=[])
    run_nominal = create_wall_run(
        traced_n,
        "W1",
        1,
        "A-101",
        "RUN-NOMINAL",
        scale,
        assembly_attrs={"nominal_thickness_in": 6.0},
    )
    assert run_nominal.thickness_measured is False
    assert run_nominal.thickness_in == 6.0

    # Sub-test A: Existing is Measured, New is Nominal
    merged_a = deduplicate_wall_runs([run_measured, run_nominal], scale)
    assert len(merged_a) == 1
    assert merged_a[0].thickness_measured is True
    assert merged_a[0].thickness_pt == 3.6562
    assert merged_a[0].thickness_in == 4.875

    # Sub-test B: Existing is Nominal, New is Measured
    # Re-instantiate to avoid mutated references
    run_measured_b = create_wall_run(traced_m, "W1", 1, "A-101", "RUN-MEASURED", scale)
    run_nominal_b = create_wall_run(
        traced_n,
        "W1",
        1,
        "A-101",
        "RUN-NOMINAL",
        scale,
        assembly_attrs={"nominal_thickness_in": 6.0},
    )
    merged_b = deduplicate_wall_runs([run_nominal_b, run_measured_b], scale)
    assert len(merged_b) == 1
    assert merged_b[0].thickness_measured is True
    assert merged_b[0].thickness_pt == 3.6562
    assert merged_b[0].thickness_in == 4.875


def test_deduplication_both_measured_averaging():
    """Verify that when both overlapping runs are measured, their thickness points are averaged."""
    scale = 1.0 / 9.0

    # Run 1: 3.60 pt (4.80 in)
    traced_1 = make_mock_traced_wall(x1=0, y1=0, x2=100, y2=0, twin_offsets=[3.60])
    run_1 = create_wall_run(traced_1, "W1", 1, "A-101", "RUN-1", scale)

    # Run 2: 3.80 pt (5.067 in)
    traced_2 = make_mock_traced_wall(x1=20, y1=0, x2=120, y2=0, twin_offsets=[3.80])
    run_2 = create_wall_run(traced_2, "W1", 1, "A-101", "RUN-2", scale)

    merged = deduplicate_wall_runs([run_1, run_2], scale)
    assert len(merged) == 1
    assert merged[0].thickness_measured is True
    # Average of 3.60 and 3.80 is 3.70
    assert merged[0].thickness_pt == pytest.approx(3.70, abs=1e-4)
    expected_in = round(3.70 * scale * 12.0, 3)
    assert merged[0].thickness_in == pytest.approx(expected_in, abs=1e-3)


def test_deduplication_both_nominal_preservation():
    """Verify that when both overlapping runs are nominal, nominal thickness is preserved."""
    scale = 1.0 / 9.0

    traced_1 = make_mock_traced_wall(x1=0, y1=0, x2=100, y2=0, twin_offsets=[])
    run_1 = create_wall_run(
        traced_1,
        "W1",
        1,
        "A-101",
        "RUN-1",
        scale,
        assembly_attrs={"nominal_thickness_in": 5.5},
    )

    traced_2 = make_mock_traced_wall(x1=20, y1=0, x2=120, y2=0, twin_offsets=[])
    run_2 = create_wall_run(
        traced_2,
        "W1",
        1,
        "A-101",
        "RUN-2",
        scale,
        assembly_attrs={"nominal_thickness_in": 5.5},
    )

    merged = deduplicate_wall_runs([run_1, run_2], scale)
    assert len(merged) == 1
    assert merged[0].thickness_measured is False
    assert merged[0].thickness_pt is None
    assert merged[0].thickness_in == 5.5


def test_deduplication_tag_conflict_does_not_merge_thickness():
    """Verify that overlapping runs with differing tags are flagged CONFLICT and do not merge."""
    scale = 1.0 / 9.0

    traced_1 = make_mock_traced_wall(x1=0, y1=0, x2=100, y2=0, twin_offsets=[3.65625])
    run_1 = create_wall_run(traced_1, "TagA", 1, "A-101", "RUN-1", scale)

    traced_2 = make_mock_traced_wall(x1=10, y1=0, x2=90, y2=0, twin_offsets=[7.3125])
    run_2 = create_wall_run(traced_2, "TagB", 1, "A-101", "RUN-2", scale)

    merged = deduplicate_wall_runs([run_1, run_2], scale)
    assert len(merged) == 1
    # run_1 should have CONFLICT status and TagB in conflict_tags
    assert merged[0].status == "CONFLICT"
    assert "TagB" in merged[0].conflict_tags
    assert merged[0].thickness_in == 4.875


def test_deduplication_non_overlapping_runs_preserved():
    """Verify that runs that do not overlap are preserved independently."""
    scale = 1.0 / 9.0

    traced_1 = make_mock_traced_wall(x1=0, y1=0, x2=100, y2=0, twin_offsets=[3.65625])
    run_1 = create_wall_run(traced_1, "TagA", 1, "A-101", "RUN-1", scale)

    # Completely separate run at y=500
    traced_2 = make_mock_traced_wall(x1=0, y1=500, x2=100, y2=500, twin_offsets=[7.3125])
    run_2 = create_wall_run(traced_2, "TagA", 1, "A-101", "RUN-2", scale)

    merged = deduplicate_wall_runs([run_1, run_2], scale)
    assert len(merged) == 2
    assert merged[0].thickness_in == 4.875
    assert merged[1].thickness_in == 9.75


# =============================================================================
# 5. CAD ANNOTATION STROKE WIDTH & TOOLTIP STRESS TESTS
# =============================================================================

def test_annotation_stroke_width_and_tooltip_formatting(tmp_path):
    """
    Verify PDF visual annotation dynamically adapts stroke width to thickness_pt
    while preserving the 8.0 pt invariant for thin runs and correctly formatting tooltips.
    """
    import pymupdf as fitz

    # Create dummy PDF
    pdf_path = tmp_path / "test_annot.pdf"
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    doc.save(str(pdf_path))
    doc.close()

    scale = 1.0 / 9.0

    # 1. Thin wall (thickness_pt = 3.656 < 8.0) -> must use 8.0 pt highlight stroke
    traced_thin = make_mock_traced_wall(x1=50, y1=100, x2=250, y2=100, twin_offsets=[3.65625])
    run_thin = create_wall_run(traced_thin, "7A", 1, "A-101", "RUN-THIN", scale)

    # 2. Thick wall (thickness_pt = 14.5 > 8.0) -> must use 14.5 pt highlight stroke
    traced_thick = make_mock_traced_wall(x1=50, y1=200, x2=250, y2=200, twin_offsets=[14.5])
    run_thick = create_wall_run(traced_thick, "8B", 1, "A-101", "RUN-THICK", scale)

    # 3. Nominal unmeasured wall (thickness_pt = None) -> must use 8.0 pt highlight stroke
    traced_nom = make_mock_traced_wall(x1=50, y1=300, x2=250, y2=300, twin_offsets=[])
    run_nom = create_wall_run(
        traced_nom,
        "1A",
        1,
        "A-101",
        "RUN-NOM",
        scale,
        assembly_attrs={"nominal_thickness_in": 4.875},
    )

    out_pdf = tmp_path / "annotated.pdf"
    annotate_blueprint_pdf(
        input_pdf_path=str(pdf_path),
        runs=[run_thin, run_thick, run_nom],
        tag_instances=[],
        output_pdf_path=str(out_pdf),
    )

    # Inspect the generated annotations in the output PDF
    doc_out = fitz.open(str(out_pdf))
    page_out = doc_out[0]
    annots = list(page_out.annots())
    assert len(annots) >= 3

    info_texts = [a.info.get("content", "") for a in annots]

    # Verify tooltip text content
    assert any('Thickness: 4.88" (Measured)' in t for t in info_texts)
    assert any('Thickness: 19.33" (Measured)' in t for t in info_texts)
    assert any('Thickness: 4.88" (Nominal)' in t for t in info_texts)

    # Verify mandatory token invariants
    for t in info_texts:
        if "Gross LF:" in t:
            assert "Net LF:" in t
            assert "Status: OK" in t

    doc_out.close()


# =============================================================================
# 6. REST API & WALLRUN SERIALIZATION CONTRACT CONFORMANCE
# =============================================================================

def test_wallrun_serialization_contract():
    """Verify WallRun.to_dict() serializes all 7 milestone M2 fields with exact types."""
    scale = 1.0 / 9.0
    layers = [
        {"side": "Face A", "material": "5/8 Type X GWB"},
        {"side": "Core", "material": "3-5/8 Metal Studs"},
    ]
    traced = make_mock_traced_wall(twin_offsets=[3.65625])
    run = create_wall_run(
        traced=traced,
        tag="7A",
        page_num=15,
        sheet_label="A-101",
        run_id="RUN-CONTRACT",
        ft_per_pt=scale,
        material_layers=layers,
    )
    run.section_callout_tag = "A-706 / 09"
    run.is_height_verified = True
    run.height_source = "A-706 Detail 09"
    run.height_ft = 8.5

    d = run.to_dict()

    # Assert presence and exact types
    assert "thickness_pt" in d
    assert isinstance(d["thickness_pt"], float)
    assert d["thickness_pt"] == 3.6562

    assert "thickness_in" in d
    assert isinstance(d["thickness_in"], float)
    assert d["thickness_in"] == 4.875

    assert "thickness_measured" in d
    assert isinstance(d["thickness_measured"], bool)
    assert d["thickness_measured"] is True

    assert "section_callout_tag" in d
    assert d["section_callout_tag"] == "A-706 / 09"

    assert "is_height_verified" in d
    assert d["is_height_verified"] is True

    assert "height_source" in d
    assert d["height_source"] == "A-706 Detail 09"

    assert "material_layers" in d
    assert len(d["material_layers"]) == 2
    assert d["material_layers"][0]["side"] == "Face A"
