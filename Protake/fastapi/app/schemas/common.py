from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    """Base for every response schema that reads from an ORM instance."""

    model_config = ConfigDict(from_attributes=True)


class Point(BaseModel):
    x: float
    y: float


class BBox(BaseModel):
    minX: float
    minY: float
    maxX: float
    maxY: float


class Message(BaseModel):
    detail: str
