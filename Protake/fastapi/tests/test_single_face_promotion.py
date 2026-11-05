"""Tests for D-011: Single-Face Evidence Promotion Engine.

Verifies the multi-signal context evidence ladder:
  Single Face
   ↓
  1. Room boundary?
   ↓
  2. Exterior envelope?
   ↓
  3. Elevation / Section reference?
   ↓
  4. Wall schedule / Spec match?
   ↓
  5. Opening attached?
   ↓
  6. Cross-sheet evidence?
   ↓
  CONFIRMED PHYSICAL WALL
"""

import pytest
from app.geometry.single_face_promotion import (
    SingleFaceContextEvidence,
    evaluate_single_face_promotion,
)
from app.models.architectural_wall import WallDecisionState
from app.models.enums import ReviewStatus
from app.trades.drywall_semantic import DrywallSemanticWallPipeline
from app.geometry.room_graph import RoomGraph


# ---------------------------------------------------------------------------
# 1. Unit Tests for Context Evidence Ladder Rungs
# ---------------------------------------------------------------------------

def test_single_face_room_boundary_and_corner_promoted():
    """Single-face candidate + Room boundary + Connected corner => PROMOTED."""
    ev = SingleFaceContextEvidence(
        has_room_boundary=True,
        is_bidirectional_verified=True,
        room_ids=[101],
        is_connected_at_corners=True,
        length_ft=12.0,
    )
    res = evaluate_single_face_promotion(ev)
    assert res.is_promoted is True
    assert res.promotion_tier == "PHYSICAL_WALL_CONFIRMED_SINGLE_SOURCE"
    assert res.recommended_confidence >= 0.75
    assert "bidirectional_room_boundary_verified" in res.matched_signals


def test_single_face_exterior_and_opening_promoted():
    """Single-face candidate + Exterior envelope + Door/Window opening => PROMOTED."""
    ev = SingleFaceContextEvidence(
        is_exterior_envelope=True,
        attached_openings_count=2,
        length_ft=20.0,
    )
    res = evaluate_single_face_promotion(ev)
    assert res.is_promoted is True
    assert res.promotion_tier == "PHYSICAL_WALL_CONFIRMED_SINGLE_SOURCE"
    assert "exterior_building_envelope" in res.matched_signals
    assert "attached_openings_count:2" in res.matched_signals


def test_single_face_schedule_match_and_tag_promoted():
    """Single-face candidate + Wall Tag + Partition Schedule Spec => PROMOTED."""
    ev = SingleFaceContextEvidence(
        has_wall_tag=True,
        wall_tag="Type A",
        has_schedule_match=True,
        assembly_verified=True,
        has_room_boundary=True,
        length_ft=8.0,
    )
    res = evaluate_single_face_promotion(ev)
    assert res.is_promoted is True
    assert "verified_partition_schedule_match" in res.matched_signals


def test_single_face_detail_callout_and_elevation_promoted():
    """Single-face candidate + Detail bubble ('3/A401') + Room boundary => PROMOTED."""
    ev = SingleFaceContextEvidence(
        has_elevation_ref=True,
        has_detail_callout_ref=True,
        callout_tags=["3/A401"],
        has_room_boundary=True,
        room_ids=[101],
        length_ft=10.0,
    )
    res = evaluate_single_face_promotion(ev)
    assert res.is_promoted is True
    assert any("elevation_or_detail_callout" in s for s in res.matched_signals)


def test_single_face_cross_sheet_rcp_promoted():
    """Single-face candidate + Cross-sheet RCP height match + Room boundary => PROMOTED."""
    ev = SingleFaceContextEvidence(
        has_rcp_height_match=True,
        has_cross_sheet_evidence=True,
        has_room_boundary=True,
        room_ids=[102],
        is_connected_at_corners=True,
        length_ft=14.0,
    )
    res = evaluate_single_face_promotion(ev)
    assert res.is_promoted is True
    assert "cross_sheet_document_evidence" in res.matched_signals


def test_single_face_isolated_noise_not_promoted():
    """Isolated single-face stub without any contextual evidence => NOT PROMOTED."""
    ev = SingleFaceContextEvidence(
        has_room_boundary=False,
        is_exterior_envelope=False,
        attached_openings_count=0,
        has_wall_tag=False,
        has_schedule_match=False,
        has_elevation_ref=False,
        is_connected_at_corners=False,
        length_ft=1.5,
    )
    res = evaluate_single_face_promotion(ev)
    assert res.is_promoted is False
    assert res.promotion_tier == "unpromoted"
    assert "insufficient_context" in res.diagnostic_reason


# ---------------------------------------------------------------------------
# 2. Integration Test with Semantic Takeoff Engine
# ---------------------------------------------------------------------------

def test_drywall_semantic_single_face_promotion_and_qto_eligibility():
    """A single-face wall with room boundary support and an opening is promoted to
    PHYSICAL_WALL_CONFIRMED_SINGLE_SOURCE, status='approved', and qto_eligible=True.
    """
    pipeline = DrywallSemanticWallPipeline(allow_defaults=True)

    room_101 = {
        "id": 101,
        "name": "Office 101",
        "polygon_norm": [
            {"x": 0.20, "y": 0.20},
            {"x": 0.40, "y": 0.20},
            {"x": 0.40, "y": 0.40},
            {"x": 0.20, "y": 0.40},
        ],
        "area_sqft": 400.0,
    }
    rooms = [room_101]
    room_graph = RoomGraph(rooms)

    # Mock wall: single-face (no face_b) bounding Room 101 on North (y=0.20)
    class MockWall:
        id = 1
        page_id = 1
        start_norm = {"x": 0.20, "y": 0.20}
        end_norm = {"x": 0.40, "y": 0.20}
        length_ft = 10.0
        height_ft = 9.0
        thickness_ft = 0.416
        thickness_measured = False
        face_a_segment_id = 100
        face_b_segment_id = None  # Single face!
        face_a_coords = None
        face_b_coords = None
        status = ReviewStatus.NEEDS_REVIEW
        source = "hough_segment"
        wall_type = "interior"
        wall_type_code = None
        height_source = "ASSUMED"
        bidirectional_verified = True

    wall = MockWall()
    import networkx as nx
    graph = nx.Graph()
    graph.add_node(1)

    aw = pipeline._evaluate_architectural_wall(
        wall=wall,
        room_graph=room_graph,
        graph=graph,
        wall_tags=[],
        classifications={},
        default_tag="Type A",
        ref_sched_sheet=None,
    )

    # Should be promoted by context evidence (room boundary verified)
    assert aw.decision_state == WallDecisionState.PHYSICAL_WALL_CONFIRMED_SINGLE_SOURCE
    assert aw.status == "approved"
    assert aw.qto_eligible is True
    assert aw.qto_block_reason is None
    assert aw.source_evidence.get("single_face_promoted") is True
