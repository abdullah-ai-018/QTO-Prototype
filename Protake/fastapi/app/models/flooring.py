"""Flooring's own persisted takeoff — same shape as app.models.drywall,
kept as a fully separate table family. Flooring's classification is
room-keyed rather than wall-keyed (flooring.py's engine sums room area,
not wall area), unlike drywall/painting.
"""

from sqlalchemy import Boolean, Enum, Float, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin
from app.models.enums import DetectionSource, TradeTakeoffStatus


class FlooringTakeoff(Base, TimestampMixin):
    """One persisted snapshot of a flooring compute for a blueprint —
    versioned like Estimate, not upserted in place.
    """

    __tablename__ = "flooring_takeoffs"

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

    items: Mapped[list["FlooringItem"]] = relationship(back_populates="takeoff", cascade="all, delete-orphan")


class FlooringItem(Base, TimestampMixin):
    """One material/labor line item within a FlooringTakeoff."""

    __tablename__ = "flooring_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    takeoff_id: Mapped[int] = mapped_column(ForeignKey("flooring_takeoffs.id", ondelete="CASCADE"), nullable=False)

    label: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    unit_cost: Mapped[float] = mapped_column(Float, nullable=False)
    total_cost: Mapped[float] = mapped_column(Float, nullable=False)
    source_proof: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    formula_breakdown: Mapped[str | None] = mapped_column(Text, nullable=True)

    takeoff: Mapped["FlooringTakeoff"] = relationship(back_populates="items")


class FlooringClassification(Base, TimestampMixin):
    """Flooring's own read of a shared Room row — an additive override,
    same pattern as DrywallClassification but keyed by room_id instead of
    wall_id. No row for a room_id means "use the geometry-derived
    default" (flooring_eligible).
    """

    __tablename__ = "flooring_classifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, unique=True)

    flooring_eligible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    floor_finish: Mapped[str | None] = mapped_column(String(100), nullable=True)

    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    source: Mapped[DetectionSource] = mapped_column(Enum(DetectionSource), default=DetectionSource.MANUAL, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
