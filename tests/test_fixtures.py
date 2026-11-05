"""test_fixtures.py: Verifies synthetic blueprint PDF fixtures.

Tests that all generated vector blueprints exist, open cleanly with PyMuPDF,
and contain expected vector linework, dimensions, text callouts, and scale metadata.
"""

from __future__ import annotations

import math
from pathlib import Path
import re
import pymupdf
import pytest

from tests.make_fixtures import (
    FIXTURES_DIR,
    build_all_fixtures,
    make_wall20_fixture,
    make_door_fixture,
    make_lumber_fixture,
    make_scale_fixture,
    make_multiwall_fixture,
)


@pytest.fixture(scope="session", autouse=True)
def ensure_fixtures():
    """Ensure all fixtures are generated before tests run."""
    build_all_fixtures(FIXTURES_DIR)


def test_fixture_files_exist():
    """Verify all 5 fixture PDFs exist on disk and have non-zero size."""
    expected_files = [
        "fixture_wall20.pdf",
        "fixture_door.pdf",
        "fixture_lumber.pdf",
        "fixture_scale.pdf",
        "fixture_multiwall.pdf",
    ]
    for filename in expected_files:
        path = FIXTURES_DIR / filename
        assert path.exists(), f"Missing fixture file: {filename}"
        assert path.stat().st_size > 500, f"Fixture file {filename} is suspiciously small ({path.stat().st_size} bytes)"


def test_fixture_wall20_structure():
    """Verify fixture_wall20.pdf geometry, scale, tags, and linework:

    - 20ft straight wall @ 1/8" = 1'-0" scale -> exactly 180 pt vector length.
    - Double face lines separated by 4 pt.
    - Tagged '1A' with callout and leader.
    - 10ft height specification in schedule notes.
    """
    path = FIXTURES_DIR / "fixture_wall20.pdf"
    doc = pymupdf.open(path)
    assert len(doc) == 1
    page = doc[0]

    # Verify text contents
    full_text = page.get_text()
    assert "1/8\" = 1'-0\"" in full_text
    assert "1A" in full_text
    assert "10'-0\" AFF" in full_text
    assert "3-5/8\" METAL STUDS" in full_text

    # Verify vector drawings
    drawings = page.get_drawings()
    assert len(drawings) >= 1

    lines = []
    for drw in drawings:
        for item in drw.get("items", []):
            if item[0] == "l":
                p1, p2 = item[1], item[2]
                length = math.hypot(p2.x - p1.x, p2.y - p1.y)
                lines.append((p1, p2, length))

    # Look for the two 180 pt horizontal wall lines (within 0.5 pt tolerance)
    wall_180_lines = [l for l in lines if abs(l[2] - 180.0) < 1.0]
    assert len(wall_180_lines) >= 2, f"Expected at least two 180 pt wall lines, found {len(wall_180_lines)}"

    # Check y-coordinates of the two wall lines (separated by 4 pt)
    y_coords = sorted([round(l[0].y, 1) for l in wall_180_lines])
    assert abs(y_coords[-1] - y_coords[0] - 4.0) < 0.5

    doc.close()


def test_fixture_door_geometry_and_arc():
    """Verify fixture_door.pdf:

    - 20ft total partition span (180 pt).
    - 3ft door opening (27 pt gap).
    - Two 8.5ft segments (76.5 pt each).
    - Door swing arc / leaf present.
    """
    path = FIXTURES_DIR / "fixture_door.pdf"
    doc = pymupdf.open(path)
    page = doc[0]

    # Verify schedule & tag text
    text = page.get_text()
    assert "1A" in text
    assert "3'-0\" X 7'-0\"" in text
    assert "1/8\" = 1'-0\"" in text

    drawings = page.get_drawings()
    lines = []
    curves = []
    for drw in drawings:
        for item in drw.get("items", []):
            if item[0] == "l":
                p1, p2 = item[1], item[2]
                length = math.hypot(p2.x - p1.x, p2.y - p1.y)
                lines.append((p1, p2, length))
            elif item[0] == "c":
                curves.append(item)

    # Check the 76.5 pt wall segment lines
    seg_lines = [l for l in lines if abs(l[2] - 76.5) < 1.0]
    assert len(seg_lines) >= 4, f"Expected 4 face lines of 76.5 pt (2 on each segment), found {len(seg_lines)}"

    # Check door leaf line (27 pt)
    door_leaf = [l for l in lines if abs(l[2] - 27.0) < 1.0]
    assert len(door_leaf) >= 1, "Door leaf line of 27 pt not found"

    # Check door swing arc (cubic Bezier curve)
    assert len(curves) >= 1, "Door swing arc curve not found in drawings"

    doc.close()


def test_fixture_lumber_negative_lookahead():
    """Verify fixture_lumber.pdf contains lumber callouts and wall tags,

    and verify that regex negative lookahead extracts tags without capturing lumber.
    """
    path = FIXTURES_DIR / "fixture_lumber.pdf"
    doc = pymupdf.open(path)
    page = doc[0]
    text = page.get_text()

    # Raw text must contain lumber notes and valid wall tags
    assert "2X4" in text
    assert "2X6" in text
    assert "1A" in text
    assert "2B" in text

    # Apply standard tag regex with negative lookahead for lumber sizes
    tag_regex_robust = re.compile(
        r"\b(?!\d+X\d+\b)([0-9][A-Z]|[1-9][A-Z][0-9]|GL[1-9]|PW)\b",
        re.IGNORECASE,
    )
    matches = tag_regex_robust.findall(text)
    unique_matches = set(m.upper() for m in matches)

    # Must find legitimate wall tags
    assert "1A" in unique_matches
    assert "2B" in unique_matches

    # Must NOT contain lumber dimensions
    for match in unique_matches:
        assert not re.match(r"^\d+X\d+$", match), f"Lumber dimension captured as wall tag: {match}"
        assert "2X4" not in match
        assert "2X6" not in match

    doc.close()


def test_fixture_scale_parsing():
    """Verify fixture_scale.pdf has explicit architectural scale notes."""
    path = FIXTURES_DIR / "fixture_scale.pdf"
    doc = pymupdf.open(path)
    page = doc[0]
    text = page.get_text()

    # Architectural scale variations present
    assert '1/8" = 1\'-0"' in text
    assert '1/4" = 1\'-0"' in text
    assert '3/16" = 1\'-0"' in text
    assert "1\" = 20'" in text

    # Verify graphic scale bar linework
    drawings = page.get_drawings()
    bar_lines = []
    for drw in drawings:
        for item in drw.get("items", []):
            if item[0] == "l":
                p1, p2 = item[1], item[2]
                length = math.hypot(p2.x - p1.x, p2.y - p1.y)
                bar_lines.append(length)

    # 4-inch scale bar is 288 pt long
    long_lines = [l for l in bar_lines if abs(l - 288.0) < 2.0]
    assert len(long_lines) >= 1, "Graphic scale bar baseline (288 pt) not found"

    doc.close()


def test_fixture_multiwall_junctions():
    """Verify fixture_multiwall.pdf contains intersecting walls and corners."""
    path = FIXTURES_DIR / "fixture_multiwall.pdf"
    doc = pymupdf.open(path)
    page = doc[0]
    text = page.get_text()

    assert "1A" in text
    assert "2B" in text
    assert '1/8" = 1\'-0"' in text

    drawings = page.get_drawings()
    lines = []
    for drw in drawings:
        for item in drw.get("items", []):
            if item[0] == "l":
                lines.append((item[1], item[2]))

    assert len(lines) >= 8, f"Expected at least 8 vector lines in multiwall plan, found {len(lines)}"

    # Check horizontal and vertical wall line orientations
    horiz_lines = [l for l in lines if abs(l[0].y - l[1].y) < 0.5 and abs(l[0].x - l[1].x) > 50]
    vert_lines = [l for l in lines if abs(l[0].x - l[1].x) < 0.5 and abs(l[0].y - l[1].y) > 50]

    assert len(horiz_lines) >= 3, f"Expected >=3 major horizontal wall lines, got {len(horiz_lines)}"
    assert len(vert_lines) >= 3, f"Expected >=3 major vertical wall lines, got {len(vert_lines)}"

    doc.close()
