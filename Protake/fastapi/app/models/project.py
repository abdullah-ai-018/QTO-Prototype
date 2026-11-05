from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin
from app.models.enums import ProjectStatus, UnitSystem


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(Enum(ProjectStatus), default=ProjectStatus.ACTIVE, nullable=False)
    # Display/input preference only — geometry stays canonically feet/sqft internally;
    # this only affects how calibration input and area/length are shown to the user.
    unit_system: Mapped[UnitSystem] = mapped_column(Enum(UnitSystem), default=UnitSystem.IMPERIAL, nullable=False)

    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    owner: Mapped["User"] = relationship(back_populates="projects")
    blueprints: Mapped[list["Blueprint"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    estimates: Mapped[list["Estimate"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    trade_configs: Mapped[list["TradeConfig"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="project", cascade="all, delete-orphan")
