"""Deterministic, trade-agnostic sanity check for a computed TradeResult
— the trade-level counterpart to app/geometry/room_validation.py's
RoomEvidence/RoomDecision pattern. No AI call: it re-examines the same
approved Room/Wall evidence (and, when available, Page.scale_source)
the engine itself calculated from, so an implausible or crashed result
is flagged before a client ever sees it, instead of silently reading as
a legitimate zero.
"""

from dataclasses import dataclass, field

from app.geometry.metrics import SCALE_SOURCE_ASSUMED
from app.models.enums import TradeKey, TradeTakeoffStatus
from app.models.page import Page
from app.models.room import Room
from app.models.wall import Wall
from app.trades.base import TradeResult, TradeValidation

# Trades whose page types are floor-plan-derived (rooms carry area) vs.
# wall-derived (drywall/painting quantities scale with wall length more
# than room count) — used only to pick a sensible confidence weighting,
# not to gate anything.
ROOM_AREA_WEIGHTED_TRADES = {TradeKey.FLOORING, TradeKey.ROOFING}

# Below this, the geometry a trade computed from is questionable enough
# that calling the result "validated" would be misleading — route to
# needs_review instead of just reporting a low number next to a
# reassuring status. Matches the existing scale-assumed cap (0.5) so a
# trade doesn't end up "validated" on worse evidence than the thing that
# already forces a review.
MIN_CONFIDENCE_FOR_VALIDATED = 0.5


def _geometry_confidence(rooms: list[Room], walls: list[Wall]) -> float:
    """Area/length-weighted mean confidence across the geometry that fed
    the calculation, mirroring how the engines themselves weight
    quantities by area/length rather than by naive row count.
    """
    room_weight = sum(r.area_sqft for r in rooms)
    if room_weight > 0:
        return round(sum(r.confidence * r.area_sqft for r in rooms) / room_weight, 4)
    wall_weight = sum(w.length_ft for w in walls)
    if wall_weight > 0:
        return round(sum(w.confidence * w.length_ft for w in walls) / wall_weight, 4)
    return 1.0


def validate_trade_result(
    trade: TradeKey,
    result: TradeResult,
    rooms: list[Room],
    walls: list[Wall],
    pages: list[Page] | None = None,
) -> TradeValidation:
    negative_items = [li.label for li in result.line_items if li.quantity < 0]
    if negative_items or result.material_quantity < 0:
        return TradeValidation(
            status=TradeTakeoffStatus.ERROR,
            confidence=0.0,
            reasons=[f"negative_quantity:{label}" for label in negative_items] or ["negative_material_quantity"],
        )

    if not rooms and not walls:
        return TradeValidation(status=TradeTakeoffStatus.NEEDS_REVIEW, confidence=0.0, reasons=["no_approved_geometry"])

    confidence = _geometry_confidence(rooms, walls)
    reasons: list[str] = []

    if pages and any(p.scale_source == SCALE_SOURCE_ASSUMED for p in pages):
        confidence = min(confidence, 0.5)
        reasons.append("scale_assumed_not_calibrated")

    has_supporting_geometry = bool(rooms) if trade in ROOM_AREA_WEIGHTED_TRADES else bool(rooms or walls)
    if has_supporting_geometry and result.material_quantity <= 0:
        reasons.append("zero_quantity_despite_approved_geometry")

    # Roofing explicit geometry check
    if trade == TradeKey.ROOFING and result.evidence:
        if result.evidence.get("fallback_warning"):
            reasons.append(result.evidence["fallback_warning"])

    # Drywall's engine computes the QTO total two independent ways — once
    # from the primary wall objects, once re-derived from the wall
    # reconciliation ledger — and records whether they agree
    # (result.evidence["independent_qto_recomputation"]["agreement"]).
    # Before this check, a mismatch was only ever logged as an error and
    # never actually affected the reported status: a trade could come back
    # "validated" even though the engine's own second calculation path
    # disagreed with the first. A real independent check that can't change
    # the outcome isn't a check — force review whenever it explicitly
    # disagrees.
    if result.evidence:
        recompute = result.evidence.get("independent_qto_recomputation")
        if isinstance(recompute, dict) and recompute.get("agreement") is False:
            reasons.append("independent_recompute_mismatch")

    if confidence < MIN_CONFIDENCE_FOR_VALIDATED:
        reasons.append("low_geometry_confidence")

    status = TradeTakeoffStatus.NEEDS_REVIEW if reasons else TradeTakeoffStatus.VALIDATED
    if reasons:
        confidence = min(confidence, 0.6)

    return TradeValidation(status=status, confidence=confidence, reasons=reasons)


def crashed_validation(error: Exception) -> TradeValidation:
    """Same shape estimate_service.py's except-block has always produced
    (a zeroed result on engine failure) but now typed as ERROR instead of
    being indistinguishable from a legitimate zero-quantity result.
    """
    return TradeValidation(status=TradeTakeoffStatus.ERROR, confidence=0.0, reasons=[str(error)])
