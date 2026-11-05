from sqlalchemy import Enum, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin
from app.models.enums import TradeKey


class QcSignoff(Base, TimestampMixin):
    """A QA reviewer's formal sign-off that one trade's quantities on one
    Estimate have been checked and are trustworthy. An Estimate can only
    be finalized once every trade has a signed_off=True row — this is
    the same "someone initials the takeoff sheet" step every commercial
    estimating shop runs before a bid goes out the door.
    """

    __tablename__ = "qc_signoffs"
    __table_args__ = (UniqueConstraint("estimate_id", "trade", name="uq_signoff_estimate_trade"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    estimate_id: Mapped[int] = mapped_column(ForeignKey("estimates.id", ondelete="CASCADE"), nullable=False)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    trade: Mapped[TradeKey] = mapped_column(Enum(TradeKey), nullable=False)
    signed_off: Mapped[bool] = mapped_column(default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    estimate: Mapped["Estimate"] = relationship(back_populates="signoffs")
    reviewer: Mapped["User"] = relationship()
