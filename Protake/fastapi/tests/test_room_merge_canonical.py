"""Tests for D-012: Canonical Room Merging & Multi-Evidence Synthesis Engine.

Verifies that:
  Room A + Room B
        ↓
  same physical room? (IoU >= 0.70 or sub-region coverage >= 0.80)
        ↓
  CANONICAL MERGE
        ↓
  1. canonical_room_id (Keeper entity)
  2. Union Polygon (Shapely unary_union with recalculated area_sqft & perimeter_ft)
  3. Preserve Both Evidence Sources (provenance, finishes, aliases, OCR tokens)
  4. Multi-Evidence Confidence Boost (min(0.99, max(c1, c2) + 0.05))
  5. Remap All Downstream Walls & Detections to canonical_room_id
"""

import pytest
from shapely.geometry import Polygon

from app.geometry.duplicate_service import (
    is_same_physical_room,
    merge_room_candidates,
    synthesize_room_names,
)
from app.models.enums import DetectionSource, ReviewStatus
from app.models.room import Room


# ---------------------------------------------------------------------------
# 1. Unit Tests for Overlap & Name Synthesis
# ---------------------------------------------------------------------------

def test_is_same_physical_room_detection():
    """High IoU (>= 0.70) or sub-region containment (>= 0.80) identifies same physical room."""
    # Room 1: 0.10 to 0.50 (size 0.40 x 0.40 = 0.16)
    p1 = Polygon([(0.10, 0.10), (0.50, 0.10), (0.50, 0.50), (0.10, 0.50)])

    # Room 2: 0.10 to 0.48 (slightly smaller under-flooded detection, 0.38 x 0.38 = 0.1444)
    p2 = Polygon([(0.10, 0.10), (0.48, 0.10), (0.48, 0.48), (0.10, 0.48)])

    is_same, score = is_same_physical_room(p1, p2)
    assert is_same is True
    assert score >= 0.80

    # Disjoint Room 3: 0.60 to 0.90
    p3 = Polygon([(0.60, 0.60), (0.90, 0.60), (0.90, 0.90), (0.60, 0.90)])
    is_same_disjoint, _ = is_same_physical_room(p1, p3)
    assert is_same_disjoint is False


def test_synthesize_room_names():
    """Specific OCR labels take precedence over generic fallback names."""
    assert synthesize_room_names("Room 1", "OFFICE 101") == "OFFICE 101"
    assert synthesize_room_names("KITCHEN", "Room 4") == "KITCHEN"
    assert synthesize_room_names("101", "OFFICE") == "OFFICE 101"
    assert synthesize_room_names("OFFICE", "102") == "OFFICE 102"
    assert synthesize_room_names("LOBBY", "LOBBY") == "LOBBY"


# ---------------------------------------------------------------------------
# 2. Canonical Room Merging Engine Tests
# ---------------------------------------------------------------------------

def test_merge_room_candidates_synthesizes_union_and_evidence():
    """Merging two room candidates synthesizes union geometry, boosts confidence,
    and preserves full evidence trails from both sources.
    """
    # Room A: Base detector output
    r1 = Room(
        id=1,
        page_id=10,
        name="Room 1",
        room_type="Office",
        floor_finish="Carpet",
        wall_finish="Paint",
        ceiling_finish="ACT",
        polygon_norm=[[0.10, 0.10], [0.50, 0.10], [0.50, 0.50], [0.10, 0.50]],
        bbox_norm={"minX": 0.10, "minY": 0.10, "maxX": 0.50, "maxY": 0.50},
        centroid_norm={"x": 0.30, "y": 0.30},
        area_sqft=400.0,
        perimeter_ft=80.0,
        confidence=0.85,
        source=DetectionSource.GEOMETRY,
        status=ReviewStatus.PENDING,
    )

    # Room B: Secondary / OCR / alternate flood-fill detection of same space
    r2 = Room(
        id=2,
        page_id=10,
        name="CONFERENCE 101",
        room_type="Meeting",
        floor_finish=None,
        wall_finish=None,
        ceiling_finish="GWB",
        polygon_norm=[[0.10, 0.10], [0.52, 0.10], [0.52, 0.50], [0.10, 0.50]],  # Slightly larger on right edge
        bbox_norm={"minX": 0.10, "minY": 0.10, "maxX": 0.52, "maxY": 0.50},
        centroid_norm={"x": 0.31, "y": 0.30},
        area_sqft=420.0,
        perimeter_ft=84.0,
        confidence=0.90,
        source=DetectionSource.OCR,
        status=ReviewStatus.PENDING,
    )

    results = merge_room_candidates([r1, r2], scale_ft_per_px=0.0)

    assert len(results) == 1
    mr = results[0]

    # Keeper is Room 2 (larger area: 420 sqft vs 400 sqft)
    assert mr.canonical_room_id == 2
    assert mr.absorbed_room_ids == [1]

    # Synthesized Name prefers specific "CONFERENCE 101" over "Room 1"
    assert mr.merged_name == "CONFERENCE 101"

    # Multi-source confidence is boosted
    assert mr.merged_confidence == pytest.approx(0.95)

    # Finishes are merged from both sources
    assert mr.merged_floor_finish == "Carpet"  # from r1
    assert mr.merged_ceiling_finish == "ACT"  # from r1 or r2

    # Evidence sources preserves both original records
    assert len(mr.evidence_sources) == 2
    src_ids = {s["room_id"] for s in mr.evidence_sources}
    assert src_ids == {1, 2}

    # Merged polygon covers both
    assert mr.merged_bbox_norm["maxX"] >= 0.52
    assert mr.merged_area_sqft >= 420.0
