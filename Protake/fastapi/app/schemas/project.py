from datetime import datetime

from pydantic import Field

from app.models.enums import ProjectStatus, UnitSystem
from app.schemas.common import ORMModel
from app.schemas.user import UserRead


class ProjectCreate(ORMModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    client_name: str | None = None
    location: str | None = None
    unit_system: UnitSystem = UnitSystem.IMPERIAL
    selected_trade: str | None = None


class ProjectUpdate(ORMModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    client_name: str | None = None
    location: str | None = None
    status: ProjectStatus | None = None
    unit_system: UnitSystem | None = None


class ProjectRead(ORMModel):
    id: int
    name: str
    description: str | None
    client_name: str | None
    location: str | None
    status: ProjectStatus
    unit_system: UnitSystem
    owner: UserRead | None = None
    created_at: datetime


class ProjectSummary(ORMModel):
    id: int
    name: str
    status: ProjectStatus
    blueprint_count: int = 0
    latest_final_bid: float | None = None
