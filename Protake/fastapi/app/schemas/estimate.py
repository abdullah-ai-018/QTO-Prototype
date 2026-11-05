from app.models.enums import EstimateItemCategory, EstimateStatus, TradeKey, TradeTakeoffStatus
from app.schemas.common import ORMModel


class EstimateItemRead(ORMModel):
    id: int
    trade: TradeKey
    category: EstimateItemCategory
    label: str
    quantity: float
    unit: str
    unit_cost: float
    total_cost: float
    source_proof: dict | None = None
    formula_breakdown: str | None = None


class ScaleWarningItem(ORMModel):
    page_ids: list[int]
    reason: str
    scale_source: str = "assumed_default"


class RoomReviewWarningItem(ORMModel):
    page_ids: list[int]
    needs_review_count: int
    reason: str
    warning_type: str = "needs_human_review"


class EstimateRead(ORMModel):
    id: int
    project_id: int
    blueprint_id: int | None
    version: str
    status: EstimateStatus
    material_cost: float
    labor_cost: float
    direct_cost: float
    overhead_pct: float
    overhead_amount: float
    profit_pct: float
    profit_amount: float
    contingency_pct: float
    contingency_amount: float
    final_bid_price: float
    items: list[EstimateItemRead]
    # Non-persisted, computed fresh on every read from the contributing
    # pages' scale_source — a page with no confirmed scale directly affects
    # this estimate's room/wall counts (see qa_service's scale check). None
    # when every contributing page has a confirmed scale.
    scale_warnings: list[ScaleWarningItem] | None = None
    # Flagged pages containing rooms routed to the Human Review Queue
    review_warnings: list[RoomReviewWarningItem] | None = None



class EstimateGenerateRequest(ORMModel):
    blueprint_id: int
    overhead_pct: float = 12.0
    profit_pct: float = 15.0
    contingency_pct: float = 5.0


class TradeBreakdown(ORMModel):
    trade: TradeKey
    material_quantity: float
    material_unit: str
    labor_hours: float
    direct_cost: float
    line_items: list[EstimateItemRead]
    # Populated from TradeResult.validation (app.trades.validation) —
    # optional so older frontend builds that don't read these fields
    # keep working unchanged.
    status: TradeTakeoffStatus | None = None
    confidence: float | None = None
    validation_reasons: list[str] | None = None
