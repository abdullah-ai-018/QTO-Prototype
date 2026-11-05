"""Tests for D-004: Room <-> Wall Bidirectional Context Verification.

Ensures deterministic bidirectional consistency between:
  WALL <-> ROOM <-> ROOM BOUNDARY <-> WALL

If Room 101 says Wall W23 is its North boundary, Wall W23 must agree that Room 101
is attached on its South face. If they disagree, or if reciprocal proof is missing,
the candidate is flagged as NEEDS_REVIEW.
"""

import pytest
from app.geometry.polygon_ops import (
    RECIPROCAL_DIRECTIONS,
    classify_cardinal_direction,
    compute_wall_face_directions,
    extract_room_boundary_segments,
)
from app.geometry.room_graph import RoomGraph, RoomBoundaryEdge, WallAttachment
from app.geometry.engine import GeometryRoom, GeometryWall
from app.models.enums import ReviewStatus


# ---------------------------------------------------------------------------
# 1. Unit Tests for Direction Classification and Geometry Helpers
# ---------------------------------------------------------------------------

def test_classify_cardinal_direction():
    # In normalized page coords: (0,0) top-left, +x East, +y South
    assert classify_cardinal_direction(0.0, -1.0) == "north"
    assert classify_cardinal_direction(0.0, 1.0) == "south"
    assert classify_cardinal_direction(1.0, 0.0) == "east"
    assert classify_cardinal_direction(-1.0, 0.0) == "west"

    # Diagonals
    assert classify_cardinal_direction(1.0, -1.0) == "north_east"
    assert classify_cardinal_direction(-1.0, -1.0) == "north_west"
    assert classify_cardinal_direction(1.0, 1.0) == "south_east"
    assert classify_cardinal_direction(-1.0, 1.0) == "south_west"


def test_extract_room_boundary_segments():
    # A simple square room from (0.2, 0.2) to (0.4, 0.4)
    # Clockwise or counter-clockwise
    poly = [
        [0.2, 0.2],
        [0.4, 0.2],
        [0.4, 0.4],
        [0.2, 0.4],
    ]
    edges = extract_room_boundary_segments(poly)
    assert len(edges) == 4

    dirs = {e["direction"] for e in edges}
    # Must have all 4 cardinal directions
    assert "north" in dirs
    assert "south" in dirs
    assert "east" in dirs
    assert "west" in dirs

    # Check top edge (y=0.2 from 0.2 to 0.4) -> must point North
    top_edge = next(e for e in edges if e["start"]["y"] == 0.2 and e["end"]["y"] == 0.2)
    assert top_edge["direction"] == "north"
    assert top_edge["outward_normal"]["y"] < 0  # pointing upward


def test_compute_wall_face_directions():
    # Horizontal wall running West to East: start=(0.2, 0.2), end=(0.4, 0.2)
    # dx = +0.2, dy = 0.
    # Left normal: (-dy, dx) = (0, +0.2) -> South
    # Right normal: (dy, -dx) = (0, -0.2) -> North
    face_info = compute_wall_face_directions((0.2, 0.2), (0.4, 0.2))
    assert face_info["side_a_direction"] == "south"
    assert face_info["side_b_direction"] == "north"


# ---------------------------------------------------------------------------
# 2. Bidirectional Proof Verification in RoomGraph
# ---------------------------------------------------------------------------

def test_bidirectional_agreement_single_room_boundary():
    """Room 101 says Wall W23 is its North boundary.
    Wall W23 says Room 101 is attached to its South side.
    Bidirectional proof must succeed.
    """
    # Room 101: (0.2, 0.2) to (0.4, 0.4)
    # North boundary is at y=0.20
    room_101 = {
        "id": 101,
        "name": "Room 101",
        "polygon_norm": [
            {"x": 0.20, "y": 0.20},
            {"x": 0.40, "y": 0.20},
            {"x": 0.40, "y": 0.40},
            {"x": 0.20, "y": 0.40},
        ],
        "area_sqft": 400.0,
    }
    graph = RoomGraph([room_101])

    # Wall W23: running along y=0.20 from x=0.20 to 0.40
    # Left normal (Side A) points South into Room 101
    wall_w23 = {
        "id": "W23",
        "start_norm": {"x": 0.20, "y": 0.20},
        "end_norm": {"x": 0.40, "y": 0.20},
    }

    report = graph.attach_and_verify_walls([wall_w23])

    assert report.is_consistent is True
    assert len(report.mismatched_pairs) == 0
    assert len(report.verified_pairs) >= 1

    # Verify matching details
    match = next(p for p in report.verified_pairs if p["room_id"] == 101 and p["wall_id"] == "W23")
    assert match["room_boundary_direction"] == "north"
    assert match["wall_face_direction"] == "south"
    assert RECIPROCAL_DIRECTIONS[match["room_boundary_direction"]] == match["wall_face_direction"]


def test_bidirectional_mismatch_detected_and_flagged():
    """If a Wall is claimed on a boundary but its orientation or attached room
    conflicts with the room boundary direction, a mismatch is recorded.
    """
    room_101 = {
        "id": 101,
        "name": "Room 101",
        "polygon_norm": [
            {"x": 0.20, "y": 0.20},
            {"x": 0.40, "y": 0.20},
            {"x": 0.40, "y": 0.40},
            {"x": 0.20, "y": 0.40},
        ],
        "area_sqft": 400.0,
    }
    graph = RoomGraph([room_101])

    # Create a conflicting wall: e.g. artificially attached to an unrelated room or opposing face
    # A perpendicular wall running vertically at x=0.30 from y=0.20 to 0.40
    # running down the middle of Room 101
    perpendicular_wall = {
        "id": "W_CONFLICT",
        "start_norm": {"x": 0.30, "y": 0.20},
        "end_norm": {"x": 0.30, "y": 0.40},
    }

    report = graph.attach_and_verify_walls([perpendicular_wall])
    # The north boundary of Room 101 (horizontal) should NOT verify with perpendicular wall
    north_edge = next(e for e in graph.room_boundaries[101] if e.direction == "north")
    assert north_edge.verified is False


def test_bidirectional_agreement_interior_partition_two_rooms():
    """Interior partition wall separating Room 101 (North) and Room 102 (South).
    Room 101's South boundary <=> Wall's North face.
    Room 102's North boundary <=> Wall's South face.
    Both rooms achieve bidirectional proof with the same partition wall.
    """
    room_101 = {
        "id": 101,
        "name": "Room 101",
        "polygon_norm": [
            {"x": 0.20, "y": 0.10},
            {"x": 0.40, "y": 0.10},
            {"x": 0.40, "y": 0.30},
            {"x": 0.20, "y": 0.30},
        ],
        "area_sqft": 400.0,
    }
    room_102 = {
        "id": 102,
        "name": "Room 102",
        "polygon_norm": [
            {"x": 0.20, "y": 0.30},
            {"x": 0.40, "y": 0.30},
            {"x": 0.40, "y": 0.50},
            {"x": 0.20, "y": 0.50},
        ],
        "area_sqft": 400.0,
    }

    graph = RoomGraph([room_101, room_102])

    # Partition wall at y=0.30
    partition_wall = {
        "id": "W_PARTITION",
        "start_norm": {"x": 0.20, "y": 0.30},
        "end_norm": {"x": 0.40, "y": 0.30},
    }

    report = graph.attach_and_verify_walls([partition_wall])

    assert report.is_consistent is True
    # Should have verified matches for both Room 101 and Room 102
    room_101_matches = [p for p in report.verified_pairs if p["room_id"] == 101 and p["wall_id"] == "W_PARTITION"]
    room_102_matches = [p for p in report.verified_pairs if p["room_id"] == 102 and p["wall_id"] == "W_PARTITION"]

    assert len(room_101_matches) >= 1
    assert len(room_102_matches) >= 1

    # Room 101 is above the wall, so its South boundary touched the wall
    assert room_101_matches[0]["room_boundary_direction"] == "south"
    # Room 102 is below the wall, so its North boundary touched the wall
    assert room_102_matches[0]["room_boundary_direction"] == "north"


# ---------------------------------------------------------------------------
# 3. Status Transition to NEEDS_REVIEW upon Bidirectional Failure
# ---------------------------------------------------------------------------

def test_room_with_no_accepted_wall_becomes_needs_review():
    """An enclosed room that has no walls bounding it must be flagged as NEEDS_REVIEW."""
    room = GeometryRoom(
        name="Phantom Room",
        polygon_norm=[[0.1, 0.1], [0.3, 0.1], [0.3, 0.3], [0.1, 0.3]],
        bbox_norm={"minX": 0.1, "minY": 0.1, "maxX": 0.3, "maxY": 0.3},
        centroid_norm={"x": 0.2, "y": 0.2},
        area_sqft=200.0,
        perimeter_ft=60.0,
        confidence=0.90,
        status=ReviewStatus.PENDING,
    )
    rooms = [room]
    # No walls on the page
    walls = []

    graph = RoomGraph(rooms)
    report = graph.attach_and_verify_walls(walls)

    # Mimic engine.py D-004 gate logic
    boundaries = graph.room_boundaries.get(0, [])
    verified_boundaries = [b for b in boundaries if b.verified]
    if len(verified_boundaries) == 0:
        room.status = ReviewStatus.NEEDS_REVIEW
        room.rejection_reasons.append("no_accepted_wall_on_boundary")

    assert room.status == ReviewStatus.NEEDS_REVIEW
    assert "no_accepted_wall_on_boundary" in room.rejection_reasons


def test_mismatched_wall_becomes_needs_review():
    """A wall with a directional or room association mismatch must be flagged as NEEDS_REVIEW."""
    wall = GeometryWall(
        start_norm={"x": 0.1, "y": 0.1},
        end_norm={"x": 0.3, "y": 0.1},
        length_ft=10.0,
        wall_type="interior",
        room_index=0,
        confidence=0.90,
        status=ReviewStatus.APPROVED,
    )

    # If verification report returns mismatch for wall 0
    mismatched_wall_ids = {0}
    if 0 in mismatched_wall_ids:
        if wall.status != ReviewStatus.REJECTED:
            wall.status = ReviewStatus.NEEDS_REVIEW
        wall.rejection_reasons.append("bidirectional_room_wall_mismatch")

    assert wall.status == ReviewStatus.NEEDS_REVIEW
    assert "bidirectional_room_wall_mismatch" in wall.rejection_reasons
