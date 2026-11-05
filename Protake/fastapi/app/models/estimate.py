from sqlalchemy import Enum, Float, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin
from app.models.enums import EstimateItemCategory, EstimateStatus, TradeKey


class Estimate(Base, TimestampMixin):
    """A snapshot of the full cost roll-up for a project at a point in
    time (one row per generated/re-generated estimate — this is what
    powers version history alongside the audit log).
    """

    __tablename__ = "estimates"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    blueprint_id: Mapped[int | None] = mapped_column(ForeignKey("blueprints.id", ondelete="SET NULL"), nullable=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    version: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[EstimateStatus] = mapped_column(Enum(EstimateStatus), default=EstimateStatus.DRAFT, nullable=False)

    material_cost: Mapped[float] = mapped_column(Float, nullable=False)
    labor_cost: Mapped[float] = mapped_column(Float, nullable=False)
    direct_cost: Mapped[float] = mapped_column(Float, nullable=False)

    overhead_pct: Mapped[float] = mapped_column(Float, nullable=False)
    overhead_amount: Mapped[float] = mapped_column(Float, nullable=False)
    profit_pct: Mapped[float] = mapped_column(Float, nullable=False)
    profit_amount: Mapped[float] = mapped_column(Float, nullable=False)
    contingency_pct: Mapped[float] = mapped_column(Float, nullable=False)
    contingency_amount: Mapped[float] = mapped_column(Float, nullable=False)

    final_bid_price: Mapped[float] = mapped_column(Float, nullable=False)

    project: Mapped["Project"] = relationship(back_populates="estimates")
    blueprint: Mapped["Blueprint | None"] = relationship(back_populates="estimates")
    items: Mapped[list["EstimateItem"]] = relationship(back_populates="estimate", cascade="all, delete-orphan")
    signoffs: Mapped[list["QcSignoff"]] = relationship(back_populates="estimate", cascade="all, delete-orphan")


class EstimateItem(Base, TimestampMixin):
    """One line item (a material or labor quantity) within an Estimate."""

    __tablename__ = "estimate_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    estimate_id: Mapped[int] = mapped_column(ForeignKey("estimates.id", ondelete="CASCADE"), nullable=False)

    trade: Mapped[TradeKey] = mapped_column(Enum(TradeKey), nullable=False)
    category: Mapped[EstimateItemCategory] = mapped_column(Enum(EstimateItemCategory), nullable=False)

    label: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    unit_cost: Mapped[float] = mapped_column(Float, nullable=False)
    total_cost: Mapped[float] = mapped_column(Float, nullable=False)

    # Evidence: exactly which approved rooms/walls/pages this quantity
    # traces back to, and the arithmetic that produced it.
    source_proof: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    formula_breakdown: Mapped[str | None] = mapped_column(Text, nullable=True)

    estimate: Mapped["Estimate"] = relationship(back_populates="items")
