"""Roofing API Schemas for Professional Takeoff"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime

from app.models.enums import RoofType, RoofMaterialType, RoofComplexity, DetectionSource, ReviewStatus


class RoofPlaneCreate(BaseModel):
    plane_name: str
    plane_number: int
    polygon_norm: List[List[float]]
    centroid_norm: Dict[str, float]
    length_ft: float
    width_ft: float
    flat_area_sqft: float
    pitch_rise: float
    pitch_run: float = 12.0


class RoofPlaneRead(RoofPlaneCreate):
    id: int
    page_id: int
    roof_id: int
    sloped_area_sqft: float
    pitch_angle_degrees: float
    pitch_factor: float
    confidence: float
    source: DetectionSource
    status: ReviewStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RoofCreate(BaseModel):
    page_id: int
    roof_type: RoofType
    material_type: RoofMaterialType
    complexity: RoofComplexity = RoofComplexity.MEDIUM
    total_flat_area_sqft: float
    total_sloped_area_sqft: float
    total_squares: float
    total_perimeter_ft: float
    eave_length_ft: float = 0.0
    rake_length_ft: float = 0.0
    ridge_length_ft: float = 0.0
    hip_length_ft: float = 0.0
    valley_length_ft: float = 0.0
    stories: int = 1
    roof_height_ft: float = 10.0
    overhang_ft: float = 1.0
    is_steep_roof: bool = False
    requires_crane: bool = False
    requires_safety_harness: bool = False
    waste_factor_pct: float = 8.0


class RoofRead(RoofCreate):
    id: int
    confidence: float
    source: DetectionSource
    status: ReviewStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RoofUpdate(BaseModel):
    roof_type: Optional[RoofType] = None
    material_type: Optional[RoofMaterialType] = None
    complexity: Optional[RoofComplexity] = None
    total_flat_area_sqft: Optional[float] = None
    total_sloped_area_sqft: Optional[float] = None
    total_squares: Optional[float] = None
    waste_factor_pct: Optional[float] = None
    status: Optional[ReviewStatus] = None


class RoofOpeningRead(BaseModel):
    id: int
    opening_type: str
    opening_name: Optional[str]
    length_ft: float
    width_ft: float
    area_sqft: float
    perimeter_ft: float
    flashing_perimeter_ft: float
    confidence: float

    class Config:
        from_attributes = True


class RoofPenetrationRead(BaseModel):
    id: int
    penetration_type: str
    diameter_inches: float
    requires_boot: bool
    requires_flashing: bool
    confidence: float

    class Config:
        from_attributes = True


class RoofAnalysisRequest(BaseModel):
    page_id: int
    roof_planes: List[Dict[str, Any]] = Field(default_factory=list)
    scale_ft_per_px: float
    assumed_pitch: float = 6.0  # 6/12 pitch default


class RoofAnalysisResponse(BaseModel):
    page_id: int
    roof_type: str
    complexity: str
    total_area_sqft: float
    slope_factor: float
    
    # Edge measurements
    ridge_length_ft: float
    hip_length_ft: float
    valley_length_ft: float
    eave_length_ft: float
    rake_length_ft: float
    
    # Detected features
    openings: List[Dict[str, Any]]
    penetrations: List[Dict[str, Any]]
    
    # Material recommendations
    recommended_waste_pct: float
    estimated_squares: float
    complexity_factors: Dict[str, bool]


class LineItemResponse(BaseModel):
    description: str
    unit: str
    quantity: float
    unit_cost: float
    total_cost: float


class RoofTakeoffRequest(BaseModel):
    page_id: int
    pitch_rise: Optional[float] = None  # Rise per 12" run
    waste_factor_pct: Optional[float] = None
    material_type: RoofMaterialType = RoofMaterialType.ASPHALT_SHINGLES


class RoofTakeoffResponse(BaseModel):
    page_id: int
    line_items: List[LineItemResponse]
    material_total: float
    labor_total: float
    total_cost: float
    metadata: Dict[str, Any]