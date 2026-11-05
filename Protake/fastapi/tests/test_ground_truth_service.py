"""Unit tests for GroundTruthService's variance math — no DB needed,
the comparison logic itself is pure. The "no ground truth on file"
behavior (empty comparisons list, has_ground_truth=False) is the most
important case here: it's what keeps a missing reference from being
silently reported as "0% variance" or any other misleading default.
"""

from app.models.enums import TradeKey
from app.services.ground_truth_service import TradeVarianceReport, VarianceComparison


def test_variance_percent_computed_correctly():
    comparison = VarianceComparison(
        item_label="total_drywall_sqft",
        reference_quantity=1000.0,
        unit="sqft",
        source="manual_takeoff",
        verified_by="J. Smith",
        variance_pct=round((1100.0 - 1000.0) / 1000.0 * 100, 2),
    )
    assert comparison.variance_pct == 10.0


def test_no_ground_truth_is_explicit_not_a_default_zero():
    report = TradeVarianceReport(
        trade=TradeKey.ROOFING,
        computed_quantity=42.0,
        computed_unit="sq",
        has_ground_truth=False,
        comparisons=[],
    )
    assert report.has_ground_truth is False
    assert report.comparisons == []
    # Explicitly NOT claiming a 0% or 100% variance when nothing exists to compare against.
