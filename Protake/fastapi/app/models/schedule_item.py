from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin
from app.models.enums import DetectionKind, ReviewStatus


class ScheduleItem(Base, TimestampMixin):
    """One row of a parsed Door/Window Schedule table (e.g. "W-4, qty 96,
    aluminium frame, 6mm clear glass") — extracted from the vector table
    structure on a schedule sheet (see app/ocr/schedule_parser.py), never
    from a floor/roof plan. Reviewable like a Detection: quantities here
    only feed the trade engines' door/window deduction once approved.
    """

    __tablename__ = "schedule_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), nullable=False)

    schedule_type: Mapped[DetectionKind] = mapped_column(Enum(DetectionKind), nullable=False)  # DOOR or WINDOW
    item_code: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. "W-4", "D-3"
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    attributes: Mapped[dict] = mapped_column(JSON, nullable=False)  # frame_material, finish, glazing, size, notes...

    confidence: Mapped[float] = mapped_column(Float, default=0.8, nullable=False)
    status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus), default=ReviewStatus.PENDING, nullable=False)

    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    page: Mapped["Page"] = relationship(back_populates="schedule_items")
