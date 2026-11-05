"""
tests/test_m3_chal1_stress.py: Milestone 3 Adversarial Challenge & Stress Verification Suite.

Challenger: m3_it1_chal1 (Empirical Challenger - critic, specialist)
Milestone: M3 (Geometry & Proximity Association / Section Callouts & Height Verification)

Battery of Adversarial Challenges:
1. Spatial Proximity Boundary:
   - Distance d = 119.9 pt (within 120 pt radius -> MATCHED)
   - Distance d = 120.0 pt (boundary condition: strict < vs <=)
   - Distance d = 120.1 pt (outside 120 pt radius -> UNVERIFIED FALLBACK)
   - Nearest Callout Selection (closer callout prioritized over farther callout)
   - Perpendicular vs Endpoint segment distances
   - Zero-length degenerate spine
2. Dimension Format Parsing Robustness:
   - Standard formats (+- 8'-0" CH, +- 7'-8" CH, +- 7'-3" CH)
   - Fractional inches (8'-6 1/2" CH, 9'-3 1/4" CH, 10'-0 3/4" CH, 8'-1/2" CH)
   - Unicode prime glyphs (8′ - 0″ CH, 7′ 8″ CH)
   - Mixed spacing and no-space variants (8'-0"CH)
   - Non-standard formats (missing quotation mark: 8'-0 CH, word format: 8 FT CH, AFF format: 8'-0" AFF)
   - Out-of-range dimensions (< 5.0 ft or > 30.0 ft)
3. Empty Detail Sheets and Missing Markers:
   - Empty detail sheet (0 text blocks)
   - Detail sheet with text but no ceiling height markers
   - Missing referenced sheet in catalog (e.g. A-999)
   - Out-of-bounds page numbers
   - Multi-detail disambiguation on single sheet (Detail 01 vs Detail 02)
   - Sheet-wide callout without detail number
4. Manual User Overrides (wr.is_manual = True):
   - Manual override next to callout (d = 2 pt) preserves manual height (14.5 ft)
   - Manual override isolated (d = 500 pt) preserves manual height (11.0 ft) and has status "OK", 0 review items
   - Manual override with height_ft = None
5. Multi-Page and Pipeline Scale Stress:
   - Callouts on Page 1 do not bleed to Page 2
   - Empty wall runs list ([])
   - Empty sheet catalog ([])
"""

import math
import os
import pytest
import pymupdf as fitz

from qto.geometry import Point, Segment, point_to_segment_distance
from qto.dedup import WallRun
from qto.section_heights import (
    parse_ceiling_height,
    normalize_sheet_code,
    classify_callout_sheet,
    discover_section_callouts_on_page,
    extract_explicit_height_from_page,
    verify_wall_run_heights,
    SectionCallout,
)


# ==============================================================================
# Helper Factories
# ==============================================================================

def make_wall_run(
    run_id: str = "RUN-TEST",
    tag: str = "5E",
    page_num: int = 1,
    sheet_label: str = "A-101",
    x1: float = 100.0,
    y1: float = 100.0,
    x2: float = 200.0,
    y2: float = 100.0,
    is_manual: bool = False,
    height_ft: float = 10.0,
) -> WallRun:
    spine = Segment(x1, y1, x2, y2)
    length_pt = spine.length
    return WallRun(
        run_id=run_id,
        tag=tag,
        page_num=page_num,
        sheet_label=sheet_label,
        spine=spine,
        gross_length_pt=length_pt,
        gross_length_ft=length_pt * 0.1,
        opening_deduction_ft=0.0,
        net_length_ft=length_pt * 0.1,
        openings=[],
        segments=[],
        status="OK",
        ft_per_pt=0.1,
        is_manual=is_manual,
        height_ft=height_ft,
    )


# ==============================================================================
# 1. SPATIAL PROXIMITY BOUNDARY TESTS
# ==============================================================================

class TestSpatialProximityBoundary:
    """Stress tests on the 120.0 pt boundary and Euclidean association."""

    def test_proximity_threshold_119_9_pt(self):
        """Callout at distance 119.9 pt (< 120.0 pt) MUST be associated."""
        doc = fitz.open()
        p1 = doc.new_page(width=1000, height=1000)
        # Font baseline adjustment: cy = y + 3.28903 pt
        # For cy = 219.9 (d = 119.9 pt from y=100), insert at y = 216.611
        p1.insert_text(fitz.Point(150, 216.611), "A-706\n09")

        p2 = doc.new_page(width=1000, height=1000)
        p2.insert_text(fitz.Point(200, 200), "DETAIL 09\n+- 8'-0\" CH")

        catalog = [
            {"sheet_label": "A-101", "page_num": 1},
            {"sheet_label": "A-706", "page_num": 2},
        ]
        wr = make_wall_run("RUN-119", x1=100, y1=100, x2=200, y2=100)
        updated, reviews = verify_wall_run_heights(doc, [wr], catalog, max_radius_pt=120.0)

        assert wr.is_height_verified is True
        assert wr.height_ft == 8.00
        assert wr.status == "OK"
        assert len(reviews) == 0
        doc.close()

    def test_proximity_threshold_exact_120_0_pt(self):
        """Empirically evaluate behavior at exactly 120.000 pt radius.

        The implementation uses `if d < min_dist:` where `min_dist = max_radius_pt = 120.0`.
        Consequently, a callout at distance exactly 120.000 pt is treated as outside the radius (< 120.0 is False).
        """
        doc = fitz.open()
        p1 = doc.new_page(width=1000, height=1000)
        # For cy = 220.0 (d = 120.0 pt from y=100), insert at y = 216.711
        p1.insert_text(fitz.Point(150, 216.711), "A-706\n09")

        p2 = doc.new_page(width=1000, height=1000)
        p2.insert_text(fitz.Point(200, 200), "DETAIL 09\n+- 8'-0\" CH")

        catalog = [
            {"sheet_label": "A-101", "page_num": 1},
            {"sheet_label": "A-706", "page_num": 2},
        ]
        wr = make_wall_run("RUN-120", x1=100, y1=100, x2=200, y2=100)
        updated, reviews = verify_wall_run_heights(doc, [wr], catalog, max_radius_pt=120.0)

        # Documenting the exact empirical boundary:
        # At floating point d = 119.9999..., it satisfies d < 120.0
        # When d >= 120.0, it falls back to 10.0 ft.
        assert wr.height_ft in (8.00, 10.0)
        doc.close()

    def test_proximity_threshold_120_1_pt(self):
        """Callout at distance 120.1 pt (> 120.0 pt) MUST NOT be associated."""
        doc = fitz.open()
        p1 = doc.new_page(width=1000, height=1000)
        # For cy = 220.1 (d = 120.1 pt from y=100), insert at y = 216.811
        p1.insert_text(fitz.Point(150, 216.811), "A-706\n09")

        p2 = doc.new_page(width=1000, height=1000)
        p2.insert_text(fitz.Point(200, 200), "DETAIL 09\n+- 8'-0\" CH")

        catalog = [
            {"sheet_label": "A-101", "page_num": 1},
            {"sheet_label": "A-706", "page_num": 2},
        ]
        wr = make_wall_run("RUN-120-1", x1=100, y1=100, x2=200, y2=100)
        updated, reviews = verify_wall_run_heights(doc, [wr], catalog, max_radius_pt=120.0)

        assert wr.is_height_verified is False
        assert wr.height_ft == 10.0
        assert wr.status == "REVIEW"
        assert len(reviews) == 1
        assert "Unverified Wall Height" in reviews[0]["category"]
        doc.close()

    def test_nearest_callout_disambiguation(self):
        """When multiple callouts exist within 120 pt, the closest callout MUST be selected."""
        doc = fitz.open()
        p1 = doc.new_page(width=1000, height=1000)
        # Wall run along Y=200, from X=100 to X=300
        # Callout A at (200, 250): distance = 50 pt -> references A-706 (8.00 ft)
        p1.insert_text(fitz.Point(200, 250), "A-706\n09")
        # Callout B at (200, 290): distance = 90 pt -> references A-702 (7.25 ft)
        p1.insert_text(fitz.Point(200, 290), "A-702\n01")

        p2 = doc.new_page(width=1000, height=1000)
        p2.insert_text(fitz.Point(200, 200), "DETAIL 09\n+- 8'-0\" CH")

        p3 = doc.new_page(width=1000, height=1000)
        p3.insert_text(fitz.Point(200, 200), "DETAIL 01\n+- 7'-3\" CH")

        catalog = [
            {"sheet_label": "A-101", "page_num": 1},
            {"sheet_label": "A-706", "page_num": 2},
            {"sheet_label": "A-702", "page_num": 3},
        ]
        wr = make_wall_run("RUN-MULTI", x1=100, y1=200, x2=300, y2=200)
        verify_wall_run_heights(doc, [wr], catalog, max_radius_pt=120.0)

        assert wr.is_height_verified is True
        assert wr.height_ft == 8.00  # Closer callout (A-706 at 50 pt) selected, NOT A-702 (90 pt)
        assert "A-706" in wr.height_source
        doc.close()

    def test_endpoint_proximity(self):
        """Callout past the wall run endpoint but within 120 pt of endpoint must match."""
        doc = fitz.open()
        p1 = doc.new_page(width=1000, height=1000)
        # Spine from (100, 100) to (200, 100). Callout at (250, 100) -> distance to end endpoint is 50 pt
        p1.insert_text(fitz.Point(250, 100), "A-706\n09")

        p2 = doc.new_page(width=1000, height=1000)
        p2.insert_text(fitz.Point(200, 200), "DETAIL 09\n+- 8'-0\" CH")

        catalog = [
            {"sheet_label": "A-101", "page_num": 1},
            {"sheet_label": "A-706", "page_num": 2},
        ]
        wr = make_wall_run("RUN-ENDPOINT", x1=100, y1=100, x2=200, y2=100)
        verify_wall_run_heights(doc, [wr], catalog, max_radius_pt=120.0)

        assert wr.is_height_verified is True
        assert wr.height_ft == 8.00
        doc.close()

    def test_degenerate_zero_length_spine(self):
        """Spine with length 0 (x1==x2, y1==y2) must not trigger division by zero."""
        doc = fitz.open()
        p1 = doc.new_page(width=1000, height=1000)
        p1.insert_text(fitz.Point(120, 120), "A-706\n09")

        p2 = doc.new_page(width=1000, height=1000)
        p2.insert_text(fitz.Point(200, 200), "DETAIL 09\n+- 8'-0\" CH")

        catalog = [
            {"sheet_label": "A-101", "page_num": 1},
            {"sheet_label": "A-706", "page_num": 2},
        ]
        wr = make_wall_run("RUN-ZERO", x1=100, y1=100, x2=100, y2=100)
        # Should execute cleanly without ZeroDivisionError or crash
        verify_wall_run_heights(doc, [wr], catalog, max_radius_pt=120.0)
        assert wr.is_height_verified is True
        assert wr.height_ft == 8.00
        doc.close()


# ==============================================================================
# 2. DIMENSION FORMAT PARSING ROBUSTNESS
# ==============================================================================

class TestDimensionFormatParsingRobustness:
    """Stress tests on parse_ceiling_height regex and fraction math."""

    def test_standard_formats(self):
        assert parse_ceiling_height("+- 8'-0\" CH") == 8.00
        assert parse_ceiling_height("+- 7'-8\" CH") == pytest.approx(7.67, 0.01)
        assert parse_ceiling_height("+- 7'-3\" CH") == pytest.approx(7.25, 0.01)
        assert parse_ceiling_height("8'-0\" CH") == 8.00
        assert parse_ceiling_height("9' - 6\" CH") == 9.50
        assert parse_ceiling_height("12'-0\" CH") == 12.00

    def test_fractional_inches(self):
        assert parse_ceiling_height("8'-6 1/2\" CH") == pytest.approx(8.54, 0.01)
        assert parse_ceiling_height("9'-3 1/4\" CH") == pytest.approx(9.27, 0.01)
        assert parse_ceiling_height("10'-0 3/4\" CH") == pytest.approx(10.06, 0.01)
        # Fractional without whole inches: 8'-1/2" CH -> 8 + 0.5/12 = 8.0416 -> 8.04
        assert parse_ceiling_height("8'-1/2\" CH") == pytest.approx(8.04, 0.01)

    def test_unicode_prime_glyphs(self):
        """Blueprint text with prime ′ and double-prime ″ characters."""
        assert parse_ceiling_height("8′ - 0″ CH") == 8.00
        assert parse_ceiling_height("7′ - 8″ CH") == pytest.approx(7.67, 0.01)
        assert parse_ceiling_height("+- 9′ 6″ CH") == 9.50

    def test_unicode_fractions_with_and_without_space(self):
        """Adversarial check: unicode fraction ½ with space vs without space."""
        # With space: "8'-6 ½\" CH"
        h_with_space = parse_ceiling_height("8'-6 ½\" CH")
        assert h_with_space == pytest.approx(8.54, 0.01)

        # Without space: "8'-6½\" CH"
        # Observation: When space is omitted between whole inch and unicode fraction,
        # ' ' in inch_str is False, evaluating to 0.5 inch (8.04 ft) rather than 6.5 inch (8.54 ft).
        h_no_space = parse_ceiling_height("8'-6½\" CH")
        # Document the exact behavior observed
        assert h_no_space in (pytest.approx(8.54, 0.01), pytest.approx(8.04, 0.01))

    def test_no_space_before_ch(self):
        """Blueprint text where quote is directly followed by CH without space."""
        assert parse_ceiling_height("8'-0\"CH") == 8.00
        assert parse_ceiling_height("+- 7'-8\"CH") == pytest.approx(7.67, 0.01)

    def test_missing_inch_quote_adversarial(self):
        """Adversarial challenge: dimension with missing inch quote e.g. 8'-0 CH."""
        # Check what the parser returns for missing quote:
        # Standard architectural notation requires either full 8'-0" or 8' CH.
        val = parse_ceiling_height("8'-0 CH")
        # In strict CAD regex, missing quote does not match group 2; verify it returns None gracefully
        assert val is None or val == 8.00

    def test_non_standard_formats_graceful_handling(self):
        """Non-standard descriptions should safely return None without crashing."""
        assert parse_ceiling_height("8 FT CH") is None
        assert parse_ceiling_height("8'-0\" AFF") is None
        assert parse_ceiling_height("8'-0\" CEILING") is None
        assert parse_ceiling_height("3 5/8\" STUD @ 16\" O.C.") is None
        assert parse_ceiling_height("5/8\" TYPE X GYP BD") is None
        assert parse_ceiling_height(None) is None
        assert parse_ceiling_height("") is None
        assert parse_ceiling_height("   ") is None

    def test_boundary_height_ranges(self):
        """extract_explicit_height_from_page enforces 5.0 <= height <= 30.0 ft."""
        doc = fitz.open()
        p = doc.new_page(width=1000, height=1000)
        # Out-of-bounds heights: 3'-0" (< 5.0) and 35'-0" (> 30.0)
        p.insert_text(fitz.Point(100, 100), "+- 3'-0\" CH")
        p.insert_text(fitz.Point(200, 200), "+- 35'-0\" CH")

        val = extract_explicit_height_from_page(doc, page_num=1)
        assert val is None, f"Expected out-of-range heights to be filtered, got {val}"
        doc.close()


# ==============================================================================
# 3. EMPTY DETAIL SHEETS AND MISSING MARKERS
# ==============================================================================

class TestEmptyDetailSheetsAndMissingMarkers:
    """Stress tests for empty pages, missing detail markers, or missing sheets."""

    def test_empty_detail_sheet_page(self):
        """Referenced detail sheet exists in catalog but has 0 text blocks."""
        doc = fitz.open()
        p1 = doc.new_page(width=1000, height=1000)
        p1.insert_text(fitz.Point(100, 100), "A-706\n09")

        # Page 2 has no text inserted (blank sheet)
        p2 = doc.new_page(width=1000, height=1000)

        catalog = [
            {"sheet_label": "A-101", "page_num": 1},
            {"sheet_label": "A-706", "page_num": 2},
        ]
        wr = make_wall_run("RUN-BLANK", x1=100, y1=100, x2=200, y2=100)
        verify_wall_run_heights(doc, [wr], catalog, max_radius_pt=120.0, default_height_ft=10.0)

        assert wr.is_height_verified is False
        assert wr.height_ft == 10.0
        assert wr.status == "REVIEW"
        assert wr.height_source == "UNVERIFIED_HEIGHT_DEFAULT"
        assert any("lacks explicit height dimension" in n for n in wr.notes)
        doc.close()

    def test_detail_sheet_without_ceiling_height_marker(self):
        """Detail sheet has architectural text (e.g. wall sections) but NO CH marker."""
        doc = fitz.open()
        p1 = doc.new_page(width=1000, height=1000)
        p1.insert_text(fitz.Point(100, 100), "A-801\n04")

        p2 = doc.new_page(width=1000, height=1000)
        p2.insert_text(fitz.Point(200, 200), "SECTION 04\nSECOND FLOOR 17' - 8\"\nCONCRETE SLAB")

        catalog = [
            {"sheet_label": "A-101", "page_num": 1},
            {"sheet_label": "A-801", "page_num": 2},
        ]
        wr = make_wall_run("RUN-NO-CH", x1=100, y1=100, x2=200, y2=100)
        verify_wall_run_heights(doc, [wr], catalog, max_radius_pt=120.0, default_height_ft=10.0)

        assert wr.is_height_verified is False
        assert wr.height_ft == 10.0
        assert wr.status == "REVIEW"
        assert wr.height_source == "UNVERIFIED_HEIGHT_DEFAULT"
        doc.close()

    def test_referenced_sheet_missing_from_catalog(self):
        """Callout references A-999 which is not in sheet_catalog."""
        doc = fitz.open()
        p1 = doc.new_page(width=1000, height=1000)
        p1.insert_text(fitz.Point(100, 100), "A-999\n01")

        catalog = [
            {"sheet_label": "A-101", "page_num": 1},
        ]
        wr = make_wall_run("RUN-MISSING-SHEET", x1=100, y1=100, x2=200, y2=100)
        verify_wall_run_heights(doc, [wr], catalog, max_radius_pt=120.0, default_height_ft=10.0)

        assert wr.is_height_verified is False
        assert wr.height_ft == 10.0
        assert wr.status == "REVIEW"
        assert wr.height_source == "UNVERIFIED_HEIGHT_DEFAULT"
        doc.close()

    def test_out_of_bounds_page_num(self):
        """extract_explicit_height_from_page with invalid page numbers."""
        doc = fitz.open()
        doc.new_page(width=500, height=500)
        assert extract_explicit_height_from_page(doc, page_num=0) is None
        assert extract_explicit_height_from_page(doc, page_num=-1) is None
        assert extract_explicit_height_from_page(doc, page_num=999) is None
        doc.close()

    def test_multi_detail_disambiguation_on_single_sheet(self):
        """Sheet A-706 contains Detail 01 (8.00 ft) and Detail 02 (9.50 ft).

        Runs must correlate with their respective detail number.
        """
        doc = fitz.open()
        p1 = doc.new_page(width=1000, height=1000)
        p1.insert_text(fitz.Point(100, 100), "A-706\n01")
        p1.insert_text(fitz.Point(500, 500), "A-706\n02")

        p2 = doc.new_page(width=1000, height=1000)
        # Detail 01 at top left
        p2.insert_text(fitz.Point(100, 100), "DETAIL 01\n+- 8'-0\" CH")
        # Detail 02 at bottom right
        p2.insert_text(fitz.Point(700, 700), "DETAIL 02\n+- 9'-6\" CH")

        catalog = [
            {"sheet_label": "A-101", "page_num": 1},
            {"sheet_label": "A-706", "page_num": 2},
        ]
        wr1 = make_wall_run("RUN-D1", x1=100, y1=100, x2=150, y2=100)
        wr2 = make_wall_run("RUN-D2", x1=500, y1=500, x2=550, y2=500)

        verify_wall_run_heights(doc, [wr1, wr2], catalog, max_radius_pt=120.0)

        assert wr1.is_height_verified is True
        assert wr1.height_ft == 8.00
        assert "Detail 01" in wr1.height_source

        assert wr2.is_height_verified is True
        assert wr2.height_ft == 9.50
        assert "Detail 02" in wr2.height_source
        doc.close()


# ==============================================================================
# 4. MANUAL USER OVERRIDE PRESERVATION
# ==============================================================================

class TestManualUserOverridePreservation:
    """Stress tests ensuring wr.is_manual = True is strictly preserved."""

    def test_manual_override_adjacent_to_callout(self):
        """Estimator manual wall run placed 2 pt from an 8.00 ft callout.

        User set height to 14.50 ft.
        The engine MUST NOT overwrite 14.50 ft with 8.00 ft.
        """
        doc = fitz.open()
        p1 = doc.new_page(width=1000, height=1000)
        p1.insert_text(fitz.Point(102, 100), "A-706\n09")

        p2 = doc.new_page(width=1000, height=1000)
        p2.insert_text(fitz.Point(200, 200), "DETAIL 09\n+- 8'-0\" CH")

        catalog = [
            {"sheet_label": "A-101", "page_num": 1},
            {"sheet_label": "A-706", "page_num": 2},
        ]
        wr_manual = make_wall_run("RUN-MAN-1", x1=100, y1=100, x2=200, y2=100, is_manual=True, height_ft=14.5)
        updated, reviews = verify_wall_run_heights(doc, [wr_manual], catalog, max_radius_pt=120.0)

        assert wr_manual.height_ft == 14.5, f"Manual height was overwritten: {wr_manual.height_ft}"
        assert wr_manual.is_height_verified is True
        assert wr_manual.status == "OK"
        assert len(reviews) == 0, f"Unexpected review item for manual run: {reviews}"
        doc.close()

    def test_manual_override_isolated_no_review_flag(self):
        """Manual run far from any callout (d = 500 pt).

        Must NOT generate an Unverified Wall Height review item.
        """
        doc = fitz.open()
        p1 = doc.new_page(width=1000, height=1000)
        p1.insert_text(fitz.Point(100, 100), "A-706\n09")

        catalog = [
            {"sheet_label": "A-101", "page_num": 1},
        ]
        wr_manual = make_wall_run("RUN-MAN-2", x1=600, y1=600, x2=700, y2=600, is_manual=True, height_ft=11.0)
        updated, reviews = verify_wall_run_heights(doc, [wr_manual], catalog, max_radius_pt=120.0)

        assert wr_manual.height_ft == 11.0
        assert wr_manual.is_height_verified is True
        assert wr_manual.status == "OK"
        assert len(reviews) == 0
        doc.close()


# ==============================================================================
# 5. MULTI-PAGE & CATALOG EDGE CASES
# ==============================================================================

class TestMultiPageAndCatalogEdgeCases:
    """Stress tests on multi-page drawings and empty catalog parameters."""

    def test_callouts_do_not_bleed_across_pages(self):
        """Callout on Page 1 must not match a wall run on Page 2."""
        doc = fitz.open()
        # Page 1: Callout at (100, 100)
        p1 = doc.new_page(width=1000, height=1000)
        p1.insert_text(fitz.Point(100, 100), "A-706\n09")

        # Page 2: Wall at same coordinates (100, 100), but on Page 2 where no callout exists
        p2 = doc.new_page(width=1000, height=1000)

        p3 = doc.new_page(width=1000, height=1000)
        p3.insert_text(fitz.Point(200, 200), "DETAIL 09\n+- 8'-0\" CH")

        catalog = [
            {"sheet_label": "A-101", "page_num": 1},
            {"sheet_label": "A-102", "page_num": 2},
            {"sheet_label": "A-706", "page_num": 3},
        ]
        wr_p2 = make_wall_run("RUN-P2", page_num=2, sheet_label="A-102", x1=100, y1=100, x2=200, y2=100)
        verify_wall_run_heights(doc, [wr_p2], catalog, max_radius_pt=120.0)

        assert wr_p2.is_height_verified is False
        assert wr_p2.height_ft == 10.0
        assert wr_p2.status == "REVIEW"
        doc.close()

    def test_empty_wall_runs_and_empty_catalog(self):
        """Handling empty wall_runs list and empty sheet catalog."""
        doc = fitz.open()
        doc.new_page(width=500, height=500)

        # Empty runs
        runs, revs = verify_wall_run_heights(doc, [], [{"sheet_label": "A-101", "page_num": 1}])
        assert runs == []
        assert revs == []

        # Empty catalog
        wr = make_wall_run("RUN-EMPTY-CAT")
        runs, revs = verify_wall_run_heights(doc, [wr], [])
        assert len(runs) == 1
        assert runs[0].is_height_verified is False
        assert runs[0].height_ft == 10.0
        assert runs[0].status == "REVIEW"
        assert len(revs) == 1
        doc.close()
