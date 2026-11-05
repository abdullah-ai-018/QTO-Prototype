"""Roofing's own takeoff *header/line-item/status* layer — deliberately a
separate module from app.models.roof, which already owns roofing's
geometry-derived tables (roofs/roof_planes/roof_edges/roof_openings/
roof_penetrations/roof_flashing). Those stay as-is; this file only adds
the same evidence/confidence/status snapshot layer the other 3 trades
have (RoofingTakeoff/RoofingItem), plus a wall-keyed classification
override for the roof_feature reads in trades/roofing.py.
"""

from sqlalchemy import Enum, Float, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin
from app.models.enums import DetectionSource, RoofFeature, TradeTakeoffStatus


class RoofingTakeoff(Base, TimestampMixin):
    """One persisted snapshot of a roofing compute for a blueprint —
    versioned like Estimate, not upserted in place.
    """

    __tablename__ = "roofing_takeoffs"

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

    items: Mapped[list["RoofingItem"]] = relationship(back_populates="takeoff", cascade="all, delete-orphan")


class RoofingItem(Base, TimestampMixin):
    """One material/labor line item within a RoofingTakeoff."""

    __tablename__ = "roofing_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    takeoff_id: Mapped[int] = mapped_column(ForeignKey("roofing_takeoffs.id", ondelete="CASCADE"), nullable=False)

    label: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    unit_cost: Mapped[float] = mapped_column(Float, nullable=False)
    total_cost: Mapped[float] = mapped_column(Float, nullable=False)
    source_proof: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    formula_breakdown: Mapped[str | None] = mapped_column(Text, nullable=True)

    takeoff: Mapped["RoofingTakeoff"] = relationship(back_populates="items")


class RoofingClassification(Base, TimestampMixin):
    """Roofing's own read of a shared Wall row's roof feature — an
    additive override, same pattern as DrywallClassification. Absence of
    a row for a wall_id means "use Wall.roof_feature" (today's behavior);
    presence overrides it — this is the two-level fallback trades/
    roofing.py's ridge/hip length lookup uses.
    """

    __tablename__ = "roofing_classifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    wall_id: Mapped[int] = mapped_column(ForeignKey("walls.id", ondelete="CASCADE"), nullable=False, unique=True)

    roof_feature: Mapped[RoofFeature | None] = mapped_column(Enum(RoofFeature), nullable=True)

    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    source: Mapped[DetectionSource] = mapped_column(Enum(DetectionSource), default=DetectionSource.MANUAL, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
