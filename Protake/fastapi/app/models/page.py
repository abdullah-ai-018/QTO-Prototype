from typing import TYPE_CHECKING
from sqlalchemy import Boolean, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.architectural_wall import ArchitecturalWallModel
    from app.models.blueprint import Blueprint
    from app.models.detection import Detection
    from app.models.measurement import Measurement
    from app.models.room import Room
    from app.models.schedule_item import ScheduleItem
    from app.models.wall import Wall


class Page(Base, TimestampMixin):
    """A single rasterized sheet of a blueprint (e.g. A101 - Floor Plan)."""

    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(primary_key=True)
    blueprint_id: Mapped[int] = mapped_column(ForeignKey("blueprints.id", ondelete="CASCADE"), nullable=False)

    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    sheet_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sheet_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    width_px: Mapped[int] = mapped_column(Integer, nullable=False)
    height_px: Mapped[int] = mapped_column(Integer, nullable=False)
    dpi: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
    rotation_deg: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    image_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    thumbnail_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Calibration: real-world feet represented by one pixel at native resolution.
    scale_ft_per_px: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Where scale_ft_per_px came from — one of metrics.SCALE_SOURCE_* — so a
    # page silently running on the assumed default (SCALE_SOURCE_ASSUMED) is
    # explicitly queryable/reviewable instead of indistinguishable from an
    # uncalibrated-but-fine page. Set on every geometry run, including when
    # no calibration was found (see blueprint_service.run_geometry_analysis).
    scale_source: Mapped[str | None] = mapped_column(String(30), nullable=True)

    geometry_processed: Mapped[bool] = mapped_column(default=False, nullable=False)
    ocr_processed: Mapped[bool] = mapped_column(default=False, nullable=False)
    ai_validated: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Page classifier results (set during geometry analysis)
    page_type: Mapped[str | None] = mapped_column(String(50), nullable=True)          # architectural / text_specification / empty_blank / non_architectural
    is_takeoff_eligible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)  # False = skip this page
    skip_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)       # Human-readable skip reason

    # Richer classifier fields — computed by page_classifier.classify_page_content
    # on every page (app.geometry.engine.GeometryResult) but previously
    # discarded before reaching this row, forcing the frontend to re-derive
    # a cruder discipline/confidence guess of its own. NULL when a page
    # never made it through classification (e.g. unreadable raster) rather
    # than defaulted, so "not classified" stays distinguishable from a real
    # classification result.
    discipline: Mapped[str | None] = mapped_column(String(30), nullable=True)         # Architectural / Structural / Mechanical / Electrical / Plumbing / Civil / General
    primary_title: Mapped[str | None] = mapped_column(String(255), nullable=True)     # e.g. "ARCHITECTURAL FLOOR PLAN"
    classification_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    geometry_authority: Mapped[str | None] = mapped_column(String(30), nullable=True)  # PARTITION_WALLS / CEILING_GWB / ROOF_SURFACES / DEMOLITION / CONTEXT_ONLY / NONE

    revision_code: Mapped[str | None] = mapped_column(String(50), nullable=True)        # e.g. "Rev B", "Revision 2"
    cross_references: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)   # Sheet callouts e.g. ["A-401", "5/A-602"]

    blueprint: Mapped["Blueprint"] = relationship(back_populates="pages")
    rooms: Mapped[list["Room"]] = relationship(back_populates="page", cascade="all, delete-orphan")
    walls: Mapped[list["Wall"]] = relationship(back_populates="page", cascade="all, delete-orphan")
    architectural_walls: Mapped[list["ArchitecturalWallModel"]] = relationship(back_populates="page", cascade="all, delete-orphan")
    detections: Mapped[list["Detection"]] = relationship(back_populates="page", cascade="all, delete-orphan")
    measurements: Mapped[list["Measurement"]] = relationship(back_populates="page", cascade="all, delete-orphan")
    schedule_items: Mapped[list["ScheduleItem"]] = relationship(back_populates="page", cascade="all, delete-orphan")

