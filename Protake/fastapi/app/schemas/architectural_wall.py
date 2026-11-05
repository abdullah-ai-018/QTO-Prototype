"""Pydantic schemas for ArchitecturalWall and semantic interpretation entities."""

from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class WallOpeningSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    opening_type: str
    width_ft: float
    height_ft: float
    area_sqft: float
    position_ratio: float = 0.5
    center_norm: dict[str, float]
    dimension_source: str = "detected_geometry"
    confidence: float = 0.90
    schedule_tag: str | None = None


class WallAssemblySpecSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tag: str
    description: str
    stud_depth_in: float = 3.625
    stud_gauge: str = "20 GA"
    board_type_side_a: str = "5/8\" Type X GWB"
    layers_side_a: int = 1
    board_type_side_b: str = "5/8\" Type X GWB"
    layers_side_b: int = 1
    sides_to_hang: int = 2
    insulation: str | None = None
    fire_rating_hr: float | None = 1.0
    sound_rating_stc: float | None = 50.0
    source: str = "partition_schedule"


class ArchitecturalWallRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    page_id: int
    start_norm: dict[str, float]
    end_norm: dict[str, float]
    clipped_segments_norm: list[list[dict[str, float]]] = Field(default_factory=list)
    wall_polygon_norm: list[list[float]] = Field(default_factory=list)

    length_ft: float
    height_ft: float = 9.0
    height_provenance: str = "ASSUMED"
    thickness_in: float = 4.875
    thickness_source: str = "project_default"

    classification: str = "NEEDS_REVIEW"
    wall_tag: str | None = None
    assembly_tag: str | None = None
    assembly_description: str | None = None
    sides_to_hang: int = 2
    layers_side_a: int = 1
    layers_side_b: int = 1
    schedule_sheet: str | None = None
    assembly_verified: bool = False

    gross_sf: float = 0.0
    openings_count: int = 0
    opening_deduction_sf: float = 0.0
    net_sf: float = 0.0

    decision_state: str = "physical_wall_confirmed"
    qto_eligible: bool = False
    qto_block_reason: str | None = None
    confidence: float = 0.0
    status: str = "approved"
    rejection_reason: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    openings: list[WallOpeningSchema] = Field(default_factory=list)


# Alias for backward compatibility
ArchitecturalWallSchema = ArchitecturalWallRead

