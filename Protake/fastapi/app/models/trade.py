from sqlalchemy import Enum, Float, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin
from app.models.enums import TradeKey


class TradeConfig(Base, TimestampMixin):
    """Configurable pricing/coverage table for one trade, scoped to a
    project (or global default when project_id is null). This is what
    lets the same deterministic rule engine serve commercial, regional,
    or fully custom pricing without touching code.
    """

    __tablename__ = "trade_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)

    trade: Mapped[TradeKey] = mapped_column(Enum(TradeKey), nullable=False)
    region: Mapped[str] = mapped_column(String(100), default="national-average", nullable=False)
    label: Mapped[str] = mapped_column(String(255), default="Default", nullable=False)

    labor_rate_per_hour: Mapped[float] = mapped_column(Float, nullable=False)
    waste_factor_pct: Mapped[float] = mapped_column(Float, nullable=False)

    # Trade-specific coverage rates / unit costs, e.g.
    # drywall: {"sheet_coverage_sqft": 32, "sheet_cost": 14.5, ...}
    coverage_rates: Mapped[dict] = mapped_column(JSON, nullable=False)
    material_unit_costs: Mapped[dict] = mapped_column(JSON, nullable=False)
    productivity_rates: Mapped[dict] = mapped_column(JSON, nullable=False)  # units per labor hour

    is_default: Mapped[bool] = mapped_column(default=False, nullable=False)

    project: Mapped["Project | None"] = relationship(back_populates="trade_configs")
