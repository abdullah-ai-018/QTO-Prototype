"""Reference (human-verified, real-world) takeoff quantities to compare
computed trade results against — the actual accuracy backing for the
confidence scores in app/trades/validation.py. Confidence and accuracy
are NOT the same thing (see TradeValidation's docstring); this table is
what lets a real accuracy/variance number be computed at all, instead of
confidence being mistaken for one.

No data is seeded here — this is infrastructure only. A blueprint has no
ground truth until someone with a verified real-world quantity adds a
row (see app/services/ground_truth_service.py / the ground-truth API
endpoints).
"""

from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin
from app.models.enums import TradeKey


class GroundTruthReference(Base, TimestampMixin):
    __tablename__ = "ground_truth_references"

    id: Mapped[int] = mapped_column(primary_key=True)
    blueprint_id: Mapped[int] = mapped_column(ForeignKey("blueprints.id", ondelete="CASCADE"), nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    trade: Mapped[TradeKey] = mapped_column(Enum(TradeKey), nullable=False)
    # What this reference measures — usually the trade's total material
    # quantity (matches TradeResult.material_quantity's unit), but can be
    # a specific line item (e.g. "Drywall Sheets (4x8)") for a finer-
    # grained comparison than just the headline number.
    item_label: Mapped[str] = mapped_column(String(255), nullable=False)
    reference_quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)

    # Where this number actually came from — required, and never
    # "computed"/"estimated"/anything the system itself produced, or it
    # stops being ground truth and becomes another opinion to compare.
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    verified_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
