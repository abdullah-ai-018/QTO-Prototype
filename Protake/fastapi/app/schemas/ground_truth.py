from app.models.enums import TradeKey
from app.schemas.common import ORMModel


class GroundTruthReferenceCreate(ORMModel):
    trade: TradeKey
    item_label: str
    reference_quantity: float
    unit: str
    source: str
    verified_by: str | None = None
    notes: str | None = None


class GroundTruthReferenceRead(ORMModel):
    id: int
    blueprint_id: int
    trade: TradeKey
    item_label: str
    reference_quantity: float
    unit: str
    source: str
    verified_by: str | None
    notes: str | None


class VarianceComparisonRead(ORMModel):
    item_label: str
    reference_quantity: float
    unit: str
    source: str
    verified_by: str | None
    variance_pct: float | None


class TradeVarianceReportRead(ORMModel):
    trade: TradeKey
    computed_quantity: float
    computed_unit: str
    has_ground_truth: bool
    comparisons: list[VarianceComparisonRead]
