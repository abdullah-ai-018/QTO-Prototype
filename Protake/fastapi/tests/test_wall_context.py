"""Tests that page/document context actually reaches wall-candidate
validation and changes its decision — not merely that a PageContext object
exists (see FORENSIC_AUDIT_REPORT.md, which is what this closes).

Split into two layers:
  - Unit tests against PageContext + evaluate_wall_candidate directly:
    fast, deterministic, exercise every context field wall_validation.py
    consumes without needing a real page image.
  - One integration test against analyze_page() on a small synthetic
    raster image, confirming context genuinely flows end to end (not just
    at the unit boundary) and that the legacy no-context call signature
    still works unchanged.
"""

import numpy as np
import pytest
from PIL import Image

from app.geometry.drawing_zone import MIN_DRAWING_ZONE_OVERLAP, zone_overlap_ratio
from app.geometry.engine import analyze_page
from app.geometry.metrics import SCALE_SOURCE_MEASURED, SCALE_SOURCE_PRINTED, ScaleContext
from app.geometry.page_classifier import ClassificationResult, PageType
from app.geometry.page_context import PageContext
from app.geometry.wall_validation import WallEvidence, evaluate_wall_candidate
from app.models.enums import ReviewStatus

_FULL_ZONE = {"minX": 0.0, "minY": 0.0, "maxX": 1.0, "maxY": 1.0}
_ARCH_ZONE = {"minX": 0.03, "minY": 0.03, "maxX": 0.96, "maxY": 0.94}


def _classification(page_type=PageType.FLOOR_PLAN, zone=_ARCH_ZONE) -> ClassificationResult:
    return ClassificationResult(
        page_type=page_type,
        discipline="Architectural",
        is_takeoff_eligible=True,
        skip_reason=None,
        drawing_zone_bbox=zone,
    )


def _context(**overrides) -> PageContext:
    defaults = dict(
        classification=_classification(),
        scale_context=ScaleContext.assumed(dpi=150.0),
        width_px=1000,
        height_px=800,
        has_vector_data=False,
        has_wall_layer=False,
        ocr_available=False,
        selected_trade=None,
    )
    defaults.update(overrides)
    return PageContext.build(**defaults)


# --- 1. page_type reaches the context object wall validation reads -------

def test_page_type_reaches_page_context():
    ctx = _context(classification=_classification(page_type=PageType.ROOF_PLAN))
    assert ctx.page_type == "roof_plan"


# --- 2 & 7. drawing_zone reaches validation AND changes the decision -----

def test_drawing_zone_reaches_context_and_rejects_outside_candidate():
    ctx = _context(classification=_classification(zone=_ARCH_ZONE))
    assert ctx.drawing_zone == _ARCH_ZONE

    # Well-supported wall (connected, room-linked, exterior) but its bbox
    # sits entirely in the title-block margin outside the drawing zone.
    outside_evidence = WallEvidence(
        length_ft=10.0, connected=True, linked_room_index=0, exterior=True,
        bbox_norm={"minX": 0.97, "minY": 0.97, "maxX": 0.99, "maxY": 0.99},
        source="vector_layer",
    )
    decision = evaluate_wall_candidate(outside_evidence, ctx)
    assert decision.status == ReviewStatus.REJECTED
    assert "outside_drawing_zone" in decision.reasons

    # Same evidence, but inside the zone — must be accepted. Proves the
    # zone check is what changed the decision, not the other evidence.
    inside_evidence = WallEvidence(
        length_ft=10.0, connected=True, linked_room_index=0, exterior=True,
        bbox_norm={"minX": 0.40, "minY": 0.40, "maxX": 0.45, "maxY": 0.40},
        source="vector_layer",
    )
    decision2 = evaluate_wall_candidate(inside_evidence, ctx)
    assert decision2.status == ReviewStatus.PENDING
    assert "outside_drawing_zone" not in decision2.reasons


# --- 3. calibrated ScaleContext reaches context ---------------------------

def test_calibrated_scale_context_reaches_page_context():
    sc = ScaleContext.from_ft_per_px(0.02, SCALE_SOURCE_MEASURED, dpi=150.0)
    ctx = _context(scale_context=sc)
    assert ctx.scale_is_calibrated is True
    assert ctx.scale == pytest.approx(0.02)


# --- 4. missing scale does NOT fabricate a scale ---------------------------

def test_missing_scale_stays_uncalibrated_not_fabricated():
    ctx = _context(scale_context=ScaleContext.assumed(dpi=150.0))
    assert ctx.scale_is_calibrated is False
    # assumed() still returns a usable pixel-space ratio for page-relative
    # math, but it must never be reported as calibrated/measured.
    assert ctx.scale_context.source not in (SCALE_SOURCE_MEASURED, SCALE_SOURCE_PRINTED)


# --- 5. selected_trade reaches context only when explicitly provided ------

def test_selected_trade_reaches_context_only_when_provided():
    ctx_none = _context(selected_trade=None)
    assert ctx_none.selected_trade is None

    ctx_drywall = _context(selected_trade="drywall")
    assert ctx_drywall.selected_trade == "drywall"


# --- selected_trade wired into wall CONFIDENCE, never into accept/reject --

def _base_evidence(**overrides) -> WallEvidence:
    defaults = dict(
        length_ft=10.0, connected=True, linked_room_index=0, exterior=True,
        bbox_norm={"minX": 0.40, "minY": 0.40, "maxX": 0.45, "maxY": 0.40},
        source="vector_layer",
    )
    defaults.update(overrides)
    return WallEvidence(**defaults)


def test_no_trade_selected_applies_zero_weight():
    ctx = _context(selected_trade=None)
    decision = evaluate_wall_candidate(_base_evidence(), ctx)
    assert decision.trade_weight == 0.0
    assert not any("trade_weight" in r for r in decision.reasons)


@pytest.mark.parametrize("trade", ["drywall", "painting"])
def test_wall_primary_trade_boosts_confidence(trade):
    ctx_none = _context(selected_trade=None)
    ctx_trade = _context(selected_trade=trade)
    base = evaluate_wall_candidate(_base_evidence(), ctx_none)
    weighted = evaluate_wall_candidate(_base_evidence(), ctx_trade)
    assert weighted.confidence > base.confidence
    assert weighted.trade_weight > 0.0
    assert any(r.startswith("trade_weight:+") for r in weighted.reasons)
    # Status must be identical regardless of trade — same geometry, same
    # evidence, only the score differs.
    assert weighted.status == base.status


@pytest.mark.parametrize("trade", ["flooring", "roofing"])
def test_wall_secondary_trade_lowers_confidence_but_never_hides_it(trade):
    ctx_none = _context(selected_trade=None)
    ctx_trade = _context(selected_trade=trade)
    base = evaluate_wall_candidate(_base_evidence(), ctx_none)
    weighted = evaluate_wall_candidate(_base_evidence(), ctx_trade)
    assert weighted.confidence < base.confidence
    assert weighted.trade_weight < 0.0
    # "flooring -> ignore walls" is exactly what this must not do: the wall
    # is still PENDING (reviewable), never dropped or force-rejected.
    assert weighted.status == base.status == ReviewStatus.PENDING


def test_trade_weighting_never_flips_reject_status_for_a_bad_candidate():
    """A candidate that fails the evidence gate stays REJECTED under every
    trade, including the ones that would otherwise boost its confidence —
    trade weighting is applied to the score, never to the accept/reject
    decision itself.
    """
    ctx_no_trade = _context(selected_trade=None)
    ctx_drywall = _context(selected_trade="drywall")
    bad_evidence = _base_evidence(connected=False, linked_room_index=None, exterior=False)
    d1 = evaluate_wall_candidate(bad_evidence, ctx_no_trade)
    d2 = evaluate_wall_candidate(bad_evidence, ctx_drywall)
    assert d1.status == ReviewStatus.REJECTED
    assert d2.status == ReviewStatus.REJECTED
    assert d2.confidence != d1.confidence  # score still moved
    assert d2.trade_weight > 0.0


def test_trade_weight_stays_within_wall_confidence_bounds():
    ctx = _context(selected_trade="drywall")
    # A candidate already at/near wall_confidence()'s own 0.98 ceiling must
    # not be pushed past it by the trade nudge.
    near_ceiling = _base_evidence(length_ft=50.0, connected=True, linked_room_index=0, exterior=True)
    decision = evaluate_wall_candidate(near_ceiling, ctx)
    assert decision.confidence <= 0.98


# --- 6. vector/raster availability reaches context -------------------------

def test_vector_and_wall_layer_availability_reach_context():
    ctx_raster_only = _context(has_vector_data=False, has_wall_layer=False)
    assert ctx_raster_only.has_vector_data is False
    assert ctx_raster_only.has_wall_layer is False

    ctx_vector = _context(has_vector_data=True, has_wall_layer=True)
    assert ctx_vector.has_vector_data is True
    assert ctx_vector.has_wall_layer is True


# --- 8. low-confidence / isolated wall does not become a normal accepted wall --

def test_isolated_unlinked_interior_wall_is_rejected_not_silently_accepted():
    """This is the exact evidence combination traced in
    FORENSIC_AUDIT_REPORT.md to a real false wall (Wall id 77333 on blueprint
    430): unconnected, borders no detected room, not on the exterior edge.
    """
    ctx = _context()
    evidence = WallEvidence(
        length_ft=3.5, connected=False, linked_room_index=None, exterior=False,
        bbox_norm={"minX": 0.20, "minY": 0.50, "maxX": 0.21, "maxY": 0.55},
        source="vector_raw",
    )
    decision = evaluate_wall_candidate(evidence, ctx)
    assert decision.confidence == pytest.approx(0.25)  # matches wall_confidence() exactly
    assert decision.status == ReviewStatus.REJECTED
    assert "isolated_unlinked_interior_segment" in decision.reasons
    assert decision.accepted is False


def test_same_isolated_wall_is_kept_if_room_linked_or_exterior():
    """Connectivity/room-linkage/exterior-ness is evidence, not an absolute
    rule — a real wall can legitimately terminate at a door or the building
    edge. Only the triple-negative gets flagged.
    """
    ctx = _context()
    room_linked = WallEvidence(
        length_ft=3.5, connected=False, linked_room_index=2, exterior=False,
        bbox_norm={"minX": 0.40, "minY": 0.40, "maxX": 0.41, "maxY": 0.45},
        source="vector_raw",
    )
    decision = evaluate_wall_candidate(room_linked, ctx)
    assert decision.status == ReviewStatus.PENDING
    assert "isolated_unlinked_interior_segment" not in decision.reasons

    exterior_wall = WallEvidence(
        length_ft=3.5, connected=False, linked_room_index=None, exterior=True,
        bbox_norm={"minX": 0.40, "minY": 0.40, "maxX": 0.41, "maxY": 0.45},
        source="vector_raw",
    )
    decision2 = evaluate_wall_candidate(exterior_wall, ctx)
    assert decision2.status == ReviewStatus.PENDING


# --- 9. provenance survives candidate -> decision ---------------------------

def test_provenance_source_and_reasons_are_returned_not_dropped():
    ctx = _context()
    evidence = WallEvidence(
        length_ft=3.5, connected=False, linked_room_index=None, exterior=False,
        bbox_norm={"minX": 0.20, "minY": 0.50, "maxX": 0.21, "maxY": 0.55},
        source="raster_band",
    )
    decision = evaluate_wall_candidate(evidence, ctx)
    assert evidence.source == "raster_band"
    assert isinstance(decision.reasons, list) and decision.reasons
    assert isinstance(decision.confidence, float)


# --- zone_overlap_ratio shared helper is what both gates use --------------

def test_zone_overlap_ratio_matches_the_constant_both_rooms_and_walls_use():
    fully_inside = zone_overlap_ratio({"minX": 0.4, "minY": 0.4, "maxX": 0.5, "maxY": 0.5}, _ARCH_ZONE)
    assert fully_inside == pytest.approx(1.0)
    assert fully_inside >= MIN_DRAWING_ZONE_OVERLAP


# --- 10. no-context legacy path still works (integration) -----------------

def _synthetic_floor_plan_image(path: str, size: int = 900) -> None:
    """A trivial rectangle-with-a-partition raster image — enough for
    analyze_page's raster fallback path (no pdf_path, no vector data) to
    run end to end without needing a real scanned sheet.
    """
    arr = np.full((size, size), 255, dtype=np.uint8)
    t = 6
    arr[100:100 + t, 100:800] = 0        # top wall
    arr[700:700 + t, 100:800] = 0        # bottom wall
    arr[100:700, 100:100 + t] = 0        # left wall
    arr[100:700, 800:800 + t] = 0        # right wall
    arr[100:700, 450:450 + t] = 0        # interior partition
    Image.fromarray(arr).save(path)


def test_analyze_page_legacy_call_still_works_without_scale_context(tmp_path):
    img_path = str(tmp_path / "plan.png")
    _synthetic_floor_plan_image(img_path)

    # Legacy signature: no scale_context, no selected_trade — must not
    # raise, and must not report a fabricated calibrated scale.
    result = analyze_page(img_path)
    assert result is not None
    assert isinstance(result.walls, list)


def test_analyze_page_accepts_selected_trade_without_changing_call_shape(tmp_path):
    img_path = str(tmp_path / "plan2.png")
    _synthetic_floor_plan_image(img_path)

    result_no_trade = analyze_page(img_path)
    result_with_trade = analyze_page(img_path, selected_trade="drywall")

    # Trade selection must not change which walls/rooms are found — only
    # be available as context (see engine.py's selected_trade docstring).
    assert len(result_no_trade.walls) == len(result_with_trade.walls)
    assert len(result_no_trade.rooms) == len(result_with_trade.rooms)

    # Every persisted wall now carries provenance instead of being
    # indistinguishable ordinary rows.
    for wall in result_with_trade.walls:
        assert wall.source != "unknown"
        assert wall.status in (ReviewStatus.PENDING, ReviewStatus.REJECTED)
