from sqlalchemy import Boolean, Enum, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.geometry.metrics import DEFAULT_WALL_THICKNESS_FT
from app.models.base import TimestampMixin
from app.models.enums import DetectionSource, ReviewStatus, RoofFeature, WallType


class Wall(Base, TimestampMixin):
    """A single wall segment extracted by the geometry engine (Hough line
    transform + connected-component merge), the primary input to the
    Drywall and Painting trade engines.
    """

    __tablename__ = "walls"
    __allow_unmapped__ = True

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), nullable=False)
    room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True)

    start_norm: Mapped[dict] = mapped_column(JSON, nullable=False)  # {x,y}
    end_norm: Mapped[dict] = mapped_column(JSON, nullable=False)  # {x,y}

    length_ft: Mapped[float] = mapped_column(Float, nullable=False)
    height_ft: Mapped[float] = mapped_column(Float, default=9.0, nullable=False)
    thickness_ft: Mapped[float] = mapped_column(Float, default=DEFAULT_WALL_THICKNESS_FT, nullable=False)  # 5in stud+board = 5/12 ft
    # Whether thickness_ft was measured off the drawing's own wall stroke
    # (see geometry.metrics.measure_wall_thickness_ft) or is just the
    # assumed default above. An estimator pricing off a wall width needs to
    # know which of the two they are looking at, so the UI labels it.
    thickness_measured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    wall_type: Mapped[WallType] = mapped_column(Enum(WallType), default=WallType.INTERIOR, nullable=False)
    wall_type_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    roof_feature: Mapped[RoofFeature | None] = mapped_column(Enum(RoofFeature), nullable=True)

    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    source: Mapped[DetectionSource] = mapped_column(Enum(DetectionSource), default=DetectionSource.GEOMETRY, nullable=False)
    status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus), default=ReviewStatus.PENDING, nullable=False)

    # Independent Face Provenance Attributes — persisted columns (not transient).
    # These carry the raw geometry-engine segment IDs that prove a wall has
    # two independently-detected face strokes (face_a != face_b), which is
    # what promotes a wall to PHYSICAL_WALL_CONFIRMED in the 5-state decision
    # machine.  Without persistence the dual-face confirmation was lost every
    # time a wall was reloaded from the DB, demoting every wall to
    # PHYSICAL_WALL_CONFIRMED_SINGLE_SOURCE regardless of detection quality.
    # Migration: e1a2b3c4d5e6_add_wall_face_provenance_columns.py
    face_a_segment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    face_b_segment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    face_a_coords: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    face_b_coords: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    overlap_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)

    # DEF-01/DEF-10: height provenance — NULL means ASSUMED (backward-compatible).
    # Migration: f1a2b3c4d5e7_add_wall_height_source_and_source_tag.py
    height_source: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # DEF-03: fine-grained geometry source tag preserved from GeometryWall.source.
    # Keeps the full origin string (e.g. 'cad_vector_entity_unnamed_unconfirmed')
    # distinct from the coarser DetectionSource enum in the `source` column.
    source_tag: Mapped[str | None] = mapped_column(String(200), nullable=True)

    page: Mapped["Page"] = relationship(back_populates="walls")
    room: Mapped["Room | None"] = relationship(back_populates="walls")

    @property
    def area_sqft(self) -> float:
        """Both wall faces (interior partitions are painted/drywalled on both sides)."""
        sides = 2 if self.wall_type != WallType.EXTERIOR else 1
        return round(self.length_ft * self.height_ft * sides, 2)
