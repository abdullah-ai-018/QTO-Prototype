"""Proves EnhancedRoofingEngine (app/trades/roofing.py) actually uses
roof pitch/slope geometry as its primary production calculation, and
only falls back to a flat-ceiling-area estimate when no real roof
geometry is available — not the other way around.

Self-contained (no DB): builds transient (unpersisted) Room/TradeConfig
ORM instances directly, since the roofing engine only reads plain
attributes off them and never touches a session.
"""

from app.ai.roof_analyzer import RoofAnalysisResult
from app.models.enums import RoofComplexity, RoofType, TradeKey, TradeTakeoffStatus
from app.models.room import Room
from app.models.trade import TradeConfig
from app.trades.registry import TRADE_ENGINES
from app.trades.validation import validate_trade_result

ROOFING_CONFIG = TradeConfig(
    trade=TradeKey.ROOFING,
    labor_rate_per_hour=45.0,
    waste_factor_pct=12.0,
    coverage_rates={
        "assumed_pitch_rise_per_12": 6.0,
        "bundle_coverage_sqft": 33.3,
        "starter_ft_per_bundle": 100,
        "underlayment_roll_coverage_sqft": 400,
        "ice_shield_ft_per_roll": 75,
        "ridge_cap_ft_per_bundle": 33,
        "drip_edge_ft_per_piece": 10,
        "valley_flashing_ft_per_piece": 10,
        "nails_per_shingle_bundle": 320,
        "nails_per_box": 7200,
    },
    material_unit_costs={},
    productivity_rates={},
)


def _flat_rooms(area_sqft: float, perimeter_ft: float) -> list[Room]:
    return [Room(id=1, page_id=1, name="Roof Footprint", area_sqft=area_sqft, perimeter_ft=perimeter_ft, confidence=1.0)]


def _roof_analysis(total_area_sqft: float, slope_factor: float) -> RoofAnalysisResult:
    return RoofAnalysisResult(
        roof_type=RoofType.GABLE,
        complexity=RoofComplexity.MEDIUM,
        total_area_sqft=total_area_sqft,
        slope_factor=slope_factor,
        ridge_length_ft=40.0,
        hip_length_ft=0.0,
        valley_length_ft=0.0,
        eave_length_ft=127.0,
        rake_length_ft=38.0,
        openings=[],
        penetrations=[],
        recommended_waste_pct=10.0,
        estimated_squares=round(total_area_sqft / 100, 2),
        complexity_factors={},
    )


def test_squares_scale_with_pitch_not_just_flat_footprint():
    """Same footprint (1000 sqft, matching flat ceiling area either way),
    three different real roof-plane pitches -> three genuinely different
    squares counts, proportional to the pitch, not identical.
    """
    rooms = _flat_rooms(area_sqft=1000.0, perimeter_ft=127.0)
    engine = TRADE_ENGINES[TradeKey.ROOFING]

    low_pitch = engine.calculate(rooms, [], ROOFING_CONFIG, roof_analysis=_roof_analysis(1000.0 * 1.0, 1.0))
    moderate_pitch = engine.calculate(rooms, [], ROOFING_CONFIG, roof_analysis=_roof_analysis(1000.0 * 1.5, 1.5))
    steep_pitch = engine.calculate(rooms, [], ROOFING_CONFIG, roof_analysis=_roof_analysis(1000.0 * 2.5, 2.5))

    assert low_pitch.material_quantity == 10.0  # 1000/100
    assert moderate_pitch.material_quantity == 15.0  # 1500/100
    assert steep_pitch.material_quantity == 25.0  # 2500/100
    # The whole point: these must differ. A calculator that silently used
    # flat ceiling area regardless of pitch would produce 10.0 for all three.
    assert len({low_pitch.material_quantity, moderate_pitch.material_quantity, steep_pitch.material_quantity}) == 3

    for result in (low_pitch, moderate_pitch, steep_pitch):
        assert result.evidence["roof_geometry_source"] == "dedicated_roof_planes"
        assert "fallback_warning" not in result.evidence


def test_ceiling_area_fallback_is_flagged_not_silent():
    """No roof_analysis supplied (no approved roof-plan geometry) ->
    engine still returns a number (graceful degradation), but the
    evidence must say so, and the validator must downgrade it to
    needs_review rather than calling it validated on an assumption.
    """
    rooms = _flat_rooms(area_sqft=1000.0, perimeter_ft=127.0)
    engine = TRADE_ENGINES[TradeKey.ROOFING]

    result = engine.calculate(rooms, [], ROOFING_CONFIG, roof_analysis=None)

    assert result.evidence["roof_geometry_source"] == "ceiling_area_fallback"
    assert result.evidence["fallback_warning"]

    validation = validate_trade_result(TradeKey.ROOFING, result, rooms, [], pages=None)
    assert validation.status == TradeTakeoffStatus.NEEDS_REVIEW
    assert any("fallback" in reason for reason in validation.reasons)


def test_fallback_pitch_factor_also_differs_from_flat_area():
    """Even the fallback path (no dedicated roof geometry) must apply a
    pitch factor from config, not just report the flat footprint as
    the roof area — assumed_pitch_rise_per_12=6.0 in this config is a
    real (non-1.0) slope, so sloped area must exceed flat area.
    """
    rooms = _flat_rooms(area_sqft=1000.0, perimeter_ft=127.0)
    engine = TRADE_ENGINES[TradeKey.ROOFING]

    result = engine.calculate(rooms, [], ROOFING_CONFIG, roof_analysis=None)

    assert result.evidence["sloped_area_sqft"] > result.evidence["flat_area_sqft"]
    assert result.evidence["pitch_factor"] > 1.0
