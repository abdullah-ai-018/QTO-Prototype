"""Compares a computed trade quantity against human-verified reference
takeoffs (app.models.ground_truth.GroundTruthReference) — the actual
accuracy signal that app.trades.validation.py's `confidence` is
explicitly NOT a substitute for.

No ground truth is seeded anywhere in this system. Every comparison
below is honest about that: a trade/blueprint with no reference rows on
file reports `has_ground_truth=False`, not a fabricated or assumed
variance.
"""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.enums import TradeKey
from app.repositories.ground_truth_repository import GroundTruthReferenceRepository


@dataclass
class VarianceComparison:
    item_label: str
    reference_quantity: float
    unit: str
    source: str
    verified_by: str | None
    variance_pct: float | None  # None only if reference_quantity == 0 (can't divide)


@dataclass
class TradeVarianceReport:
    trade: TradeKey
    computed_quantity: float
    computed_unit: str
    has_ground_truth: bool
    comparisons: list[VarianceComparison] = field(default_factory=list)


class GroundTruthService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = GroundTruthReferenceRepository(db)

    def compare(self, trade: TradeKey, blueprint_id: int, computed_quantity: float, computed_unit: str) -> TradeVarianceReport:
        references = self.repo.for_blueprint_and_trade(blueprint_id, trade)
        comparisons = [
            VarianceComparison(
                item_label=ref.item_label,
                reference_quantity=ref.reference_quantity,
                unit=ref.unit,
                source=ref.source,
                verified_by=ref.verified_by,
                variance_pct=(
                    round((computed_quantity - ref.reference_quantity) / ref.reference_quantity * 100, 2)
                    if ref.reference_quantity
                    else None
                ),
            )
            for ref in references
        ]
        return TradeVarianceReport(
            trade=trade,
            computed_quantity=computed_quantity,
            computed_unit=computed_unit,
            has_ground_truth=bool(comparisons),
            comparisons=comparisons,
        )

    def evaluate_ground_truth_for_page(
        self,
        detected_walls: list,
        ground_truth_walls: list[dict],
        detected_rooms: list | None = None,
        ground_truth_rooms: list[dict] | None = None,
    ):
        """Runs the 12-metric forensic ground-truth evaluation across walls, rooms, and QTO."""
        from app.geometry.ground_truth_evaluation import evaluate_ground_truth
        return evaluate_ground_truth(
            detected_walls=detected_walls,
            ground_truth_walls=ground_truth_walls,
            detected_rooms=detected_rooms,
            ground_truth_rooms=ground_truth_rooms,
        )

