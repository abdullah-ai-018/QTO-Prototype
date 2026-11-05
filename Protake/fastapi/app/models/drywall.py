"""Drywall's own persisted takeoff — deliberately separate from the
shared `estimate_items` table so a drywall recompute/version never reads
or writes another trade's rows, and from `rooms`/`walls` so a drywall
interpretation of a wall (e.g. "don't hang this one") never mutates
shared geometry other trades also read.
"""

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin
from app.models.enums import DetectionSource, TradeTakeoffStatus


class DrywallTakeoff(Base, TimestampMixin):
    """One persisted snapshot of a drywall compute for a blueprint —
    versioned like Estimate (a new row per POST .../takeoffs/drywall,
    not upserted in place) so takeoff history is preserved.
    """

    __tablename__ = "drywall_takeoffs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    blueprint_id: Mapped[int] = mapped_column(ForeignKey("blueprints.id", ondelete="CASCADE"), nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    material_quantity: Mapped[float] = mapped_column(Float, nullable=False)
    material_unit: Mapped[str] = mapped_column(String(30), nullable=False)
    labor_hours: Mapped[float] = mapped_column(Float, nullable=False)
    material_cost: Mapped[float] = mapped_column(Float, nullable=False)
    labor_cost: Mapped[float] = mapped_column(Float, nullable=False)
    direct_cost: Mapped[float] = mapped_column(Float, nullable=False)

    status: Mapped[TradeTakeoffStatus] = mapped_column(
        Enum(TradeTakeoffStatus), default=TradeTakeoffStatus.NEEDS_REVIEW, nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # Which room/wall/page ids and door/window counts fed this quantity —
    # so "8420 sqft" can be traced back to the exact approved geometry.
    evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    validation_reasons: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Snapshot versioning: fingerprints of the exact geometry/scale state
    # and the engine formula version that produced this row, so a stale
    # takeoff (geometry corrected or rescaled after this was computed)
    # can be detected by comparing against a freshly computed version.
    geometry_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    scale_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    engine_version: Mapped[str | None] = mapped_column(String(20), nullable=True)

    items: Mapped[list["DrywallItem"]] = relationship(back_populates="takeoff", cascade="all, delete-orphan")


class DrywallItem(Base, TimestampMixin):
    """One material/labor line item within a DrywallTakeoff — mirrors
    app.trades.base.LineItem / the shared EstimateItem shape.
    """

    __tablename__ = "drywall_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    takeoff_id: Mapped[int] = mapped_column(ForeignKey("drywall_takeoffs.id", ondelete="CASCADE"), nullable=False)

    label: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    unit_cost: Mapped[float] = mapped_column(Float, nullable=False)
    total_cost: Mapped[float] = mapped_column(Float, nullable=False)
    source_proof: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    formula_breakdown: Mapped[str | None] = mapped_column(Text, nullable=True)

    takeoff: Mapped["DrywallTakeoff"] = relationship(back_populates="items")


class DrywallClassification(Base, TimestampMixin):
    """Drywall's own read of a shared Wall row — an additive override,
    never a mutation of the `walls` table itself. No row for a given
    wall_id means "use the geometry-derived default" (hangable, sides
    inferred from wall_type); a row present overrides it.
    """

    __tablename__ = "drywall_classifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    wall_id: Mapped[int] = mapped_column(ForeignKey("walls.id", ondelete="CASCADE"), nullable=False, unique=True)

    hangable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sides_to_hang: Mapped[int | None] = mapped_column(Integer, nullable=True)

    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    source: Mapped[DetectionSource] = mapped_column(Enum(DetectionSource), default=DetectionSource.MANUAL, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
