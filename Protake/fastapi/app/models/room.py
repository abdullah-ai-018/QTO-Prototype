from sqlalchemy import Enum, Float, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin
from app.models.enums import DetectionSource, ReviewStatus


class Room(Base, TimestampMixin):
    """A deterministically-derived, or human-confirmed, room boundary.

    Geometry (`polygon_norm`, `area_sqft`, ...) is produced by the geometry
    engine (flood fill + contour + polygon approximation over wall lines).
    OCR/AI only ever annotate or validate this record — they never write
    area/perimeter values themselves.
    """

    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    room_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    floor_finish: Mapped[str | None] = mapped_column(String(100), nullable=True)
    wall_finish: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ceiling_finish: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # List[[x, y]] in normalized 0..1 page space, closed polygon.
    polygon_norm: Mapped[list] = mapped_column(JSON, nullable=False)
    bbox_norm: Mapped[dict] = mapped_column(JSON, nullable=False)  # {minX,minY,maxX,maxY}
    centroid_norm: Mapped[dict] = mapped_column(JSON, nullable=False)  # {x,y}

    area_sqft: Mapped[float] = mapped_column(Float, nullable=False)
    perimeter_ft: Mapped[float] = mapped_column(Float, nullable=False)

    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    source: Mapped[DetectionSource] = mapped_column(Enum(DetectionSource), default=DetectionSource.GEOMETRY, nullable=False)
    status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus), default=ReviewStatus.PENDING, nullable=False)

    page: Mapped["Page"] = relationship(back_populates="rooms")
    walls: Mapped[list["Wall"]] = relationship(back_populates="room")
