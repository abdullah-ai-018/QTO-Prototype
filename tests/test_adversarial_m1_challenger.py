"""
tests/test_adversarial_m1_challenger.py: Empirical Adversarial Verification Suite for Milestone 1.

Scope:
1. Parallel opposite face pairing: separations 2pt, 4pt, 12pt, 15pt, and 13pt cutoff.
2. Deduplication: identical tag merge vs differing tag conflict flagging.
3. Centerline spine calculation: exact midpoint verification between opposite faces.
4. Annotated PDF output: PyMuPDF visual red highlights and interactive annotation objects.
"""

from __future__ import annotations
import math
import tempfile
from pathlib import Path
import pymupdf
import pytest

from qto.geometry import (
    Point,
    Segment,
    BoundingBox,
    are_parallel,
    are_collinear,
    project_point_to_axis,
)
from qto.dedup import (
    WallRun,
    compute_centerline_spine,
    are_runs_overlapping,
    deduplicate_wall_runs,
)
from qto.trace_walls import trace_wall_from_seed
from qto.tags import TagInstance
from qto.annotate import annotate_blueprint_pdf


# =============================================================================
# 1. PARALLEL OPPOSITE FACE PAIRING & CUTOFF VERIFICATION
# =============================================================================

def test_are_parallel_cutoff_thresholds():
    """Verifies that are_parallel correctly pairs opposite faces within [1.0, 13.0] pt

    and enforces strict cutoff above 13.0 pt.
    """
    # Primary face: horizontal segment along y=100 from x=0 to x=100
    s_prim = Segment(x1=0.0, y1=100.0, x2=100.0, y2=100.0)

    # 1. 2pt separation -> Parallel (within [1.0, 13.0])
    s_2pt = Segment(x1=0.0, y1=102.0, x2=100.0, y2=102.0)
    is_par, d_2 = are_parallel(s_prim, s_2pt)
    assert is_par is True
    assert abs(abs(d_2) - 2.0) < 1e-6

    # 2. 4pt separation -> Parallel
    s_4pt = Segment(x1=0.0, y1=104.0, x2=100.0, y2=104.0)
    is_par, d_4 = are_parallel(s_prim, s_4pt)
    assert is_par is True
    assert abs(abs(d_4) - 4.0) < 1e-6

    # 3. 12pt separation -> Parallel
    s_12pt = Segment(x1=0.0, y1=112.0, x2=100.0, y2=112.0)
    is_par, d_12 = are_parallel(s_prim, s_12pt)
    assert is_par is True
    assert abs(abs(d_12) - 12.0) < 1e-6

    # 4. 13pt separation -> Boundary edge: Parallel
    s_13pt = Segment(x1=0.0, y1=113.0, x2=100.0, y2=113.0)
    is_par, d_13 = are_parallel(s_prim, s_13pt)
    assert is_par is True
    assert abs(abs(d_13) - 13.0) < 1e-6

    # 5. 13.01pt separation -> Exceeds cutoff -> NOT parallel
    s_13_01pt = Segment(x1=0.0, y1=113.01, x2=100.0, y2=113.01)
    is_par, _ = are_parallel(s_prim, s_13_01pt)
    assert is_par is False

    # 6. 15pt separation -> Exceeds cutoff -> NOT parallel
    s_15pt = Segment(x1=0.0, y1=115.0, x2=100.0, y2=115.0)
    is_par, _ = are_parallel(s_prim, s_15pt)
    assert is_par is False

    # 7. Sub-minimum separation (< 1.0 pt) -> NOT parallel
    s_sub1pt = Segment(x1=0.0, y1=100.5, x2=100.0, y2=100.5)
    is_par, _ = are_parallel(s_prim, s_sub1pt)
    assert is_par is False


def test_are_parallel_angular_divergence():
    """Verifies that are_parallel enforces the 3.5-degree angular alignment threshold."""
    s_prim = Segment(x1=0.0, y1=0.0, x2=100.0, y2=0.0)

    # 2.0 degrees divergence (< 3.5 deg) at 4pt offset -> Parallel
    rad_2deg = math.radians(2.0)
    s_2deg = Segment(
        x1=0.0, y1=4.0,
        x2=100.0 * math.cos(rad_2deg), y2=4.0 + 100.0 * math.sin(rad_2deg)
    )
    is_par, _ = are_parallel(s_prim, s_2deg)
    assert is_par is True

    # 4.0 degrees divergence (> 3.5 deg) at 4pt offset -> NOT parallel
    rad_4deg = math.radians(4.0)
    s_4deg = Segment(
        x1=0.0, y1=4.0,
        x2=100.0 * math.cos(rad_4deg), y2=4.0 + 100.0 * math.sin(rad_4deg)
    )
    is_par, _ = are_parallel(s_prim, s_4deg)
    assert is_par is False


def test_trace_wall_face_pairing_empirical_behavior():
    """Empirically tests trace_wall_from_seed behavior across separations 2pt, 4pt, 12pt, 13pt, 15pt.

    Discovers whether 2pt faces are paired as parallel opposite faces or misclassified as collinear.
    """
    s_prim = Segment(x1=0.0, y1=0.0, x2=100.0, y2=0.0)

    # 4pt separation: correctly paired into parallel_segments
    s_4pt = Segment(x1=0.0, y1=4.0, x2=100.0, y2=4.0)
    traced_4pt = trace_wall_from_seed(
        seed_seg=s_prim, leader_seg=None, segments=[s_prim, s_4pt],
        door_arcs=[], ft_per_pt=0.1
    )
    assert len(traced_4pt.parallel_segments) == 1
    assert 4.0 in traced_4pt.twin_offsets

    # 12pt separation: correctly paired into parallel_segments
    s_12pt = Segment(x1=0.0, y1=12.0, x2=100.0, y2=12.0)
    traced_12pt = trace_wall_from_seed(
        seed_seg=s_prim, leader_seg=None, segments=[s_prim, s_12pt],
        door_arcs=[], ft_per_pt=0.1
    )
    assert len(traced_12pt.parallel_segments) == 1
    assert 12.0 in traced_12pt.twin_offsets

    # 13pt separation: correctly paired at cutoff boundary
    s_13pt = Segment(x1=0.0, y1=13.0, x2=100.0, y2=13.0)
    traced_13pt = trace_wall_from_seed(
        seed_seg=s_prim, leader_seg=None, segments=[s_prim, s_13pt],
        door_arcs=[], ft_per_pt=0.1
    )
    assert len(traced_13pt.parallel_segments) == 1
    assert 13.0 in traced_13pt.twin_offsets

    # 15pt separation: excluded by cutoff (> 13pt)
    s_15pt = Segment(x1=0.0, y1=15.0, x2=100.0, y2=15.0)
    traced_15pt = trace_wall_from_seed(
        seed_seg=s_prim, leader_seg=None, segments=[s_prim, s_15pt],
        door_arcs=[], ft_per_pt=0.1
    )
    assert len(traced_15pt.parallel_segments) == 0

    # 2pt separation: Remediated behavior
    # With collinear threshold tightened to 0.75, 2pt separation correctly classifies into parallel_candidates.
    s_2pt = Segment(x1=0.0, y1=2.0, x2=100.0, y2=2.0)
    traced_2pt = trace_wall_from_seed(
        seed_seg=s_prim, leader_seg=None, segments=[s_prim, s_2pt],
        door_arcs=[], ft_per_pt=0.1
    )
    assert len(traced_2pt.parallel_segments) == 1, (
        "2pt separation must be correctly paired as parallel opposite face"
    )
    assert 2.0 in traced_2pt.twin_offsets


# =============================================================================
# 2. DEDUPLICATION: MERGE IDENTICAL VS CONFLICT FLAGGING
# =============================================================================

def test_deduplication_identical_tags_merge():
    """Verifies that two overlapping wall runs with the IDENTICAL tag

    are merged into a single consolidated WallRun with the union span.
    """
    spine1 = Segment(x1=100.0, y1=200.0, x2=200.0, y2=200.0)
    spine2 = Segment(x1=150.0, y1=200.0, x2=250.0, y2=200.0)

    run1 = WallRun(
        run_id="RUN-001", tag="1A", page_num=1, sheet_label="A-101",
        spine=spine1, gross_length_pt=100.0, gross_length_ft=10.0,
        opening_deduction_ft=0.0, net_length_ft=10.0, openings=[],
        segments=[spine1], tag_instances=["TAG-1A-01"]
    )
    run2 = WallRun(
        run_id="RUN-002", tag="1A", page_num=1, sheet_label="A-101",
        spine=spine2, gross_length_pt=100.0, gross_length_ft=10.0,
        opening_deduction_ft=0.0, net_length_ft=10.0, openings=[],
        segments=[spine2], tag_instances=["TAG-1A-02"]
    )

    deduped = deduplicate_wall_runs([run1, run2], ft_per_pt=0.1)

    # Must merge into exactly 1 consolidated run
    assert len(deduped) == 1
    merged = deduped[0]

    # Verify attributes of merged run
    assert merged.tag == "1A"
    assert merged.status == "OK"
    assert merged.run_id == "RUN-001"

    # Union span is x in [100.0, 250.0] -> 150.0 pt -> 15.0 ft
    assert abs(merged.spine.x1 - 100.0) < 1e-4
    assert abs(merged.spine.x2 - 250.0) < 1e-4
    assert abs(merged.gross_length_pt - 150.0) < 1e-4
    assert abs(merged.gross_length_ft - 15.0) < 1e-4
    assert abs(merged.net_length_ft - 15.0) < 1e-4

    # Both segments retained
    assert len(merged.segments) == 2
    # Both tag instances retained
    assert set(merged.tag_instances) == {"TAG-1A-01", "TAG-1A-02"}
    # Merge documented in notes
    assert any("Merged duplicate run from RUN-002" in note for note in merged.notes)


def test_deduplication_different_tags_conflict_flag():
    """Verifies that two overlapping wall runs with DIFFERENT tags

    are flagged as CONFLICT and record the conflicting tag.
    """
    spine1 = Segment(x1=100.0, y1=200.0, x2=200.0, y2=200.0)
    spine2 = Segment(x1=150.0, y1=200.0, x2=250.0, y2=200.0)

    run1 = WallRun(
        run_id="RUN-001", tag="1A", page_num=1, sheet_label="A-101",
        spine=spine1, gross_length_pt=100.0, gross_length_ft=10.0,
        opening_deduction_ft=0.0, net_length_ft=10.0, openings=[],
        segments=[spine1]
    )
    run2 = WallRun(
        run_id="RUN-002", tag="2B", page_num=1, sheet_label="A-101",
        spine=spine2, gross_length_pt=100.0, gross_length_ft=10.0,
        opening_deduction_ft=0.0, net_length_ft=10.0, openings=[],
        segments=[spine2]
    )

    deduped = deduplicate_wall_runs([run1, run2], ft_per_pt=0.1)

    assert len(deduped) == 1
    flagged = deduped[0]

    # Verify conflict status and metadata
    assert flagged.status == "CONFLICT"
    assert "2B" in flagged.conflict_tags
    assert any("Overlaps with tag '2B'" in note for note in flagged.notes)


def test_deduplication_low_overlap_not_merged():
    """Verifies that runs overlapping by less than 40% threshold are NOT merged."""
    # Run 1: x in [0, 100]. Run 2: x in [90, 190]. Overlap = 10 pt (10% < 40%)
    spine1 = Segment(x1=0.0, y1=50.0, x2=100.0, y2=50.0)
    spine2 = Segment(x1=90.0, y1=50.0, x2=190.0, y2=50.0)

    run1 = WallRun(
        run_id="RUN-001", tag="1A", page_num=1, sheet_label="A-101",
        spine=spine1, gross_length_pt=100.0, gross_length_ft=10.0,
        opening_deduction_ft=0.0, net_length_ft=10.0, openings=[], segments=[spine1]
    )
    run2 = WallRun(
        run_id="RUN-002", tag="1A", page_num=1, sheet_label="A-101",
        spine=spine2, gross_length_pt=100.0, gross_length_ft=10.0,
        opening_deduction_ft=0.0, net_length_ft=10.0, openings=[], segments=[spine2]
    )

    deduped = deduplicate_wall_runs([run1, run2], ft_per_pt=0.1)
    assert len(deduped) == 2


def test_deduplication_different_pages_not_merged():
    """Verifies that runs on different sheets/pages are NEVER merged."""
    spine = Segment(x1=0.0, y1=50.0, x2=100.0, y2=50.0)
    run1 = WallRun(
        run_id="RUN-001", tag="1A", page_num=1, sheet_label="A-101",
        spine=spine, gross_length_pt=100.0, gross_length_ft=10.0,
        opening_deduction_ft=0.0, net_length_ft=10.0, openings=[], segments=[spine]
    )
    run2 = WallRun(
        run_id="RUN-002", tag="1A", page_num=2, sheet_label="A-102",
        spine=spine, gross_length_pt=100.0, gross_length_ft=10.0,
        opening_deduction_ft=0.0, net_length_ft=10.0, openings=[], segments=[spine]
    )

    deduped = deduplicate_wall_runs([run1, run2], ft_per_pt=0.1)
    assert len(deduped) == 2


# =============================================================================
# 3. CENTERLINE SPINE CALCULATION & MIDPOINT VERIFICATION
# =============================================================================

def test_centerline_spine_midpoint_exactness():
    """Tests the mathematical accuracy of compute_centerline_spine.

    A true centerline spine must lie at EXACTLY half the separation D/2 between opposite faces.
    """
    ox, oy = 100.0, 200.0
    ux, uy = 1.0, 0.0  # Horizontal wall pointing +x
    t_start, t_end = 0.0, 180.0
    sep = 4.0  # 4pt wall thickness, opposite face at y=204.0

    # Theoretical Ground Truth:
    # Primary face: y = 200.0
    # Opposite face: y = 204.0
    # True Midpoint Centerline: y = 202.0
    expected_midpoint_y = 202.0

    # Remediated behavior: compute_centerline_spine calculates d_center = d_face2 / 2.0
    spine_api = compute_centerline_spine(ox, oy, ux, uy, t_start, t_end, [sep])
    assert abs(spine_api.y1 - expected_midpoint_y) < 1e-4, (
        f"API call with [4.0] offset must place spine at midpoint {expected_midpoint_y}, got {spine_api.y1}"
    )

    # Multiple parallel segments on opposite face
    spine_multi = compute_centerline_spine(ox, oy, ux, uy, t_start, t_end, [sep, sep])
    actual_y_multi = spine_multi.y1
    assert abs(actual_y_multi - expected_midpoint_y) < 1e-4, (
        f"Multiple opposite segments must place spine at midpoint {expected_midpoint_y}, got {actual_y_multi}"
    )


def test_centerline_spine_angled_midpoint():
    """Tests centerline spine calculation on a 45-degree angled wall."""
    ox, oy = 100.0, 100.0
    ang = math.pi / 4.0
    ux, uy = math.cos(ang), math.sin(ang)
    t_start, t_end = 0.0, 100.0
    sep = 4.0

    # Normal vector perpendicular to wall is (-uy, ux) = (-sqrt(2)/2, sqrt(2)/2)
    # Primary face midpoint: (100 + 50*ux, 100 + 50*uy)
    # True centerline midpoint should be shifted by d = 2.0 along normal:
    # cx = 100 + 50*ux - 2.0 * uy
    # cy = 100 + 50*uy + 2.0 * ux
    expected_cx = ox + 50.0 * ux - 2.0 * uy
    expected_cy = oy + 50.0 * uy + 2.0 * ux

    # In current implementation, if twin_offsets = [0.0, 4.0] (single segment hack):
    spine_single = compute_centerline_spine(ox, oy, ux, uy, t_start, t_end, [0.0, sep])
    actual_cx = (spine_single.x1 + spine_single.x2) / 2.0
    actual_cy = (spine_single.y1 + spine_single.y2) / 2.0
    assert abs(actual_cx - expected_cx) < 1e-4
    assert abs(actual_cy - expected_cy) < 1e-4


# =============================================================================
# 4. ANNOTATED PDF OUTPUT: VISUAL HIGHLIGHTS & INTERACTIVE OBJECTS
# =============================================================================

def test_annotated_pdf_generation_visual_and_interactive():
    """Verifies that qto.annotate.annotate_blueprint_pdf produces:

    1. A valid, uncorrupted PDF document.
    2. Visual red vector drawings (semi-transparent bright red highlight + dark red crisp lines).
    3. Interactive PyMuPDF annotation objects (Line annotation on wall, Square annotation on tag).
    """
    input_pdf = "tests/fixtures/fixture_wall20.pdf"
    assert Path(input_pdf).exists(), "Input fixture must exist"

    with tempfile.TemporaryDirectory() as tmpdir:
        out_pdf = str(Path(tmpdir) / "output_annotated.pdf")

        spine = Segment(x1=200.0, y1=352.0, x2=380.0, y2=352.0)
        seg_top = Segment(x1=200.0, y1=350.0, x2=380.0, y2=350.0)
        seg_bot = Segment(x1=200.0, y1=354.0, x2=380.0, y2=354.0)
        leader = Segment(x1=238.25, y1=312.0, x2=238.25, y2=350.0)

        run = WallRun(
            run_id="RUN-001",
            tag="1A",
            page_num=1,
            sheet_label="A-101",
            spine=spine,
            gross_length_pt=180.0,
            gross_length_ft=20.0,
            opening_deduction_ft=0.0,
            net_length_ft=20.0,
            openings=[],
            segments=[seg_top, seg_bot],
            leader_segment=leader,
            status="OK",
        )

        tag = TagInstance(
            tag="1A",
            page_num=1,
            bbox=BoundingBox(x0=228.0, y0=288.0, x1=248.0, y1=312.0),
            center=Point(238.0, 300.0),
            tag_radius=12.0,
        )

        registry = {"1A": {"probability": 0.98, "description": "Metal Stud Drywall"}}

        # Execute annotation engine
        result_path = annotate_blueprint_pdf(
            input_pdf_path=input_pdf,
            runs=[run],
            tag_instances=[tag],
            output_pdf_path=out_pdf,
            registry=registry,
        )

        assert Path(result_path).exists()
        assert Path(result_path).stat().st_size > 0

        # Open and inspect the resulting PDF
        doc = pymupdf.open(result_path)
        try:
            assert len(doc) == 1
            page = doc[0]

            # 1. Verify Interactive PyMuPDF Annotations
            annots = list(page.annots())
            assert len(annots) >= 2, f"Expected at least 2 interactive annotations, got {len(annots)}"

            annot_types = [a.type[1] for a in annots]
            assert "Line" in annot_types, "Must contain interactive Line annotation on wall spine"
            assert "Square" in annot_types, "Must contain interactive Square annotation on tag box"

            # Check line annotation content
            line_annot = next(a for a in annots if a.type[1] == "Line")
            info = line_annot.info
            assert "RUN-001" in info.get("title", "")
            assert "Gross LF: 20.00'" in info.get("content", "")
            assert "Net LF: 20.00'" in info.get("content", "")
            assert "Jev Probability: 98.0%" in info.get("content", "")

            # Check tag annotation content
            rect_annot = next(a for a in annots if a.type[1] == "Square")
            assert "Tag 1A" in rect_annot.info.get("title", "")
            assert "DRYWALL TAG: 1A" in rect_annot.info.get("content", "")

            # 2. Verify Visual Vector Drawings (overlay shape)
            drawings = page.get_drawings()
            assert len(drawings) > 0, "PDF must contain drawing paths"

            # Check for bright red highlight drawings (color ~ (1.0, 0.0, 0.0))
            bright_red_drawings = [
                d for d in drawings
                if d.get("color") and abs(d["color"][0] - 1.0) < 0.05 and d["color"][1] < 0.05 and d["color"][2] < 0.05
            ]
            assert len(bright_red_drawings) > 0, "Must contain bright red highlight band"
            assert any(abs(d.get("width", 0.0) - 8.0) < 0.1 for d in bright_red_drawings), "Bright red band must have width 8.0"

            # Check for dark red drawings (color ~ (0.85, 0.0, 0.0))
            dark_red_drawings = [
                d for d in drawings
                if d.get("color") and abs(d["color"][0] - 0.85) < 0.05 and d["color"][1] < 0.05 and d["color"][2] < 0.05
            ]
            assert len(dark_red_drawings) > 0, "Must contain dark red CAD edge lines"
            assert any(abs(d.get("width", 0.0) - 2.2) < 0.1 for d in dark_red_drawings), "Dark red edge must have width 2.2"
        finally:
            doc.close()


def test_annotated_pdf_missing_file():
    """Verifies that annotate_blueprint_pdf cleanly raises FileNotFoundError when input is missing."""
    with pytest.raises(FileNotFoundError):
        annotate_blueprint_pdf(
            input_pdf_path="non_existent_file.pdf",
            runs=[],
            tag_instances=[],
            output_pdf_path="out.pdf",
        )
