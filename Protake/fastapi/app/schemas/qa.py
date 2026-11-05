from datetime import datetime

from pydantic import Field

from app.models.enums import QAFlagLevel, TradeKey
from app.schemas.common import ORMModel


class EntityCoverage(ORMModel):
    entity_type: str
    approved: int
    pending: int
    rejected: int
    total: int


class CoverageReport(ORMModel):
    blueprint_id: int
    rooms: EntityCoverage
    walls: EntityCoverage
    detections: EntityCoverage
    overall_readiness_pct: float
    gaps: list[str]


class VarianceFlag(ORMModel):
    room_id: int
    room_name: str
    geometry_area_sqft: float
    manual_measurement_id: int
    manual_area_sqft: float
    deviation_pct: float


class VarianceCheckResponse(ORMModel):
    page_id: int
    checked_rooms: int
    flags: list[VarianceFlag]


class RuleCalculateRequest(ORMModel):
    rule: str = Field(min_length=1)
    inputs: dict[str, float]


class RuleCalculateResponse(ORMModel):
    rule: str
    inputs: dict[str, float]
    result: float


class RuleListResponse(ORMModel):
    rules: list[str]


class QcSignoffRequest(ORMModel):
    trade: TradeKey
    signed_off: bool = True
    notes: str | None = None


class QcSignoffRead(ORMModel):
    id: int
    estimate_id: int
    trade: TradeKey
    reviewer_id: int
    signed_off: bool
    notes: str | None
    created_at: datetime


class EstimateReadinessResponse(ORMModel):
    estimate_id: int
    signed_off_trades: list[TradeKey]
    missing_trades: list[TradeKey]
    ready_to_finalize: bool


class CrossValidationFlag(ORMModel):
    schedule_type: str
    schedule_quantity: int
    ai_quantity: int
    discrepancy: int
    message: str


class CrossValidationResponse(ORMModel):
    blueprint_id: int
    flags: list[CrossValidationFlag]


class QAEngineFlag(ORMModel):
    level: QAFlagLevel
    message: str


class QAEngineResponse(ORMModel):
    blueprint_id: int
    flags: list[QAEngineFlag]
