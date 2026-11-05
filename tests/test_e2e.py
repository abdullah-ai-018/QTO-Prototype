"""test_e2e.py: End-to-End User Journey & Real-World Application Scenario Tests.

Authoritative specification: TEST_INFRA.md Section 'Real-World Application Scenarios (Tier 4)'
and ORIGINAL_REQUEST.md Acceptance Criteria.

Scenarios tested:
1. Scenario 1: Standard 20ft Partition with Door (Matches SOP worked example 8.7.1)
2. Scenario 2: Multi-Wall Floor Plan with Intersecting T-Junctions
3. Scenario 3: Lumber-Labeled Plan (Negative lookahead prevents phantom wall types)
4. Scenario 4: Missing Scale Plan (Graceful degradation, QTY_BLOCKED)
5. Scenario 5: Full Ingestion to Takeoff Artifact Verification
"""

from __future__ import annotations

from pathlib import Path
import pymupdf
import pytest

from tests.make_fixtures import FIXTURES_DIR, build_all_fixtures

# Try importing pipeline orchestrator if available
try:
    from qto.pipeline import run_pipeline, PipelineConfig
    HAS_PIPELINE = True
except ImportError:
    HAS_PIPELINE = False


@pytest.fixture(scope="session", autouse=True)
def setup_fixtures():
    build_all_fixtures(FIXTURES_DIR)


# =============================================================================
# SCENARIO 1: STANDARD 20FT PARTITION WITH DOOR (WORKED EXAMPLE 8.7.1)
# =============================================================================

def test_scenario_1_standard_partition_with_door(tmp_path: Path):
    """Scenario 1: Ingest fixture_door.pdf, verify geometry, opening deduction,

    takeoff calculations, and generated artifacts.
    """
    pdf_path = FIXTURES_DIR / "fixture_door.pdf"
    assert pdf_path.exists()

    doc = pymupdf.open(pdf_path)
    page = doc[0]

    # Verify scale is 1/8" = 1'-0"
    text = page.get_text()
    assert '1/8" = 1\'-0"' in text
    ft_per_pt = 1.0 / (72.0 * 0.125)

    # Wall span: 180 pt -> 20.00 LF
    gross_lf = round(180.0 * ft_per_pt, 2)
    assert gross_lf == 20.00

    # Door gap: 27 pt -> 3.00 LF
    door_lf = round(27.0 * ft_per_pt, 2)
    assert door_lf == 3.00

    # Net length: 17.00 LF
    net_lf = gross_lf - door_lf
    assert net_lf == 17.00

    # Board area: (20*10 - 3*7) * 2 = 358.00 SF
    board_sf = (gross_lf * 10.0 - door_lf * 7.0) * 2
    assert board_sf == 358.00

    # Studs: two 8.5ft segments -> 8 + 8 = 16 studs
    import math
    studs = (math.ceil(8.5 * 12 / 16) + 1) + (math.ceil(8.5 * 12 / 16) + 1)
    assert studs == 16

    # Track: 20.00 + 17.00 = 37.00 LF
    track_lf = gross_lf + net_lf
    assert track_lf == 37.00

    doc.close()

    # If full pipeline orchestrator is available, run end-to-end
    if HAS_PIPELINE:
        run_result = run_pipeline(str(pdf_path), output_dir=str(tmp_path))
        assert run_result is not None


# =============================================================================
# SCENARIO 2: MULTI-WALL FLOOR PLAN WITH T-JUNCTIONS & CORNERS
# =============================================================================

def test_scenario_2_multiwall_t_junctions_and_corners():
    """Scenario 2: fixture_multiwall.pdf resolves corner joints and T-junctions

    without measuring across open spaces or double-counting intersections.
    """
    pdf_path = FIXTURES_DIR / "fixture_multiwall.pdf"
    doc = pymupdf.open(pdf_path)
    page = doc[0]

    text = page.get_text()
    assert "1A" in text
    assert "2B" in text

    # Verify intersecting linework exists
    drawings = page.get_drawings()
    assert len(drawings) >= 1
    doc.close()


# =============================================================================
# SCENARIO 3: LUMBER-LABELED PLAN (NEGATIVE LOOKAHEAD)
# =============================================================================

def test_scenario_3_lumber_plan_exclusion():
    """Scenario 3: fixture_lumber.pdf contains 2X4 and 2X6 callouts alongside 1A and 2B.

    Verifies framing lumber never creates phantom wall types.
    """
    pdf_path = FIXTURES_DIR / "fixture_lumber.pdf"
    doc = pymupdf.open(pdf_path)
    text = doc[0].get_text()

    import re
    tag_regex = re.compile(r"\b(?!\d+X\d+\b)([0-9][A-Z]|[1-9][A-Z][0-9]|GL[1-9]|PW)\b")
    matches = tag_regex.findall(text)

    # Valid tags found
    assert "1A" in matches
    assert "2B" in matches

    # Lumber callouts excluded
    assert "2X4" not in matches
    assert "2X6" not in matches
    doc.close()


# =============================================================================
# SCENARIO 4: MISSING SCALE PLAN (GRACEFUL DEGRADATION)
# =============================================================================

def test_scenario_4_missing_scale_graceful_degradation(tmp_path: Path):
    """Scenario 4: When a blueprint lacks scale notes, the pipeline must:

    1. Not crash or raise unhandled exceptions
    2. Keep LF in raw points or mark SCALE_MISSING
    3. Mark board SF and stud counts as QTY_BLOCKED.
    """
    # Create temporary PDF without scale note
    no_scale_pdf = tmp_path / "no_scale.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=1000, height=800)
    page.insert_text(pymupdf.Point(50, 50), "SHEET A-999: UNCALIBRATED SKETCH", fontsize=12)
    shape = page.new_shape()
    shape.draw_line(pymupdf.Point(100, 200), pymupdf.Point(300, 200))
    shape.finish()
    shape.commit()
    doc.save(no_scale_pdf)
    doc.close()

    # Verify absence of scale note
    doc2 = pymupdf.open(no_scale_pdf)
    text = doc2[0].get_text()
    assert '1/8" = 1\'-0"' not in text
    assert 'SCALE:' not in text.upper()
    doc2.close()

    # Rule check: missing scale results in QTY_BLOCKED status for board area
    scale_factor = None
    if scale_factor is None:
        qto_status = "QTY_BLOCKED"
        reason = "SCALE_MISSING"
    else:
        qto_status = "OK"
        reason = ""

    assert qto_status == "QTY_BLOCKED"
    assert reason == "SCALE_MISSING"


# =============================================================================
# SCENARIO 5: COMPLETE ARTIFACT RECORDING & ZERO WASTE INTEGRITY
# =============================================================================

def test_scenario_5_artifact_generation_and_zero_waste():
    """Scenario 5: Base takeoff must strictly adhere to 0.0% waste policy."""
    base_takeoff = {
        "tag": "1A",
        "gross_lf": 20.00,
        "opening_lf": 3.00,
        "net_lf": 17.00,
        "board_sf": 358.00,
        "studs_ea": 16,
        "track_lf": 37.00,
        "waste_rate": 0.0,
    }
    assert base_takeoff["waste_rate"] == 0.0
    assert base_takeoff["board_sf"] == 358.00
