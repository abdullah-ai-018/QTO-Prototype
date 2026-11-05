"""Canonical BIM Models: Unified, platform-neutral building domain structures with strict provenance tracking and QTO eligibility gates."""
from __future__ import annotations

import enum
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


class DataProvenanceStatus(str, enum.Enum):
    VERIFIED_EXPLICIT = "VERIFIED_EXPLICIT"  # Found in explicit IFC properties/Pset/Qto
    DERIVED_GEOMETRIC = "DERIVED_GEOMETRIC"  # Calculated from BRep/Solid/Curve geometry
    CONFIGURED_ASSUMPTION = "CONFIGURED_ASSUMPTION"  # Project/code configured default rule
    UNKNOWN_UNRESOLVED = "UNKNOWN_UNRESOLVED"  # Missing from IFC; requires estimator review


class QTOEligibilityStatus(str, enum.Enum):
    ELIGIBLE = "ELIGIBLE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    INELIGIBLE_NON_DRYWALL = "INELIGIBLE_NON_DRYWALL"
    INELIGIBLE_NON_ROOF = "INELIGIBLE_NON_ROOF"
    INELIGIBLE_INVALID_GEOMETRY = "INELIGIBLE_INVALID_GEOMETRY"


class FlooringCategory(str, enum.Enum):
    HARDWOOD_FLOORING = "HARDWOOD_FLOORING"
    LAMINATE_FLOORING = "LAMINATE_FLOORING"
    TILE_CERAMIC_PORCELAIN = "TILE_CERAMIC_PORCELAIN"
    CARPET_BROADLOOM = "CARPET_BROADLOOM"
    CARPET_TILE = "CARPET_TILE"
    RESILIENT_VINYL_LVT = "RESILIENT_VINYL_LVT"
    CONCRETE_POLISHED_SEALED = "CONCRETE_POLISHED_SEALED"
    UNASSIGNED_FINISH = "UNASSIGNED_FINISH"


class FlooringEvidenceType(str, enum.Enum):
    PHYSICAL_COVERING = "PHYSICAL_COVERING"
    PHYSICAL_SLAB_FINISH = "PHYSICAL_SLAB_FINISH"
    SPATIAL_SPACE_FINISH = "SPATIAL_SPACE_FINISH"


class FlooringEligibilityStatus(str, enum.Enum):
    ELIGIBLE = "ELIGIBLE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    INELIGIBLE_STRUCTURAL_SLAB = "INELIGIBLE_STRUCTURAL_SLAB"
    INELIGIBLE_ROOF_SLAB = "INELIGIBLE_ROOF_SLAB"
    SUPERSEDED_BY_PHYSICAL_ELEMENT = "SUPERSEDED_BY_PHYSICAL_ELEMENT"


class CanonicalFlooringElement(BaseModel):
    id: str
    ifc_guid: str
    source_entity_type: Literal["IFC_COVERING", "IFC_SLAB", "IFC_SPACE"]
    evidence_type: FlooringEvidenceType
    source_name: str
    storey_id: str
    storey_name: str = "Level 01"
    
    # Material & Finish
    flooring_category: FlooringCategory = FlooringCategory.UNASSIGNED_FINISH
    finish_material_name: Optional[str] = None
    thickness_in: Optional[float] = None
    
    # Geometry & Areas
    has_physical_solid_geometry: bool = False
    gross_area_sqft: float = 0.0
    void_deductions_sqft: float = 0.0
    net_area_sqft: float = 0.0
    perimeter_ft: float = 0.0
    vertices: list[list[float]] = Field(default_factory=list)
    bbox: Optional[dict[str, float]] = None
    
    # Scope Precedence & Gating
    qto_eligibility: FlooringEligibilityStatus = FlooringEligibilityStatus.ELIGIBLE
    provenance_status: DataProvenanceStatus = DataProvenanceStatus.VERIFIED_EXPLICIT
    eligibility_reasons: list[str] = Field(default_factory=list)
    superseded_by_guid: Optional[str] = None
    
    # Raw IFC Evidence
    source_psets: dict[str, Any] = Field(default_factory=dict)


class QTOReadiness(str, enum.Enum):
    READY_FOR_QTO = "READY_FOR_QTO"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"


class ModelHealthCard(BaseModel):
    schema_version: str
    length_unit: str
    unit_scale_to_meters: float
    total_elements: int
    wall_count: int
    opening_count: int
    space_count: int
    storey_count: int
    
    # Coverage Scores (0.0 to 1.0)
    geometry_coverage_score: float = 1.0
    material_coverage_score: float = 0.0
    assembly_coverage_score: float = 0.0
    opening_coverage_score: float = 0.0
    spatial_coverage_score: float = 0.0
    
    readiness: QTOReadiness = QTOReadiness.REVIEW_REQUIRED
    readiness_notes: list[str] = Field(default_factory=list)


class MaterialLayer(BaseModel):
    layer_index: int
    material_name: str
    thickness_ft: float
    is_drywall: bool = False
    is_stud_cavity: bool = False
    is_insulation: bool = False
    is_masonry_or_concrete: bool = False
    provenance_status: DataProvenanceStatus = DataProvenanceStatus.VERIFIED_EXPLICIT


class WallAssembly(BaseModel):
    assembly_name: Optional[str] = None
    stud_type: Literal["LIGHT_GAUGE_STEEL", "WOOD", "STRUCTURAL_STEEL", "NONE"] = "LIGHT_GAUGE_STEEL"
    stud_size: str = '3-5/8"'  # e.g. 3-5/8", 6", 2x4, 2x6
    stud_gauge: str = "25ga"
    stud_spacing_in: int = 16  # 16" or 24" o.c.
    board_type: str = '5/8" Type X'
    board_thickness_in: float = 0.625
    side_a_layers: int = 1
    side_b_layers: int = 1
    has_insulation: bool = False
    fire_rating_hours: Optional[float] = None
    stc_rating: Optional[int] = None
    assembly_provenance: DataProvenanceStatus = DataProvenanceStatus.CONFIGURED_ASSUMPTION


class CanonicalOpening(BaseModel):
    id: str
    ifc_guid: str
    name: str = "Opening"
    opening_type: Literal["DOOR", "WINDOW", "GENERIC_VOID"]
    width_ft: float
    height_ft: float
    area_sqft: float
    elevation_z_ft: float = 0.0
    filling_guid: Optional[str] = None
    geometry_width_ft: Optional[float] = None
    geometry_height_ft: Optional[float] = None
    qto_width_ft: Optional[float] = None
    qto_height_ft: Optional[float] = None
    filling_width_ft: Optional[float] = None
    filling_height_ft: Optional[float] = None
    intersection_area_sqft: Optional[float] = None
    position_along_wall_ft: Optional[float] = None
    sill_height_ft: Optional[float] = None
    provenance_status: DataProvenanceStatus = DataProvenanceStatus.VERIFIED_EXPLICIT
    source_properties: dict[str, Any] = Field(default_factory=dict)


class CanonicalDoor(BaseModel):
    id: str
    ifc_guid: str
    name: str = "Door"
    width_ft: float
    height_ft: float
    door_type: Optional[str] = None
    opening_guid: Optional[str] = None


class CanonicalWindow(BaseModel):
    id: str
    ifc_guid: str
    name: str = "Window"
    width_ft: float
    height_ft: float
    window_type: Optional[str] = None
    opening_guid: Optional[str] = None


class CanonicalSpace(BaseModel):
    id: str
    ifc_guid: str
    name: str = "Space"
    long_name: Optional[str] = None
    storey_id: str
    net_floor_area_sqft: float
    gross_floor_area_sqft: float
    ceiling_height_ft: float
    perimeter_ft: float = 0.0
    bounding_wall_guids: list[str] = Field(default_factory=list)
    flooring_assembly: Optional[FlooringAssembly] = None
    provenance_status: DataProvenanceStatus = DataProvenanceStatus.VERIFIED_EXPLICIT
    source_psets: dict[str, Any] = Field(default_factory=dict)


class CanonicalStorey(BaseModel):
    id: str
    ifc_guid: str
    name: str = "Storey"
    elevation_ft: float
    height_ft: float = 10.0
    spaces: list[str] = Field(default_factory=list)
    walls: list[str] = Field(default_factory=list)


class CanonicalWall(BaseModel):
    id: str
    ifc_guid: str
    name: str = "Wall"
    tag: Optional[str] = None
    storey_id: str
    storey_name: str = "Level 01"
    
    # 3D Analytical Geometry
    length_ft: float
    nominal_thickness_in: float
    physical_height_ft: float
    start_point: tuple[float, float, float]
    end_point: tuple[float, float, float]
    length_provenance: DataProvenanceStatus = DataProvenanceStatus.DERIVED_GEOMETRIC
    height_provenance: DataProvenanceStatus = DataProvenanceStatus.DERIVED_GEOMETRIC
    
    # IFC Semantics & Properties
    is_external: bool = False
    is_load_bearing: bool = False
    fire_rating: Optional[str] = None
    acoustic_rating: Optional[str] = None
    
    # Spatial Topology
    adjacent_space_ids: list[str] = Field(default_factory=list)
    room_a_name: Optional[str] = None
    room_b_name: Optional[str] = None
    
    # Sub-elements
    openings: list[CanonicalOpening] = Field(default_factory=list)
    
    # Assemblies & Layers
    material_layers: list[MaterialLayer] = Field(default_factory=list)
    assembly: WallAssembly = Field(default_factory=WallAssembly)
    
    # Trade Scope Classification
    wall_classification: Literal[
        "INTERIOR_PARTITION",
        "DEMISING_WALL",
        "SHAFT_WALL",
        "EXTERIOR_WALL",
        "CURTAIN_WALL",
        "STRUCTURAL_CONCRETE",
        "MASONRY",
        "UNKNOWN"
    ] = "INTERIOR_PARTITION"
    
    # QTO Eligibility Gate
    qto_eligibility: QTOEligibilityStatus = QTOEligibilityStatus.ELIGIBLE
    eligibility_reasons: list[str] = Field(default_factory=list)
    
    drywall_scope_eligible: bool = True
    drywall_finish_height_ft: float = 10.0
    drywall_side_a_scope: bool = True
    drywall_side_b_scope: bool = True
    
    source_psets: dict[str, Any] = Field(default_factory=dict)


class FlooringType(str, enum.Enum):
    HARDWOOD = "HARDWOOD"
    ENGINEERED_WOOD = "ENGINEERED_WOOD"
    PORCELAIN_TILE = "PORCELAIN_TILE"
    CERAMIC_TILE = "CERAMIC_TILE"
    LUXURY_VINYL_PLANK = "LUXURY_VINYL_PLANK"
    CARPET = "CARPET"
    EPOXY = "EPOXY"
    POLISHED_CONCRETE = "POLISHED_CONCRETE"
    UNKNOWN = "UNKNOWN"


class FlooringAssembly(BaseModel):
    assembly_name: Optional[str] = None
    flooring_type: FlooringType = FlooringType.HARDWOOD
    tile_width_in: float = 12.0
    tile_length_in: float = 24.0
    box_coverage_sqft: float = 20.0
    waste_factor_pct: float = 10.0
    has_underlayment: bool = True
    underlayment_type: str = "Acoustic Vapor Barrier"
    has_waterproofing_membrane: bool = False
    grout_joint_width_in: float = 0.125
    baseboard_type: str = '3-1/4" MDF Baseboard'
    has_baseboard: bool = True
    adhesive_type: Optional[str] = None
    assembly_provenance: DataProvenanceStatus = DataProvenanceStatus.CONFIGURED_ASSUMPTION


class CanonicalSlab(BaseModel):
    id: str
    ifc_guid: str
    name: str
    storey_id: str
    storey_name: str = "Level 01"
    slab_type: Literal["FLOOR_SLAB", "ROOF_SLAB", "LANDING", "FOUNDATION", "GENERIC"] = "FLOOR_SLAB"
    area_sqft: float
    perimeter_ft: float = 0.0
    thickness_in: float = 6.0
    is_roof: bool = False
    slope_degrees: float = 0.0
    pitch_multiplier: float = 1.0
    flooring_eligible: bool = True
    flooring_assembly: Optional[FlooringAssembly] = None
    source_psets: dict[str, Any] = Field(default_factory=dict)


class CanonicalRoof(BaseModel):
    id: str
    ifc_guid: str
    name: str
    source_type: Literal["IfcRoof", "IfcSlab", "PDF_VECTOR", "UNKNOWN"] = "IfcRoof"
    storey_id: str
    storey_name: str = "Roof Level"
    roof_type: Literal["GABLE", "HIP", "FLAT", "SHED", "MANSARD", "COMPLEX", "UNKNOWN"] = "UNKNOWN"
    slope_degrees: Optional[float] = None
    pitch_ratio: Optional[str] = None
    pitch_multiplier: Optional[float] = None
    plan_area_sqft: float = 0.0
    true_surface_area_sqft: float = 0.0
    ridge_length_ft: float = 0.0
    hip_length_ft: float = 0.0
    valley_length_ft: float = 0.0
    eave_length_ft: float = 0.0
    rake_length_ft: float = 0.0
    elevation_ft: float = 0.0
    vertices: list[list[float]] = Field(default_factory=list)
    faces: list[list[int]] = Field(default_factory=list)
    face_map: list[int] = Field(default_factory=list)
    bbox: Optional[dict[str, float]] = None
    primary_material: str = "UNASSIGNED"
    material_evidence: Optional[str] = None
    material_provenance: DataProvenanceStatus = DataProvenanceStatus.UNKNOWN_UNRESOLVED
    slope_provenance: DataProvenanceStatus = DataProvenanceStatus.UNKNOWN_UNRESOLVED
    area_provenance: DataProvenanceStatus = DataProvenanceStatus.DERIVED_GEOMETRIC
    qto_eligibility: QTOEligibilityStatus = QTOEligibilityStatus.ELIGIBLE
    review_reasons: list[str] = Field(default_factory=list)
    source_psets: dict[str, Any] = Field(default_factory=dict)


class CanonicalColumn(BaseModel):
    id: str
    ifc_guid: str
    name: str
    storey_id: str


class CanonicalBuilding(BaseModel):
    id: str
    ifc_guid: str
    name: str
    storeys: list[CanonicalStorey] = Field(default_factory=list)


class CanonicalProject(BaseModel):
    id: str
    ifc_guid: str
    name: str
    schema_version: str
    length_unit: str
    buildings: list[CanonicalBuilding] = Field(default_factory=list)


class CanonicalBIMModel(BaseModel):
    project: CanonicalProject
    health_card: Optional[ModelHealthCard] = None
    storeys: list[CanonicalStorey] = Field(default_factory=list)
    spaces: list[CanonicalSpace] = Field(default_factory=list)
    walls: list[CanonicalWall] = Field(default_factory=list)
    openings: list[CanonicalOpening] = Field(default_factory=list)
    slabs: list[CanonicalSlab] = Field(default_factory=list)
    roofs: list[CanonicalRoof] = Field(default_factory=list)
    columns: list[CanonicalColumn] = Field(default_factory=list)
    flooring_elements: list[CanonicalFlooringElement] = Field(default_factory=list)
    source_hash: Optional[str] = None
    
    @property
    def total_wall_length_ft(self) -> float:
        return sum(w.length_ft for w in self.walls)
        
    @property
    def total_drywall_eligible_walls(self) -> int:
        return sum(1 for w in self.walls if w.qto_eligibility == QTOEligibilityStatus.ELIGIBLE)

    @property
    def total_floor_area_sqft(self) -> float:
        if self.spaces:
            return sum(s.net_floor_area_sqft for s in self.spaces)
        return sum(sl.area_sqft for sl in self.slabs if not sl.is_roof)

    @property
    def total_roof_area_sqft(self) -> float:
        if self.roofs:
            return sum(r.true_surface_area_sqft for r in self.roofs)
        return sum(sl.area_sqft * sl.pitch_multiplier for sl in self.slabs if sl.is_roof)

