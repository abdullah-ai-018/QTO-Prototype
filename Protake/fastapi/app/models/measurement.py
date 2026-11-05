from sqlalchemy import Enum, Float, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin
from app.models.enums import MeasurementTool


class Measurement(Base, TimestampMixin):
    """A manual takeoff measurement drawn by an estimator directly on a
    page (area / linear / polygon / count), independent of AI detections.
    """

    __tablename__ = "measurements"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), nullable=False)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    tool: Mapped[MeasurementTool] = mapped_column(Enum(MeasurementTool), nullable=False)
    points_norm: Mapped[list] = mapped_column(JSON, nullable=False)  # List[[x,y]]
    label: Mapped[str] = mapped_column(String(255), nullable=False)

    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)  # ft, sq ft, count

    page: Mapped["Page"] = relationship(back_populates="measurements")
