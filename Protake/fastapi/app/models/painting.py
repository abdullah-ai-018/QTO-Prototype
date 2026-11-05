"""Painting's own persisted takeoff — same shape as app.models.drywall,
kept as a fully separate table family so a painting recompute/version
never touches drywall's (or any other trade's) rows.
"""

from sqlalchemy import Boolean, Enum, Float, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin
from app.models.enums import DetectionSource, TradeTakeoffStatus


class PaintingTakeoff(Base, TimestampMixin):
    """One persisted snapshot of a painting compute for a blueprint —
    versioned like Estimate, not upserted in place.
    """

    __tablename__ = "painting_takeoffs"

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
    evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    validation_reasons: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Snapshot versioning — see DrywallTakeoff's identical fields for the
    # full rationale (staleness detection after geometry/scale edits).
    geometry_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    scale_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    engine_version: Mapped[str | None] = mapped_column(String(20), nullable=True)

    items: Mapped[list["PaintingItem"]] = relationship(back_populates="takeoff", cascade="all, delete-orphan")


class PaintingItem(Base, TimestampMixin):
    """One material/labor line item within a PaintingTakeoff."""

    __tablename__ = "painting_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    takeoff_id: Mapped[int] = mapped_column(ForeignKey("painting_takeoffs.id", ondelete="CASCADE"), nullable=False)

    label: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    unit_cost: Mapped[float] = mapped_column(Float, nullable=False)
    total_cost: Mapped[float] = mapped_column(Float, nullable=False)
    source_proof: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    formula_breakdown: Mapped[str | None] = mapped_column(Text, nullable=True)

    takeoff: Mapped["PaintingTakeoff"] = relationship(back_populates="items")


class PaintingClassification(Base, TimestampMixin):
    """Painting's own read of a shared Wall row — an additive override,
    same pattern as DrywallClassification (app.models.drywall). No row
    for a wall_id means "use the geometry-derived default" (paintable).
    """

    __tablename__ = "painting_classifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    wall_id: Mapped[int] = mapped_column(ForeignKey("walls.id", ondelete="CASCADE"), nullable=False, unique=True)

    paintable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    source: Mapped[DetectionSource] = mapped_column(Enum(DetectionSource), default=DetectionSource.MANUAL, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
