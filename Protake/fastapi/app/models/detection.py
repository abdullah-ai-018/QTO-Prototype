from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin
from app.models.enums import DetectionKind, DetectionSource, ReviewStatus, TradeKey


class Detection(Base, TimestampMixin):
    """A candidate object surfaced by OCR/AI validation (YOLOv11 + SAM2) or
    the geometry engine, awaiting (or having received) human review.

    Detections never drive quantity calculations directly — approving one
    only marks the underlying Room/Wall record (or creates one) as
    confirmed, which the deterministic trade engines then consume.
    """

    __tablename__ = "detections"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), nullable=False)

    kind: Mapped[DetectionKind] = mapped_column(Enum(DetectionKind), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    trade: Mapped[TradeKey | None] = mapped_column(Enum(TradeKey), nullable=True)

    polygon_norm: Mapped[list] = mapped_column(JSON, nullable=False)  # List[[x,y]]
    bbox_norm: Mapped[dict] = mapped_column(JSON, nullable=False)

    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[DetectionSource] = mapped_column(Enum(DetectionSource), nullable=False)
    status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus), default=ReviewStatus.PENDING, nullable=False)

    linked_room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True)
    linked_wall_id: Mapped[int | None] = mapped_column(ForeignKey("walls.id", ondelete="SET NULL"), nullable=True)

    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    page: Mapped["Page"] = relationship(back_populates="detections")
