"""Context-aware acceptance gate for a room candidate — the room-side
counterpart to wall_validation.py.

`room_confidence()` (polygon_ops.py) already computes a plausibility score
from area, vertex count, `wall_verified`, rectilinearity, `wall_contact`,
and drawing-zone containment.
"""

from dataclasses import dataclass, field

from app.geometry.polygon_ops import MIN_WALL_CONTACT_FOR_HIGH_CONFIDENCE, room_confidence
from app.models.enums import ReviewStatus


MIN_RASTER_WALL_CONTACT = 0.65  # Empirically optimal threshold derived from dynamic sweep


@dataclass
class RoomEvidence:
    area_sqft: float
    num_vertices: int
    wall_verified: bool
    polygon_norm: list[list[float]] | None
    wall_contact: float | None  # Vector wall contact metric
    in_drawing_zone: bool
    raster_wall_contact: float | None = None  # Separate raster line-segment wall contact metric


@dataclass
class RoomDecision:
    confidence: float
    status: ReviewStatus
    reasons: list[str] = field(default_factory=list)

    @property
    def accepted(self) -> bool:
        return self.status != ReviewStatus.REJECTED


def evaluate_room_candidate(evidence: RoomEvidence) -> RoomDecision:
    confidence = room_confidence(
        evidence.area_sqft,
        evidence.num_vertices,
        wall_verified=evidence.wall_verified,
        polygon_norm=evidence.polygon_norm,
        wall_contact=evidence.wall_contact,
        in_drawing_zone=evidence.in_drawing_zone,
    )
    reasons: list[str] = []

    # 1. Vector wall contact support signal
    has_vector_wall_support = (
        evidence.wall_contact is not None and evidence.wall_contact >= MIN_WALL_CONTACT_FOR_HIGH_CONFIDENCE
    )

    # 2. Raster line-segment wall contact support signal (separate metric)
    has_raster_wall_support = (
        evidence.raster_wall_contact is not None and evidence.raster_wall_contact >= MIN_RASTER_WALL_CONTACT
    )

    # Multi-signal OR logic: candidate passes if supported by vector layer OR raster line segments
    # When wall_contact is None (e.g. covered exterior areas), it is not checked for wall contact.
    if evidence.wall_contact is not None:
        has_sufficient_wall_support = has_vector_wall_support or has_raster_wall_support
        if not has_sufficient_wall_support:
            reasons.append("low_wall_contact")

    if not evidence.in_drawing_zone:
        reasons.append("outside_drawing_zone")

    if reasons:
        status = ReviewStatus.REJECTED
    else:
        status = ReviewStatus.PENDING

    return RoomDecision(confidence=confidence, status=status, reasons=reasons)
