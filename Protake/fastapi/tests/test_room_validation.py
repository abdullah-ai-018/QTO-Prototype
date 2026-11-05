"""Tests for the room-side accept/reject gate (room_validation.py) — the
room half of the same gap wall_validation.py closed earlier this session
(see REPOSITORY_AUDIT_AND_MIGRATION_PLAN.md, Finding F2).

Covers:
  1. Outside-drawing-zone rejects, mirroring the wall gate exactly.
  2. Low wall-contact rejects, using the measured separation margin already
     documented in polygon_ops.py (real rooms 0.575-0.926, false positives
     0.000-0.131).
  3. wall_verified=False (synthetic label-bisector cut) alone does NOT
     reject — stays PENDING, only capped in confidence.
  4. Low rectilinearity alone does NOT reject — irregular/L-shaped rooms
     are architecturally normal.
  5. wall_contact=None (covered exterior areas) never triggers the
     low-wall-contact reject path.
  6. Confidence value returned matches room_confidence() exactly — no
     drift introduced by the gate.
"""

import pytest

from app.geometry.polygon_ops import MIN_WALL_CONTACT_FOR_HIGH_CONFIDENCE, room_confidence
from app.geometry.room_validation import RoomEvidence, evaluate_room_candidate
from app.models.enums import ReviewStatus

# A plausible rectilinear rectangle, well above every size/vertex penalty.
_RECT_POLYGON = [[0.40, 0.40], [0.50, 0.40], [0.50, 0.50], [0.40, 0.50]]


def _evidence(**overrides) -> RoomEvidence:
    defaults = dict(
        area_sqft=150.0,
        num_vertices=4,
        wall_verified=True,
        polygon_norm=_RECT_POLYGON,
        wall_contact=0.75,
        in_drawing_zone=True,
    )
    defaults.update(overrides)
    return RoomEvidence(**defaults)


def test_well_supported_room_is_pending_not_rejected():
    decision = evaluate_room_candidate(_evidence())
    assert decision.status == ReviewStatus.PENDING
    assert decision.reasons == []
    assert decision.accepted is True


def test_outside_drawing_zone_rejects():
    decision = evaluate_room_candidate(_evidence(in_drawing_zone=False))
    assert decision.status == ReviewStatus.REJECTED
    assert "outside_drawing_zone" in decision.reasons
    assert decision.accepted is False


def test_low_wall_contact_rejects():
    """Matches the measured false-positive band documented in
    polygon_ops.py: exterior slabs/title-block boxes score 0.000-0.131,
    well under MIN_WALL_CONTACT_FOR_HIGH_CONFIDENCE (0.50).
    """
    decision = evaluate_room_candidate(_evidence(wall_contact=0.08))
    assert decision.status == ReviewStatus.REJECTED
    assert "low_wall_contact" in decision.reasons


def test_wall_contact_at_and_above_threshold_does_not_reject():
    at_threshold = evaluate_room_candidate(_evidence(wall_contact=MIN_WALL_CONTACT_FOR_HIGH_CONFIDENCE))
    assert at_threshold.status == ReviewStatus.PENDING
    just_below = evaluate_room_candidate(
        _evidence(wall_contact=MIN_WALL_CONTACT_FOR_HIGH_CONFIDENCE - 0.01)
    )
    assert just_below.status == ReviewStatus.REJECTED


def test_unverified_room_alone_does_not_reject():
    """A synthetic label-bisector cut is a deliberate fallback for a wall
    gap, not evidence of a false room — it stays reviewable (PENDING),
    only capped in confidence, same as before this gate existed.
    """
    decision = evaluate_room_candidate(_evidence(wall_verified=False, wall_contact=None))
    assert decision.status == ReviewStatus.PENDING
    assert decision.reasons == []
    assert decision.confidence <= 0.45  # UNVERIFIED_ROOM_CONFIDENCE_CAP


def test_low_rectilinearity_alone_does_not_reject():
    """Real L-shaped / irregular rooms are architecturally normal — must
    not be auto-rejected on shape alone.
    """
    irregular_polygon = [
        [0.40, 0.40], [0.55, 0.42], [0.53, 0.55], [0.48, 0.53], [0.45, 0.58], [0.41, 0.50],
    ]
    decision = evaluate_room_candidate(
        _evidence(polygon_norm=irregular_polygon, wall_contact=0.75)
    )
    assert decision.status == ReviewStatus.PENDING


def test_wall_contact_none_never_rejects_covered_areas():
    """Covered exterior areas are deliberately scored without wall_contact
    (see engine.py's Covered Area comment) — None must never be
    misinterpreted as "low."
    """
    decision = evaluate_room_candidate(_evidence(wall_contact=None, polygon_norm=None))
    assert decision.status == ReviewStatus.PENDING
    assert "low_wall_contact" not in decision.reasons


def test_confidence_matches_room_confidence_exactly():
    evidence = _evidence(wall_contact=0.62)
    decision = evaluate_room_candidate(evidence)
    expected = room_confidence(
        evidence.area_sqft, evidence.num_vertices,
        wall_verified=evidence.wall_verified, polygon_norm=evidence.polygon_norm,
        wall_contact=evidence.wall_contact, in_drawing_zone=evidence.in_drawing_zone,
    )
    assert decision.confidence == expected


def test_both_reject_reasons_can_combine():
    decision = evaluate_room_candidate(_evidence(in_drawing_zone=False, wall_contact=0.05))
    assert decision.status == ReviewStatus.REJECTED
    assert "outside_drawing_zone" in decision.reasons
    assert "low_wall_contact" in decision.reasons
