from sqlalchemy import Enum, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin
from app.models.enums import AuditAction


class AuditLog(Base, TimestampMixin):
    """Immutable record of every mutating action in the system. Undo/redo
    is implemented by replaying the inverse of `previous_value` /
    `new_value` — see `app.services.audit_service`.
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[int] = mapped_column(nullable=False)
    action: Mapped[AuditAction] = mapped_column(Enum(AuditAction), nullable=False)

    field_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    previous_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    version: Mapped[str] = mapped_column(String(20), nullable=False)
    is_undone: Mapped[bool] = mapped_column(default=False, nullable=False)

    project: Mapped["Project"] = relationship(back_populates="audit_logs")
    user: Mapped["User"] = relationship(back_populates="audit_logs")
