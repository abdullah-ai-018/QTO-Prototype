from pydantic import Field

from app.models.enums import MeasurementTool
from app.schemas.common import ORMModel


class MeasurementCreate(ORMModel):
    page_id: int
    tool: MeasurementTool
    points_norm: list[list[float]] = Field(min_length=1)
    label: str = Field(min_length=1, max_length=255)


class MeasurementRead(ORMModel):
    id: int
    page_id: int
    created_by_id: int
    tool: MeasurementTool
    points_norm: list[list[float]]
    label: str
    value: float
    unit: str
