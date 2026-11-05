"""Regression tests for Phase 7 of the migration plan: independent
validation must actually be able to change the reported outcome, not just
compute a number nobody reads.

Two things are tested:
1. validate_trade_result() downgrades status to NEEDS_REVIEW when the
   engine's own independent recompute (result.evidence
   ["independent_qto_recomputation"]["agreement"]) disagrees — previously
   this flag was computed and logged but never actually consulted.
2. GroundTruthService.compare(), exercised against a real (SQLite,
   in-memory) database session — this codebase had no DB-session-backed
   test anywhere before this file, which is exactly how a repository-level
   filter regression shipped silently earlier in this same migration.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401 — registers every ORM model on Base.metadata
from app.database import Base
from app.models.enums import TradeKey, TradeTakeoffStatus
from app.models.ground_truth import GroundTruthReference
from app.models.room import Room
from app.models.wall import Wall
from app.trades.base import LineItem, TradeResult
from app.trades.validation import validate_trade_result
from app.services.ground_truth_service import GroundTruthService


# ---------------------------------------------------------------------------
# 1. Independent recompute mismatch must force review
# ---------------------------------------------------------------------------

def _room():
    return Room(
        id=1, page_id=1, name="Office", area_sqft=200.0, perimeter_ft=60.0, confidence=0.95,
        polygon_norm=[{"x": 0.1, "y": 0.1}, {"x": 0.4, "y": 0.1}, {"x": 0.4, "y": 0.4}, {"x": 0.1, "y": 0.4}],
    )


def test_independent_recompute_disagreement_forces_needs_review():
    result = TradeResult(
        trade=TradeKey.DRYWALL,
        material_quantity=100.0,
        material_unit="sheets",
        labor_hours=10.0,
        line_items=[LineItem(label="Drywall Sheets", quantity=100.0, unit="sheets", unit_cost=28.0)],
        evidence={
            "independent_qto_recomputation": {
                "primary_wall_area_sqft": 5000.0,
                "independent_wall_area_sqft": 4200.0,
                "agreement": False,
                "status": "MISMATCH_INVESTIGATE",
            }
        },
    )
    validation = validate_trade_result(TradeKey.DRYWALL, result, [_room()], [], None)

    assert validation.status == TradeTakeoffStatus.NEEDS_REVIEW
    assert "independent_recompute_mismatch" in validation.reasons


def test_independent_recompute_agreement_does_not_force_review():
    """Sanity: the same geometry, but agreement=True, must NOT be forced
    into review by this check (isolating that the new check is triggered by
    the flag, not by something else in the fixture)."""
    result = TradeResult(
        trade=TradeKey.DRYWALL,
        material_quantity=100.0,
        material_unit="sheets",
        labor_hours=10.0,
        line_items=[LineItem(label="Drywall Sheets", quantity=100.0, unit="sheets", unit_cost=28.0)],
        evidence={
            "independent_qto_recomputation": {
                "primary_wall_area_sqft": 5000.0,
                "independent_wall_area_sqft": 5000.0,
                "agreement": True,
                "status": "AGREED",
            }
        },
    )
    validation = validate_trade_result(TradeKey.DRYWALL, result, [_room()], [], None)

    assert validation.status == TradeTakeoffStatus.VALIDATED
    assert "independent_recompute_mismatch" not in validation.reasons


# ---------------------------------------------------------------------------
# 2. GroundTruthService against a real DB session
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_ground_truth_reports_no_reference_honestly(db_session):
    service = GroundTruthService(db_session)
    report = service.compare(TradeKey.DRYWALL, blueprint_id=999, computed_quantity=437.0, computed_unit="sheets")

    assert report.has_ground_truth is False
    assert report.comparisons == []


def test_ground_truth_computes_real_variance_from_seeded_reference(db_session):
    ref = GroundTruthReference(
        blueprint_id=42,
        trade=TradeKey.DRYWALL,
        item_label="Drywall Sheets (4x8)",
        reference_quantity=400.0,
        unit="sheets",
        source="estimator_manual_takeoff_2026_08_20",
        verified_by="J. Smith",
    )
    db_session.add(ref)
    db_session.commit()

    service = GroundTruthService(db_session)
    # Computed quantity is 10% over the seeded reference (400 -> 440).
    report = service.compare(TradeKey.DRYWALL, blueprint_id=42, computed_quantity=440.0, computed_unit="sheets")

    assert report.has_ground_truth is True
    assert len(report.comparisons) == 1
    comparison = report.comparisons[0]
    assert comparison.reference_quantity == 400.0
    assert comparison.source == "estimator_manual_takeoff_2026_08_20"
    assert comparison.variance_pct == pytest.approx(10.0, abs=0.01)


def test_ground_truth_does_not_leak_across_blueprints_or_trades(db_session):
    """A reference row for a different blueprint or a different trade must
    never be picked up — this is what 'has_ground_truth' actually promises."""
    db_session.add(GroundTruthReference(
        blueprint_id=1, trade=TradeKey.DRYWALL, item_label="Drywall Sheets",
        reference_quantity=100.0, unit="sheets", source="manual",
    ))
    db_session.add(GroundTruthReference(
        blueprint_id=2, trade=TradeKey.PAINTING, item_label="Paint Gallons",
        reference_quantity=50.0, unit="gal", source="manual",
    ))
    db_session.commit()

    service = GroundTruthService(db_session)

    # Same blueprint, wrong trade -> no match.
    report_wrong_trade = service.compare(TradeKey.PAINTING, blueprint_id=1, computed_quantity=99.0, computed_unit="gal")
    assert report_wrong_trade.has_ground_truth is False

    # Right trade, wrong blueprint -> no match.
    report_wrong_blueprint = service.compare(TradeKey.DRYWALL, blueprint_id=2, computed_quantity=99.0, computed_unit="sheets")
    assert report_wrong_blueprint.has_ground_truth is False

    # Correct pairing -> real match.
    report_correct = service.compare(TradeKey.DRYWALL, blueprint_id=1, computed_quantity=100.0, computed_unit="sheets")
    assert report_correct.has_ground_truth is True
    assert report_correct.comparisons[0].variance_pct == 0.0
