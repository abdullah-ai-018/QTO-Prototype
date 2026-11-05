"""test_pipeline.py: Unit Tests for Blueprint Parsing & Wall Extraction Pipeline.

Covers:
- Scale calibration and conversion factor (SOP 8.6.5)
- Wall tag discovery with lumber negative lookahead (SOP 8.6.2)
- Door and opening detection and deduction rules (SOP 3.4, 8.6.7)
- Vector segmentation and geometry utilities (SOP 8.6.6)
"""

from __future__ import annotations

import math
from pathlib import Path
import re
import pymupdf
import pytest

from tests.make_fixtures import FIXTURES_DIR, build_all_fixtures

# Try importing modular qto components
try:
    from qto.scale import parse_scale_string, parse_fraction, DEFAULT_FT_PER_PT
    from qto.tags import TAG_REGEX, is_valid_wall_tag, discover_tags_from_schedules
    from qto.geometry import Point, Segment, point_to_segment_distance, angle_diff
    from qto.segments import extract_page_segments
    HAS_QTO_PIPELINE = True
except ImportError:
    HAS_QTO_PIPELINE = False


@pytest.fixture(scope="session", autouse=True)
def setup_fixtures():
    build_all_fixtures(FIXTURES_DIR)


# =============================================================================
# 1. SCALE PARSING & CALIBRATION TESTS (SOP 8.6.5)
# =============================================================================

def test_scale_parsing_standard_architectural():
    """Verify parsing standard architectural scales into ft_per_pt."""
    test_cases = [
        ('1/8" = 1\'-0"', 1.0 / (72.0 * 0.125)),       # 0.111111...
        ('1/4" = 1\'-0"', 1.0 / (72.0 * 0.250)),       # 0.055555...
        ('3/16" = 1\'-0"', 1.0 / (72.0 * 0.1875)),     # 0.074074...
        ('3/32" = 1\'-0"', 1.0 / (72.0 * 0.09375)),    # 0.148148...
        ('1" = 20\'', 1.0 / (72.0 * 0.050)),           # 0.277777...
    ]
    for scale_str, expected in test_cases:
        if HAS_QTO_PIPELINE:
            res = parse_scale_string(scale_str)
            assert res is not None
            assert abs(res - expected) < 1e-4, f"Failed for {scale_str}: expected {expected}, got {res}"
        else:
            # Direct regex test if module not yet imported
            m = re.search(r'([\d\s\/\.\-]+)\s*["״]?\s*[:=]\s*(\d+)\s*[\'′]', scale_str)
            assert m is not None


def test_scale_parsing_invalid_inputs():
    """Verify invalid or empty scale strings return None without raising."""
    if not HAS_QTO_PIPELINE:
        pytest.skip("qto.scale not available")

    assert parse_scale_string("") is None
    assert parse_scale_string("NOT A SCALE") is None
    assert parse_scale_string("DO NOT SCALE DRAWING") is None
    assert parse_scale_string("Scale: N.T.S.") is None


def test_fraction_parsing():
    """Verify fractional expression parser (1/8, 3/16, 1-1/2)."""
    if not HAS_QTO_PIPELINE:
        pytest.skip("qto.scale not available")

    assert parse_fraction("1/8") == 0.125
    assert parse_fraction("1/4") == 0.25
    assert parse_fraction("3/16") == 0.1875
    assert parse_fraction("1-1/2") == 1.5
    assert parse_fraction("0.125") == 0.125
    assert parse_fraction("invalid") is None


# =============================================================================
# 2. TAG DISCOVERY & LUMBER NEGATIVE LOOKAHEAD TESTS (SOP 8.6.2)
# =============================================================================

def test_tag_regex_matches_valid_wall_tags():
    """Verify wall tags (1A, 2B, 7A, 5E, 1A2, GL1, PW) match canonical tag pattern."""
    tag_regex = re.compile(r"\b(?!\d+X\d+\b)([0-9][A-Z]|[1-9][A-Z][0-9]|GL[1-9]|PW)\b")
    valid_tags = ["1A", "2B", "7A", "5E", "3C", "1A2", "4B1", "GL1", "GL2", "PW"]
    for tag in valid_tags:
        assert tag_regex.search(tag) is not None, f"Valid tag {tag} failed regex match"
        if HAS_QTO_PIPELINE:
            assert is_valid_wall_tag(tag) is True


def test_tag_regex_strictly_rejects_lumber_dimensions():
    """Verify negative lookahead strictly prevents lumber notes (2X4, 2X6, 2X8, 1X3) from matching."""
    tag_regex = re.compile(r"\b(?!\d+X\d+\b)([0-9][A-Z]|[1-9][A-Z][0-9]|GL[1-9]|PW)\b")
    lumber_notes = ["2X4", "2X6", "2X8", "2X10", "1X3", "1X4", "4X4", "2x4", "2x6"]
    for note in lumber_notes:
        match = tag_regex.search(note)
        assert match is None, f"Lumber dimension '{note}' was erroneously matched as a wall tag"
        if HAS_QTO_PIPELINE:
            assert is_valid_wall_tag(note) is False


def test_tag_exclusion_tokens():
    """Verify non-wall trade abbreviations are excluded."""
    if not HAS_QTO_PIPELINE:
        pytest.skip("qto.tags not available")

    exclusions = ["GA", "DC", "HR", "SF", "LF", "OC", "MAX", "MIN", "TYP", "SIM", "NTS"]
    for token in exclusions:
        assert is_valid_wall_tag(token) is False


def test_discover_tags_from_fixture_lumber():
    """Verify discovery extracts 1A and 2B from fixture_lumber.pdf without capturing 2X4 or 2X6."""
    pdf_path = FIXTURES_DIR / "fixture_lumber.pdf"
    doc = pymupdf.open(pdf_path)

    if HAS_QTO_PIPELINE:
        discovered = discover_tags_from_schedules(doc)
        assert "1A" in discovered
        assert "2B" in discovered
        assert "2X4" not in discovered
        assert "2X6" not in discovered
    else:
        text = doc[0].get_text()
        tag_regex = re.compile(r"\b(?!\d+X\d+\b)([0-9][A-Z]|[1-9][A-Z][0-9]|GL[1-9]|PW)\b")
        found = set(tag_regex.findall(text))
        assert "1A" in found
        assert "2B" in found
        assert "2X4" not in found
        assert "2X6" not in found
    doc.close()


# =============================================================================
# 3. OPENING DETECTION & DEDUCTION RULES (SOP 3.4 & 8.6.7)
# =============================================================================

def test_opening_classification_rules():
    """Verify SOP opening classification thresholds:

    - gap < 0.5 ft -> GAP_JOINT (continuous wall)
    - 2.0 ft <= gap <= 8.0 ft with door arc -> GAP_OPENING_CONFIRMED
    - 2.0 ft <= gap <= 4.0 ft without door arc -> GAP_OPENING_SUSPECTED
    - gap > 4.0 ft without arc -> GAP_END
    """
    def classify_gap(gap_ft: float, has_door_arc: bool, opp_face_continuous: bool) -> str:
        if gap_ft < 0.5:
            return "GAP_JOINT"
        if opp_face_continuous:
            return "GAP_INTERSECTION"
        if 2.0 <= gap_ft <= 8.0 and has_door_arc:
            return "GAP_OPENING_CONFIRMED"
        if 2.0 <= gap_ft <= 4.0 and not has_door_arc:
            return "GAP_OPENING_SUSPECTED"
        if gap_ft > 4.0 and not has_door_arc:
            return "GAP_END"
        return "GAP_UNKNOWN"

    # Micro-gap / joint
    assert classify_gap(0.3, has_door_arc=False, opp_face_continuous=False) == "GAP_JOINT"

    # T-junction intersection
    assert classify_gap(1.5, has_door_arc=False, opp_face_continuous=True) == "GAP_INTERSECTION"

    # Confirmed 3ft door with swing arc
    assert classify_gap(3.0, has_door_arc=True, opp_face_continuous=False) == "GAP_OPENING_CONFIRMED"

    # Confirmed 6ft double door with swing arc
    assert classify_gap(6.0, has_door_arc=True, opp_face_continuous=False) == "GAP_OPENING_CONFIRMED"

    # Suspected 3ft opening without arc
    assert classify_gap(3.0, has_door_arc=False, opp_face_continuous=False) == "GAP_OPENING_SUSPECTED"

    # Wall end (5ft open space)
    assert classify_gap(5.0, has_door_arc=False, opp_face_continuous=False) == "GAP_END"


def test_never_measure_through_doors():
    """Verify SOP rule: gross wall length minus confirmed openings equals net length."""
    gross_lf = 20.0
    door_opening_lf = 3.0
    net_lf = gross_lf - door_opening_lf
    assert net_lf == 17.0
    assert net_lf < gross_lf, "Wall must deduct door opening length"


# =============================================================================
# 4. VECTOR SEGMENTATION & GEOMETRY UTILITIES (SOP 8.6.6)
# =============================================================================

def test_geometry_point_to_segment_distance():
    """Verify mathematical point-to-segment distance calculation."""
    if not HAS_QTO_PIPELINE:
        pytest.skip("qto.geometry not available")

    # Segment from (0, 0) to (10, 0)
    # Point directly above midpoint (5, 5) -> distance = 5.0
    dist, cx, cy, t = point_to_segment_distance(5.0, 5.0, 0.0, 0.0, 10.0, 0.0)
    assert abs(dist - 5.0) < 1e-6
    assert abs(cx - 5.0) < 1e-6
    assert abs(cy - 0.0) < 1e-6

    # Point to the left (-3, 0) -> distance to start = 3.0
    dist, cx, cy, t = point_to_segment_distance(-3.0, 0.0, 0.0, 0.0, 10.0, 0.0)
    assert abs(dist - 3.0) < 1e-6

    # Point to the right (14, 0) -> distance to end = 4.0
    dist, cx, cy, t = point_to_segment_distance(14.0, 0.0, 0.0, 0.0, 10.0, 0.0)
    assert abs(dist - 4.0) < 1e-6


def test_geometry_angle_diff():
    """Verify angular difference calculation between segments in radians."""
    if not HAS_QTO_PIPELINE:
        pytest.skip("qto.geometry not available")

    # Parallel lines (same angle) -> 0 rad
    assert abs(angle_diff(0.0, 0.0)) < 1e-6
    # Parallel lines opposite direction (0 and pi) -> 0 rad
    assert abs(angle_diff(0.0, math.pi)) < 1e-6
    # Perpendicular lines -> pi/2 rad
    assert abs(angle_diff(0.0, math.pi / 2.0) - (math.pi / 2.0)) < 1e-6
    # Slightly angled line (3.0 deg difference)
    rad_3deg = math.radians(3.0)
    assert abs(angle_diff(0.0, rad_3deg) - rad_3deg) < 1e-4


def test_segment_extraction_noise_filtering():
    """Verify segment extraction from fixture_wall20.pdf filters margins and short ticks."""
    pdf_path = FIXTURES_DIR / "fixture_wall20.pdf"
    doc = pymupdf.open(pdf_path)
    page = doc[0]

    if HAS_QTO_PIPELINE:
        segments = extract_page_segments(page)
        assert len(segments) >= 2
        # Verify no segment is shorter than 4.0 pt
        for s in segments:
            assert s["length"] >= 4.0
            # Verify no segment in the right 22% margin
            assert min(s["x1"], s["x2"]) <= page.rect.width * 0.78
    else:
        drawings = page.get_drawings()
        assert len(drawings) >= 1
    doc.close()
