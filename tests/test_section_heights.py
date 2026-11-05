"""
tests/test_section_heights.py: Unit and Integration Tests for Section Tag Callout & Height Verification Engine.

Tests:
1. Architectural dimension parsing (parse_ceiling_height)
2. Sheet code normalization & classification
3. Floor plan callout tag discovery (discover_section_callouts_on_page)
4. Referenced detail sheet height extraction (extract_explicit_height_from_page)
5. Wall run height spatial verification & 10 ft fallback (verify_wall_run_heights)
6. Takeoff calculation integration with extra_review_items
7. Excel export serialization of heights and review items
"""

import os
import pytest
import pymupdf as fitz

from qto.geometry import Point, Segment
from qto.dedup import WallRun
from qto.sheet_index import index_blueprint_sheets
from qto.quantities import calculate_takeoff
from qto.export import create_qto_workbook
from qto.section_heights import (
    parse_ceiling_height,
    normalize_sheet_code,
    classify_callout_sheet,
    discover_section_callouts_on_page,
    extract_explicit_height_from_page,
    verify_wall_run_heights,
    SectionCallout,
)

BLUEPRINT_PATH = os.path.join("uploads", "doc_20261104_101950_6cbd34.pdf")


# =============================================================================
# 1. PARSING & UTILITY TESTS
# =============================================================================

def test_parse_ceiling_height_standard():
    assert parse_ceiling_height("+- 8'-0\" CH") == 8.00
    assert parse_ceiling_height("+- 7'-8\" CH") == pytest.approx(7.67, 0.01)
    assert parse_ceiling_height("+- 7'-3\" CH") == pytest.approx(7.25, 0.01)
    assert parse_ceiling_height("8'-0\" CH") == 8.00
    assert parse_ceiling_height("9' - 6\" CH") == 9.50


def test_parse_ceiling_height_fractions():
    assert parse_ceiling_height("8'-6 1/2\" CH") == pytest.approx(8.54, 0.01)
    assert parse_ceiling_height("9'-3 1/4\" CH") == pytest.approx(9.27, 0.01)
    assert parse_ceiling_height("10'-0 3/4\" CH") == pytest.approx(10.06, 0.01)


def test_parse_ceiling_height_invalid():
    assert parse_ceiling_height("") is None
    assert parse_ceiling_height("RANDOM TEXT") is None
    assert parse_ceiling_height("DOOR 3'-0\" x 7'-0\"") is None


def test_normalize_sheet_code():
    assert normalize_sheet_code("a-706") == "A-706"
    assert normalize_sheet_code("A 702") == "A-702"
    assert normalize_sheet_code("a801") == "A-801"
    assert normalize_sheet_code("A-907") == "A-907"


def test_classify_callout_sheet():
    assert classify_callout_sheet("A-706") == "ELEVATION"
    assert classify_callout_sheet("A-801") == "SECTION"
    assert classify_callout_sheet("A-907") == "PARTITION_DETAIL"
    assert classify_callout_sheet("M-101") == "OTHER"


# =============================================================================
# 2. REAL BLUEPRINT EXTRACTION & VERIFICATION TESTS
# =============================================================================

@pytest.mark.skipif(not os.path.exists(BLUEPRINT_PATH), reason="Blueprint PDF not present")
def test_discover_section_callouts_on_blueprint_p15():
    doc = fitz.open(BLUEPRINT_PATH)
    try:
        p15 = doc[14]  # Page 15 is A-101
        callouts = discover_section_callouts_on_page(p15, page_num=15, current_sheet_label="A-101")
        assert len(callouts) >= 10, f"Expected >= 10 callouts on A-101, got {len(callouts)}"

        found_tags = {c.tag for c in callouts}
        # Check expected tags
        assert any("A-706" in t for t in found_tags), f"Missing A-706 in {found_tags}"
        assert any("A-702" in t for t in found_tags), f"Missing A-702 in {found_tags}"
        assert any("A-801" in t for t in found_tags), f"Missing A-801 in {found_tags}"
        assert any("A-907" in t for t in found_tags), f"Missing A-907 in {found_tags}"

        # Ensure no current sheet false positives (A-101)
        assert not any(c.sheet_ref == "A-101" for c in callouts)
    finally:
        doc.close()


@pytest.mark.skipif(not os.path.exists(BLUEPRINT_PATH), reason="Blueprint PDF not present")
def test_extract_explicit_height_from_blueprint_sheets():
    doc = fitz.open(BLUEPRINT_PATH)
    try:
        catalog = index_blueprint_sheets(doc)
        sheet_map = {s["sheet_label"]: s["page_num"] for s in catalog if s.get("sheet_label")}

        # Test A-706 (Page 52)
        p_a706 = sheet_map.get("A-706")
        assert p_a706 is not None
        h_a706_09 = extract_explicit_height_from_page(doc, p_a706, detail_num="09")
        assert h_a706_09 in (8.00, 7.67), f"Expected 8.00 or 7.67, got {h_a706_09}"

        # Test A-702 (Page 48)
        p_a702 = sheet_map.get("A-702")
        assert p_a702 is not None
        h_a702_01 = extract_explicit_height_from_page(doc, p_a702, detail_num="01")
        assert h_a702_01 == 7.25, f"Expected 7.25 ft for Restroom detail 01 on A-702, got {h_a702_01}"
    finally:
        doc.close()


# =============================================================================
# 3. WALL RUN SPATIAL VERIFICATION LOGIC TESTS
# =============================================================================

def test_verify_wall_run_heights_logic():
    # Synthetic document with two pages: Page 1 (Floor plan), Page 2 (Detail sheet A-706)
    doc = fitz.open()
    
    # Page 1: Floor Plan A-101 with a callout bubble "A-706\n09" at (100, 100)
    p1 = doc.new_page(width=1000, height=1000)
    p1.insert_text(fitz.Point(100, 100), "A-706\n09")

    # Page 2: Elevation sheet A-706 with "+- 8'-0\" CH"
    p2 = doc.new_page(width=1000, height=1000)
    p2.insert_text(fitz.Point(200, 200), "DETAIL 09\nELEVATION\n+- 8'-0\" CH")

    sheet_catalog = [
        {"sheet_label": "A-101", "page_num": 1, "page_type": "FLOOR_PLAN"},
        {"sheet_label": "A-706", "page_num": 2, "page_type": "OTHER"},
    ]

    # Run 1: Close to callout (within 120 pt) -> should verify to 8.00 ft
    wr_close = WallRun(
        run_id="RUN-001",
        tag="5E",
        page_num=1,
        sheet_label="A-101",
        spine=Segment(110, 110, 200, 110),
        gross_length_pt=90.0,
        gross_length_ft=10.0,
        opening_deduction_ft=0.0,
        net_length_ft=10.0,
        openings=[],
        segments=[],
        status="OK",
        ft_per_pt=0.111111,
        is_manual=False,
        height_ft=10.0,
    )

    # Run 2: Far from callout (> 120 pt) -> should fallback to 10.0 ft with REVIEW status
    wr_far = WallRun(
        run_id="RUN-002",
        tag="7A",
        page_num=1,
        sheet_label="A-101",
        spine=Segment(500, 500, 600, 500),
        gross_length_pt=100.0,
        gross_length_ft=11.1,
        opening_deduction_ft=0.0,
        net_length_ft=11.1,
        openings=[],
        segments=[],
        status="OK",
        ft_per_pt=0.111111,
        is_manual=False,
        height_ft=10.0,
    )

    # Run 3: Manual run -> preserves manual height and marks verified
    wr_manual = WallRun(
        run_id="RUN-003",
        tag="1A",
        page_num=1,
        sheet_label="A-101",
        spine=Segment(700, 700, 800, 700),
        gross_length_pt=100.0,
        gross_length_ft=11.1,
        opening_deduction_ft=0.0,
        net_length_ft=11.1,
        openings=[],
        segments=[],
        status="OK",
        ft_per_pt=0.111111,
        is_manual=True,
        height_ft=12.0,
    )

    wall_runs = [wr_close, wr_far, wr_manual]
    updated_runs, reviews = verify_wall_run_heights(doc, wall_runs, sheet_catalog, max_radius_pt=120.0, default_height_ft=10.0)

    # Check Run 1 (Verified)
    assert wr_close.height_ft == 8.00
    assert wr_close.is_height_verified is True
    assert wr_close.status == "OK"
    assert "A-706" in wr_close.height_source

    # Check Run 2 (Unverified fallback)
    assert wr_far.height_ft == 10.0
    assert wr_far.is_height_verified is False
    assert wr_far.status == "REVIEW"
    assert wr_far.height_source == "UNVERIFIED_HEIGHT_DEFAULT"
    assert len(reviews) == 1
    assert reviews[0]["run_id"] == "RUN-002"
    assert "Unverified Wall Height" in reviews[0]["category"]

    # Check Run 3 (Manual override preserved)
    assert wr_manual.height_ft == 12.0
    assert wr_manual.is_height_verified is True
    assert wr_manual.status == "OK"

    doc.close()


# =============================================================================
# 4. TAKEOFF & EXPORT INTEGRATION TESTS
# =============================================================================

def test_takeoff_and_excel_export_with_height_reviews():
    # Setup runs: 1 verified, 1 unverified review
    wr_ver = WallRun(
        run_id="RUN-101",
        tag="5E",
        page_num=15,
        sheet_label="A-101",
        spine=Segment(100, 100, 200, 100),
        gross_length_pt=100.0,
        gross_length_ft=10.0,
        opening_deduction_ft=0.0,
        net_length_ft=10.0,
        openings=[],
        segments=[],
        status="OK",
        ft_per_pt=0.1,
        is_manual=False,
        height_ft=8.0,
        is_height_verified=True,
        height_source="A-706 Detail 09",
    )

    wr_unver = WallRun(
        run_id="RUN-102",
        tag="7A",
        page_num=15,
        sheet_label="A-101",
        spine=Segment(500, 500, 600, 500),
        gross_length_pt=100.0,
        gross_length_ft=10.0,
        opening_deduction_ft=0.0,
        net_length_ft=10.0,
        openings=[],
        segments=[],
        status="REVIEW",
        ft_per_pt=0.1,
        is_manual=False,
        height_ft=10.0,
        is_height_verified=False,
        height_source="UNVERIFIED_HEIGHT_DEFAULT",
    )

    extra_reviews = [{
        "run_id": "RUN-102",
        "target_id": "RUN-102",
        "review_id": "REV-HGT-RUN-102",
        "tag": "7A",
        "page": 15,
        "sheet": "A-101",
        "category": "Unverified Wall Height",
        "issue": "Unverified wall height for Tag 7A: No section callout found.",
        "description": "Unverified wall height for Tag 7A: No section callout found.",
        "action_required": "Estimator review required.",
        "required_action": "Estimator review required.",
        "measured_values": "Default Height: 10.00 ft | Gross: 10.00 LF",
    }]

    takeoff = calculate_takeoff(
        runs=[wr_ver, wr_unver],
        scale_ft_per_pt=0.1,
        default_height_ft=10.0,
        extra_review_items=extra_reviews,
    )

    # Assert review items aggregated
    assert len(takeoff.review_items) >= 1
    assert any(r["run_id"] == "RUN-102" for r in takeoff.review_items)

    # Assert board SF uses individual heights:
    # 5E: gross 10 LF * 8 ft * 2 faces = 160 SF
    # 7A: gross 10 LF * 10 ft * 2 faces = 200 SF
    # Total = 360 SF
    assert takeoff.total_board_sf == pytest.approx(360.0, 1.0)

    # Test openpyxl workbook export
    wb = create_qto_workbook(takeoff, {"run_id": "TEST-EXPORT"})
    assert "Runs" in wb.sheetnames
    assert "Review" in wb.sheetnames
    assert "Summary" in wb.sheetnames

    # Check Review sheet content
    ws_review = wb["Review"]
    assert ws_review.max_row >= 2  # Header + at least 1 item
    found_item = False
    for row in range(2, ws_review.max_row + 1):
        if ws_review.cell(row, 1).value == "REV-HGT-RUN-102":
            found_item = True
            assert ws_review.cell(row, 2).value == "Unverified Wall Height"
            assert ws_review.cell(row, 5).value == "RUN-102"
    assert found_item is True, "REV-HGT-RUN-102 not serialized in Excel Review sheet"

    wb.close()


@pytest.mark.skipif(not os.path.exists(BLUEPRINT_PATH), reason="Blueprint PDF not present")
def test_pipeline_e2e_sheet_a101_verified_heights(tmp_path):
    from qto.pipeline import QTOPipeline
    pipe = QTOPipeline(BLUEPRINT_PATH, selected_pages=[15], output_dir=str(tmp_path))
    summary = pipe.run()

    # Check verified counts
    assert summary["total_wall_runs"] == 18
    assert summary["verified_height_count"] == 6
    assert summary["unverified_height_count"] == 12

    # Check specific verified heights
    verified_runs = [r for r in summary["runs"] if r.get("is_height_verified")]
    assert len(verified_runs) == 6
    verified_heights = {r["height_ft"] for r in verified_runs}
    assert 8.00 in verified_heights, "Expected 8.00 ft from A-706 details"
    assert 7.25 in verified_heights, "Expected 7.25 ft from A-702 restroom details"

    for r in verified_runs:
        assert r["status"] == "OK"
        assert r["height_source"] != "UNVERIFIED_HEIGHT_DEFAULT"

    # Check unverified runs
    unverified_runs = [r for r in summary["runs"] if not r.get("is_height_verified")]
    assert len(unverified_runs) == 12
    for r in unverified_runs:
        assert r["height_ft"] == 10.0
        assert r["status"] == "REVIEW"
        assert r["height_source"] == "UNVERIFIED_HEIGHT_DEFAULT"

    # Check review items
    assert len(summary["review_items"]) >= 12
    assert all("Unverified" in (rev.get("issue") or rev.get("description", "")) for rev in summary["review_items"])

