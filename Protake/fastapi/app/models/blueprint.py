from sqlalchemy import BigInteger, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin
from app.models.enums import BlueprintStatus


class Blueprint(Base, TimestampMixin):
    __tablename__ = "blueprints"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), default="application/pdf", nullable=False)
    num_pages: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pages_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[BlueprintStatus] = mapped_column(
        Enum(BlueprintStatus), default=BlueprintStatus.UPLOADED, nullable=False
    )
    processing_error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # Human-readable description of what the background worker is doing
    # right now (e.g. "Detecting rooms & walls (page 2/5)"), committed after
    # every real step in blueprint_service.process_single_page so a client
    # polling GET /blueprints/{id} sees genuine progress instead of only
    # `pages_processed`, which only moves once an entire page finishes and
    # can sit unchanged for the full 1-3 minutes a page takes.
    current_stage: Mapped[str | None] = mapped_column(String(200), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="blueprints")
    pages: Mapped[list["Page"]] = relationship(
        back_populates="blueprint", cascade="all, delete-orphan", order_by="Page.page_number"
    )
    estimates: Mapped[list["Estimate"]] = relationship(back_populates="blueprint")
