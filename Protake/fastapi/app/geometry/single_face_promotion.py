"""Single-Face Evidence Promotion Engine (D-011).

Evaluates single-face wall candidates against a multi-signal contextual evidence ladder.
Instead of trapping single-face candidates permanently in NEEDS_REVIEW, context itself
serves as deterministic proof of physical wall legitimacy:

Single Face
 ↓
1. Room Boundary? (D-004 bidirectional room boundary support)
 ↓
2. Exterior Envelope? (conditioned building footprint boundary)
 ↓
3. Elevation / Section Callout Reference? (detail bubble e.g. 3/A401)
 ↓
4. Wall Schedule / Partition Spec Match? (tag or schedule sheet ref)
 ↓
5. Attached Openings? (door/window host)
 ↓
6. Cross-Sheet Evidence? (RCP ceiling height / multi-sheet correlation)
 ↓
CONFIRMED PHYSICAL WALL
"""

from dataclasses import dataclass, field
from typing import Any


# Weights for individual context signals
WEIGHT_ROOM_BOUNDARY = 0.35
WEIGHT_EXTERIOR_ENVELOPE = 0.30
WEIGHT_ATTACHED_OPENING = 0.30
WEIGHT_WALL_SCHEDULE_OR_TAG = 0.35
WEIGHT_ELEVATION_OR_CALLOUT = 0.25
WEIGHT_CROSS_SHEET_EVIDENCE = 0.20
WEIGHT_CONNECTED_CORNER = 0.20

# Minimum composite context score required to promote a single-face wall
PROMOTION_SCORE_THRESHOLD = 0.50


@dataclass
class SingleFaceContextEvidence:
    """Carries all context signals available for a single-face wall candidate."""
    # 1. Room Boundary Evidence
    has_room_boundary: bool = False
    is_bidirectional_verified: bool = False
    room_ids: list[int | str] = field(default_factory=list)

    # 2. Exterior Envelope
    is_exterior_envelope: bool = False

    # 3. Elevation & Detail Callout References
    has_elevation_ref: bool = False
    has_detail_callout_ref: bool = False
    callout_tags: list[str] = field(default_factory=list)

    # 4. Wall Schedule & Assembly Spec
    has_wall_tag: bool = False
    has_schedule_match: bool = False
    assembly_verified: bool = False
    wall_tag: str | None = None

    # 5. Attached Architectural Openings
    attached_openings_count: int = 0

    # 6. Cross-Sheet / Multi-Page Document Evidence
    has_cross_sheet_evidence: bool = False
    has_rcp_height_match: bool = False
    referenced_schedule_sheet: str | None = None

    # 7. Structural / Corner Continuity
    is_connected_at_corners: bool = False
    length_ft: float = 0.0


@dataclass
class SingleFacePromotionResult:
    """Outcome of single-face context evidence evaluation."""
    is_promoted: bool
    context_score: float
    matched_signals: list[str] = field(default_factory=list)
    promotion_tier: str = "unpromoted"
    recommended_confidence: float = 0.50
    diagnostic_reason: str = "insufficient_context_for_promotion"


def evaluate_single_face_promotion(evidence: SingleFaceContextEvidence) -> SingleFacePromotionResult:
    """Evaluates context signals for a single-face candidate and determines if it qualifies
    for promotion to a confirmed physical wall.
    """
    score = 0.0
    matched_signals: list[str] = []

    # 1. Room boundary support (either verified bidirectional link or room adjacency)
    if evidence.is_bidirectional_verified:
        score += WEIGHT_ROOM_BOUNDARY + 0.10
        matched_signals.append("bidirectional_room_boundary_verified")
    elif evidence.has_room_boundary or len(evidence.room_ids) > 0:
        score += WEIGHT_ROOM_BOUNDARY
        matched_signals.append("room_boundary_supported")

    # 2. Exterior building envelope
    if evidence.is_exterior_envelope:
        score += WEIGHT_EXTERIOR_ENVELOPE
        matched_signals.append("exterior_building_envelope")

    # 3. Attached architectural openings (doors/windows hosted by this wall)
    if evidence.attached_openings_count > 0:
        score += WEIGHT_ATTACHED_OPENING
        matched_signals.append(f"attached_openings_count:{evidence.attached_openings_count}")

    # 4. Wall schedule / tag / assembly specification
    if evidence.assembly_verified:
        score += WEIGHT_WALL_SCHEDULE_OR_TAG + 0.10
        matched_signals.append("verified_partition_schedule_match")
    elif evidence.has_schedule_match:
        score += WEIGHT_WALL_SCHEDULE_OR_TAG
        matched_signals.append("partition_schedule_match")
    elif evidence.has_wall_tag:
        score += WEIGHT_WALL_SCHEDULE_OR_TAG * 0.8
        matched_signals.append(f"wall_tag_present:{evidence.wall_tag}")

    # 5. Detail bubble or elevation callout reference
    if evidence.has_elevation_ref or evidence.has_detail_callout_ref:
        score += WEIGHT_ELEVATION_OR_CALLOUT
        callouts_str = ",".join(evidence.callout_tags) if evidence.callout_tags else "callout_detected"
        matched_signals.append(f"elevation_or_detail_callout:{callouts_str}")

    # 6. Cross-sheet / document-level correlation (e.g. RCP height)
    if evidence.has_rcp_height_match or evidence.has_cross_sheet_evidence:
        score += WEIGHT_CROSS_SHEET_EVIDENCE
        matched_signals.append("cross_sheet_document_evidence")

    # 7. Corner continuity for architectural-scale partitions (>= 3 ft)
    if evidence.is_connected_at_corners and evidence.length_ft >= 3.0:
        score += WEIGHT_CONNECTED_CORNER
        matched_signals.append("connected_corner_continuity")

    # Hard fast-path promotions:
    # - Verified Room Boundary + Connected Corner => instant promotion
    # - Exterior Envelope + Attached Opening => instant promotion
    # - Verified Schedule Match + Attached Opening => instant promotion
    fast_path = (
        (evidence.has_room_boundary and evidence.is_connected_at_corners and evidence.length_ft >= 3.0)
        or (evidence.is_exterior_envelope and evidence.attached_openings_count > 0)
        or (evidence.has_schedule_match and (evidence.has_room_boundary or evidence.attached_openings_count > 0))
    )

    is_promoted = (score >= PROMOTION_SCORE_THRESHOLD) or fast_path

    if is_promoted:
        # Confidence scaled by context score (bounded between 0.75 and 0.90)
        recommended_conf = round(min(0.90, max(0.75, 0.65 + score * 0.3)), 2)
        tier = "PHYSICAL_WALL_CONFIRMED_SINGLE_SOURCE"
        diag = "single_face_promoted_by_context:" + "+".join(matched_signals)
    else:
        recommended_conf = 0.50
        tier = "unpromoted"
        diag = "insufficient_context_for_single_face_promotion"

    return SingleFacePromotionResult(
        is_promoted=is_promoted,
        context_score=round(score, 3),
        matched_signals=matched_signals,
        promotion_tier=tier,
        recommended_confidence=recommended_conf,
        diagnostic_reason=diag,
    )
