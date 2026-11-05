"""Regression test for independent QTO recomputation agreement."""

from app.database import SessionLocal
from app.models.room import Room
from app.models.wall import Wall
from app.models.enums import ReviewStatus, TradeKey
from app.trades.drywall import DrywallEngine
from app.trades.pricing_service import PricingService


def test_independent_recompute_agreement_with_openings():
    """Test that independent QTO recomputation from wall ledger agrees with primary wall sheets even with modified openings."""
    db = SessionLocal()
    try:
        pricing = PricingService(db)
        config = pricing.resolve(TradeKey.DRYWALL, None)

        room = Room(id=1, page_id=1, name="Room 101", area_sqft=100.0, status=ReviewStatus.APPROVED)
        wall1 = Wall(
            id=101, page_id=1, length_ft=20.0, height_ft=9.0, status=ReviewStatus.APPROVED,
            start_norm={"x": 0.1, "y": 0.1}, end_norm={"x": 0.3, "y": 0.1}, thickness_ft=5/12
        )
        wall2 = Wall(
            id=102, page_id=1, length_ft=30.0, height_ft=9.0, status=ReviewStatus.APPROVED,
            start_norm={"x": 0.3, "y": 0.1}, end_norm={"x": 0.6, "y": 0.1}, thickness_ft=5/12
        )

        scale_info = {1: {"scale_ft_per_px": 0.05, "width_px": 8000, "height_px": 6000}}

        engine = DrywallEngine()
        result = engine.calculate(
            rooms=[room],
            walls=[wall1, wall2],
            config=config,
            page_scale_info=scale_info,
        )

        recomp = result.evidence.get("independent_qto_recomputation", {})
        assert recomp.get("status") == "AGREED", f"Expected AGREED status, got: {recomp}"
        assert recomp.get("agreement") is True
        assert recomp.get("discrepancy_sqft", 999) <= 1.0
    finally:
        db.close()
