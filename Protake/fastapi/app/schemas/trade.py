from pydantic import Field

from app.models.enums import TradeKey
from app.schemas.common import ORMModel


class TradeConfigRead(ORMModel):
    id: int
    project_id: int | None
    trade: TradeKey
    region: str
    label: str
    labor_rate_per_hour: float
    waste_factor_pct: float
    coverage_rates: dict
    material_unit_costs: dict
    productivity_rates: dict
    is_default: bool


class TradeConfigUpsert(ORMModel):
    trade: TradeKey
    region: str = "national-average"
    label: str = "Custom"
    labor_rate_per_hour: float | None = Field(default=None, gt=0)
    waste_factor_pct: float | None = Field(default=None, ge=0, le=100)
    coverage_rates: dict | None = None
    material_unit_costs: dict | None = None
    productivity_rates: dict | None = None

