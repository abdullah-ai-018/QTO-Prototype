from app.models.enums import TradeKey, TradeTakeoffStatus
from app.schemas.common import ORMModel


class TradeTakeoffItemRead(ORMModel):
    id: int
    label: str
    quantity: float
    unit: str
    unit_cost: float
    total_cost: float
    source_proof: dict | None = None
    formula_breakdown: str | None = None


class TradeTakeoffRead(ORMModel):
    id: int
    project_id: int
    blueprint_id: int
    trade: TradeKey
    material_quantity: float
    material_unit: str
    labor_hours: float
    material_cost: float
    labor_cost: float
    direct_cost: float
    status: TradeTakeoffStatus
    confidence: float
    evidence: dict | None = None
    validation_reasons: list[str] | None = None
    # Snapshot versioning (app.models.drywall.DrywallTakeoff etc.) — lets
    # a caller detect whether this persisted takeoff is stale relative to
    # the geometry/scale/engine state it would be recomputed from now.
    geometry_version: str | None = None
    scale_version: str | None = None
    engine_version: str | None = None
    items: list[TradeTakeoffItemRead]


class PageTradeTakeoffItemRead(ORMModel):
    label: str
    quantity: float
    unit: str
    unit_cost: float
    total_cost: float
    source_proof: dict | None = None
    formula_breakdown: str | None = None


class PageTradeTakeoffRead(ORMModel):
    """Non-persisted, live-computed takeoff scoped to a single page (sheet)
    — the sheet-scoped counterpart to TradeTakeoffRead. Runs through the
    exact same engine and carries the same evidence/formula_breakdown
    provenance as the blueprint-level takeoff, just filtered to one page's
    geometry, instead of a separate unaudited client-side recomputation.
    """
    page_id: int
    blueprint_id: int
    trade: TradeKey
    material_quantity: float
    material_unit: str
    labor_hours: float
    material_cost: float
    labor_cost: float
    direct_cost: float
    status: TradeTakeoffStatus
    confidence: float
    evidence: dict | None = None
    validation_reasons: list[str] | None = None
    items: list[PageTradeTakeoffItemRead]
