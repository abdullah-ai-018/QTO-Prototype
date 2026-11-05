"""Canonical Drawing Model and PDF Capability Models.
Conforms strictly to the ProTake / MRPOOL Single Source of Truth architecture:
- PDF canonical geometry = Canvas geometry = Selected geometry = QTO geometry.
- Preserves original PDF geometry and reconstructed geometry separately.
- Zero synthetic fallbacks or guessed geometry.
"""
from __future__ import annotations

import enum
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field

from app.bim.models import DataProvenanceStatus, QTOEligibilityStatus


class PDFType(str, enum.Enum):
    VECTOR_PDF = "VECTOR_PDF"
    SCANNED_PDF = "SCANNED_PDF"
    HYBRID_PDF = "HYBRID_PDF"


class DrawingType(str, enum.Enum):
    """Architectural Drawing Category per sheet or region."""
    FLOOR_PLAN = "FLOOR_PLAN"
    ROOF_PLAN = "ROOF_PLAN"
    REFLECTED_CEILING_PLAN = "REFLECTED_CEILING_PLAN"
    PLUMBING_PLAN = "PLUMBING_PLAN"
    ELECTRICAL_PLAN = "ELECTRICAL_PLAN"
    HVAC_PLAN = "HVAC_PLAN"
    ELEVATION = "ELEVATION"
    SECTION = "SECTION"
    DETAIL = "DETAIL"
    SCHEDULE = "SCHEDULE"
    LEGEND = "LEGEND"
    TITLE_SHEET = "TITLE_SHEET"
    GENERAL_NOTES = "GENERAL_NOTES"
    FOUNDATION_PLAN = "FOUNDATION_PLAN"
    FURNITURE_PLAN = "FURNITURE_PLAN"
    DETAIL_DRAWING = "DETAIL_DRAWING"
    PLUMBING_DRAWING = "PLUMBING_DRAWING"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class DrawingRegionCategory(str, enum.Enum):
    """Explicit architectural regions isolating project geometry from annotation/detail geometry."""
    DRAWING_REGION = "DRAWING_REGION"
    DETAIL_REGION = "DETAIL_REGION"
    LEGEND_REGION = "LEGEND_REGION"
    TITLE_BLOCK_REGION = "TITLE_BLOCK_REGION"
    NOTES_REGION = "NOTES_REGION"


class GeometrySemanticClass(str, enum.Enum):
    """Strict semantic classification of native CAD vector linework."""
    WALL = "WALL"
    DOOR = "DOOR"
    WINDOW = "WINDOW"
    ROOM_BOUNDARY = "ROOM_BOUNDARY"
    ROOF_BOUNDARY = "ROOF_BOUNDARY"
    FLOOR_AREA = "FLOOR_AREA"
    PIPE = "PIPE"
    FIXTURE = "FIXTURE"
    EQUIPMENT = "EQUIPMENT"
    DIMENSION_LINE = "DIMENSION_LINE"
    WITNESS_LINE = "WITNESS_LINE"
    GRID = "GRID"
    TITLE_BLOCK = "TITLE_BLOCK"
    DETAIL_GEOMETRY = "DETAIL_GEOMETRY"
    SECTION_GEOMETRY = "SECTION_GEOMETRY"
    LEGEND_GEOMETRY = "LEGEND_GEOMETRY"
    SYMBOL = "SYMBOL"
    HATCH = "HATCH"
    ANNOTATION = "ANNOTATION"
    UNKNOWN = "UNKNOWN"


class DrawingObjectType(str, enum.Enum):
    """Classification of all architectural drawing objects on a sheet."""
    LINE = "LINE"
    POLYLINE = "POLYLINE"
    POLYGON = "POLYGON"
    RECTANGLE = "RECTANGLE"
    CURVE = "CURVE"
    ARC = "ARC"
    BEZIER = "BEZIER"
    HATCH = "HATCH"
    TEXT = "TEXT"
    DIMENSION = "DIMENSION"
    GRID = "GRID"
    WALL = "WALL"
    PHYSICAL_WALL = "PHYSICAL_WALL"
    MASONRY_WALL = "MASONRY_WALL"
    CONCRETE_WALL = "CONCRETE_WALL"
    PARTITION_WALL = "PARTITION_WALL"
    DRYWALL_PARTITION = "DRYWALL_PARTITION"
    SECTION_WALL_REPRESENTATION = "SECTION_WALL_REPRESENTATION"
    WALL_REFERENCE = "WALL_REFERENCE"
    DOOR = "DOOR"
    WINDOW = "WINDOW"
    OPENING = "OPENING"
    ROOM = "ROOM"
    ROOF = "ROOF"
    ROOF_PLANE = "ROOF_PLANE"
    RIDGE = "RIDGE"
    HIP = "HIP"
    VALLEY = "VALLEY"
    EAVE = "EAVE"
    RAKE = "RAKE"
    SLOPE_ARROW = "SLOPE_ARROW"
    COLUMN = "COLUMN"
    STAIR = "STAIR"
    LEVEL = "LEVEL"
    FLOOR_LINE = "FLOOR_LINE"
    ROOF_LINE = "ROOF_LINE"
    SLAB = "SLAB"
    FOUNDATION = "FOUNDATION"
    FOUNDATION_WALL = "FOUNDATION_WALL"
    FOOTING = "FOOTING"
    FOUNDATION_OPENING = "FOUNDATION_OPENING"
    FURNITURE = "FURNITURE"
    FIXTURE = "FIXTURE"
    PLUMBING_FIXTURE = "PLUMBING_FIXTURE"
    PIPE = "PIPE"
    DRAIN = "DRAIN"
    WATER_LINE = "WATER_LINE"
    SOIL_LINE = "SOIL_LINE"
    WASTE_LINE = "WASTE_LINE"
    VENT = "VENT"
    MANHOLE = "MANHOLE"
    GULLY = "GULLY"
    GULLY_TRAP = "GULLY_TRAP"
    FLOOR_TRAP = "FLOOR_TRAP"
    CLEANOUT = "CLEANOUT"
    SEWER_LINE = "SEWER_LINE"
    LEGEND = "LEGEND"
    DETAIL_REGION = "DETAIL_REGION"
    MATERIAL = "MATERIAL"
    COMPONENT = "COMPONENT"
    SECTION_LINE = "SECTION_LINE"
    SECTION_LEVEL_LINE = "SECTION_LEVEL_LINE"
    SECTION_STRUCTURAL_LINE = "SECTION_STRUCTURAL_LINE"
    LAWN = "LAWN"
    CAR_PORCH = "CAR_PORCH"
    GATE = "GATE"
    TERRACE = "TERRACE"
    SYMBOL = "SYMBOL"
    PLUMBING_SYMBOL = "PLUMBING_SYMBOL"
    CENTERLINE = "CENTERLINE"
    LEADER = "LEADER"
    ANNOTATION = "ANNOTATION"
    GENERAL_ANNOTATION = "GENERAL_ANNOTATION"
    GENERAL_NOTE = "GENERAL_NOTE"
    PLUMBING_NOTE = "PLUMBING_NOTE"
    NOTE_GEOMETRY = "NOTE_GEOMETRY"
    NOTE_TEXT = "NOTE_TEXT"
    TITLE_BLOCK = "TITLE_BLOCK"
    TITLE_BLOCK_TEXT = "TITLE_BLOCK_TEXT"
    DETAIL_MARKER = "DETAIL_MARKER"
    DETAIL_CALLOUT = "DETAIL_CALLOUT"
    SCALE_MARKER = "SCALE_MARKER"
    NORTH_ARROW = "NORTH_ARROW"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class SemanticTextRole(str, enum.Enum):
    """Semantic role of text in an architectural sheet."""
    DIMENSION_TEXT = "DIMENSION_TEXT"
    ROOM_LABEL = "ROOM_LABEL"
    WALL_NOTE = "WALL_NOTE"
    MATERIAL_NOTE = "MATERIAL_NOTE"
    TRADE_NOTE = "TRADE_NOTE"
    SECTION_LABEL = "SECTION_LABEL"
    DETAIL_LABEL = "DETAIL_LABEL"
    DETAIL_CALLOUT = "DETAIL_CALLOUT"
    ELEVATION_LABEL = "ELEVATION_LABEL"
    DRAWING_TITLE = "DRAWING_TITLE"
    SHEET_NUMBER = "SHEET_NUMBER"
    SCALE_TEXT = "SCALE_TEXT"
    SCALE_LABEL = "SCALE_LABEL"
    GENERAL_NOTE = "GENERAL_NOTE"
    LEGEND_TEXT = "LEGEND_TEXT"
    TITLE_BLOCK_TEXT = "TITLE_BLOCK_TEXT"
    TITLE_BLOCK = "TITLE_BLOCK"
    ANNOTATION = "ANNOTATION"
    GENERAL_ANNOTATION = "GENERAL_ANNOTATION"
    GENERAL_TEXT = "GENERAL_TEXT"
    GRID_LABEL = "GRID_LABEL"
    LEVEL_LABEL = "LEVEL_LABEL"
    NOTE = "NOTE"
    PLUMBING_NOTE = "PLUMBING_NOTE"
    ROOF_LABEL = "ROOF_LABEL"
    MATERIAL_LABEL = "MATERIAL_LABEL"
    UNKNOWN = "UNKNOWN"
    UNKNOWN_TEXT = "UNKNOWN_TEXT"


class SemanticClassificationStatus(str, enum.Enum):
    """Auditable state of semantic inference - no guesses allowed."""
    VERIFIED_EXPLICIT = "VERIFIED_EXPLICIT"
    DERIVED_GEOMETRIC = "DERIVED_GEOMETRIC"
    CONFIGURED_ASSUMPTION = "CONFIGURED_ASSUMPTION"
    UNKNOWN_UNRESOLVED = "UNKNOWN_UNRESOLVED"
    SUPPORTED = "SUPPORTED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    UNKNOWN = "UNKNOWN"


class SemanticContentType(str, enum.Enum):
    DRAWING_TITLE = "DRAWING_TITLE"
    SLOPE_ANNOTATION = "SLOPE_ANNOTATION"
    DIMENSION_TEXT = "DIMENSION_TEXT"
    ROOF_LABEL = "ROOF_LABEL"
    ROOM_LABEL = "ROOM_LABEL"
    NOTES = "NOTES"
    MATERIAL_ANNOTATION = "MATERIAL_ANNOTATION"
    SCALE_LABEL = "SCALE_LABEL"
    GENERAL_TEXT = "GENERAL_TEXT"
    GRID_LABEL = "GRID_LABEL"
    SHEET_NUMBER = "SHEET_NUMBER"


class GeometryPrimitiveType(str, enum.Enum):
    LINE = "LINE"
    POLYLINE = "POLYLINE"
    BEZIER = "BEZIER"
    RECTANGLE = "RECTANGLE"
    QUAD = "QUAD"
    CLOSED_BOUNDARY = "CLOSED_BOUNDARY"
    COMPOUND_PATH = "COMPOUND_PATH"


class ScaleStatus(str, enum.Enum):
    VERIFIED_EXPLICIT = "VERIFIED_EXPLICIT"
    CALIBRATED_DIMENSION = "CALIBRATED_DIMENSION"
    SCALE_UNRESOLVED = "SCALE_UNRESOLVED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    CONFIGURED_ASSUMPTION = "CONFIGURED_ASSUMPTION"


class TransformMetadata(BaseModel):
    """Explicitly records all transformations applied to source geometry.
    Prevents silent geometric modification.
    """
    applied_snapping_tolerance_pt: float = 0.0
    snap_count: int = 0
    translation_x_pt: float = 0.0
    translation_y_pt: float = 0.0
    scale_ft_per_pt: Optional[float] = None
    rotation_deg: float = 0.0
    reconstruction_method: str = "NATIVE_EXPLICIT"
    notes: list[str] = Field(default_factory=list)


class ScaleEvidence(BaseModel):
    """Auditable evidence establishing real-world drawing scale.
    Never defaults to an arbitrary or guessed scale.
    """
    scale_status: ScaleStatus = ScaleStatus.SCALE_UNRESOLVED
    scale_string: Optional[str] = None
    scale_detected: Optional[str] = None
    scale_validated: str = "UNRESOLVED"  # "VERIFIED" | "REVIEW_REQUIRED" | "UNRESOLVED"
    scale_display: str = "UNRESOLVED"
    scale_evidence_type: str = "NONE"  # "EXPLICIT_TEXT" | "CALIBRATED_DIMENSION" | "NONE"
    ratio: Optional[float] = None
    ft_per_pt: Optional[float] = None
    unit: str = "ft"
    source_text_id: Optional[str] = None
    calibrating_dimension_id: Optional[str] = None
    dimension_evidence: Optional[str] = None
    vector_measurement: Optional[float] = None
    expected_measurement: Optional[float] = None
    actual_measurement: Optional[float] = None
    residual_error: Optional[float] = None
    confidence: float = 1.0
    scale_source: str = "TITLE_BLOCK_OR_EXPLICIT_TEXT"
    provenance: DataProvenanceStatus = DataProvenanceStatus.UNKNOWN_UNRESOLVED
    notes: list[str] = Field(default_factory=list)



class DrawingTextObject(BaseModel):
    """Native PDF text element decoded directly from PDF content streams with full provenance."""
    id: str
    text_id: str = ""
    source_text_id: Optional[str] = None
    page: int = 1
    page_number: int = 1
    text: str = ""
    content: str = ""
    semantic_type: SemanticContentType = SemanticContentType.GENERAL_TEXT
    semantic_role: SemanticTextRole = SemanticTextRole.GENERAL_ANNOTATION
    bbox_pdf: list[float] = Field(default_factory=list)  # [x0, y0, x1, y1] in 72 DPI PDF points
    bbox: list[float] = Field(default_factory=list)
    origin_pdf: list[float] = Field(default_factory=list)  # [x, y] text baseline origin
    x: Optional[float] = None
    y: Optional[float] = None
    width: float = 0.0
    height: float = 0.0
    drawing_region_id: Optional[str] = None
    font: Optional[str] = None
    font_name: Optional[str] = None
    font_size: float = 0.0
    rotation: float = 0.0
    rotation_deg: float = 0.0
    color: Optional[str] = None
    color_rgb: Optional[tuple[int, int, int]] = None
    layer: str = "Text"
    transformed_bbox_ft: Optional[list[float]] = None
    classification_status: SemanticClassificationStatus = SemanticClassificationStatus.SUPPORTED
    confidence: float = 1.0
    provenance: DataProvenanceStatus = DataProvenanceStatus.VERIFIED_EXPLICIT
    source: str = "PDF_NATIVE_TEXT"
    source_object_id: Optional[str] = None
    source_hash: str = ""
    is_duplicate: bool = False
    display_priority: int = 50
    overlap_group_id: Optional[str] = None
    is_suppressed_in_clean_mode: bool = False

    def model_post_init(self, __context: Any) -> None:
        if not self.text_id:
            self.text_id = self.id
        if not self.content:
            self.content = self.text
        if not self.text:
            self.text = self.content
        if not self.page:
            self.page = self.page_number
        if not self.page_number:
            self.page_number = self.page
        if not self.bbox and self.bbox_pdf:
            self.bbox = list(self.bbox_pdf)
        if not self.bbox_pdf and self.bbox:
            self.bbox_pdf = list(self.bbox)
        if len(self.bbox_pdf) == 4:
            self.width = round(abs(self.bbox_pdf[2] - self.bbox_pdf[0]), 2)
            self.height = round(abs(self.bbox_pdf[3] - self.bbox_pdf[1]), 2)
            if self.x is None:
                self.x = self.bbox_pdf[0]
            if self.y is None:
                self.y = self.bbox_pdf[1]
        if not self.font and self.font_name:
            self.font = self.font_name
        if not self.font_name and self.font:
            self.font_name = self.font
        if not self.rotation and self.rotation_deg:
            self.rotation = self.rotation_deg
        if not self.rotation_deg and self.rotation:
            self.rotation_deg = self.rotation


class DrawingGeometryObject(BaseModel):
    """Native PDF drawing geometry object.
    Maintains separate source coordinates, normalized coordinates, and transformed coordinates
    to mathematically prove that reconstruction did not fabricate geometry.
    """
    id: str
    geometry_id: str = ""
    source_vector_id: Optional[str] = None
    page: int = 1
    page_number: int = 1
    primitive_type: GeometryPrimitiveType
    path_type: Optional[str] = None
    drawing_region_id: Optional[str] = None
    layer: str = "Geometry"
    layer_name: Optional[str] = None
    semantic_class: GeometrySemanticClass = GeometrySemanticClass.UNKNOWN
    trade: str = "NONE"
    confidence: float = 1.0
    takeoff_eligible: bool = False
    source_reference: str = ""
    # 1. Raw native PDF coordinates (unaltered 72 pt/in)
    source_points_pdf: list[list[float]] = Field(default_factory=list)
    source_coordinates: list[list[float]] = Field(default_factory=list)
    coordinates: list[list[float]] = Field(default_factory=list)
    source_page: int = 1
    source_object_id: Optional[int] = None
    source_bbox: list[float] = Field(default_factory=list)
    source_text: Optional[str] = None
    source_vector_reference: Optional[str] = None
    source_hash: str = ""
    region_type: DrawingRegionCategory = DrawingRegionCategory.DRAWING_REGION
    # 2. Normalized page coordinates (0 to width_pt, 0 to height_pt, origin bottom-left or top-left standard)
    normalized_points: list[list[float]] = Field(default_factory=list)
    # 3. Transformed real-world coordinates in feet (only populated once scale is verified)
    transformed_points_ft: list[list[float]] = Field(default_factory=list)
    is_closed: bool = False
    stroke_color: Optional[tuple[float, float, float]] = None
    fill_color: Optional[tuple[float, float, float]] = None
    stroke: Optional[dict[str, Any]] = None
    fill: Optional[dict[str, Any]] = None
    stroke_width: float = 1.0
    bbox_pdf: list[float] = Field(default_factory=list)  # [min_x, min_y, max_x, max_y]
    bbox: list[float] = Field(default_factory=list)
    transform_metadata: TransformMetadata = Field(default_factory=TransformMetadata)
    source: str = "PDF_VECTOR"
    provenance: DataProvenanceStatus = DataProvenanceStatus.VERIFIED_EXPLICIT

    def model_post_init(self, __context: Any) -> None:
        if not self.geometry_id:
            self.geometry_id = self.id
        if not self.page:
            self.page = self.page_number
        if not self.page_number:
            self.page_number = self.page
        if not self.source_page:
            self.source_page = self.page_number
        if not self.source_coordinates and self.source_points_pdf:
            self.source_coordinates = [list(p) for p in self.source_points_pdf]
        if not self.coordinates and self.source_points_pdf:
            self.coordinates = [list(p) for p in self.source_points_pdf]
        if not self.source_points_pdf and self.coordinates:
            self.source_points_pdf = [list(p) for p in self.coordinates]
        if not self.bbox and self.bbox_pdf:
            self.bbox = list(self.bbox_pdf)
        if not self.bbox_pdf and self.bbox:
            self.bbox_pdf = list(self.bbox)
        if not self.source_bbox and self.bbox_pdf:
            self.source_bbox = list(self.bbox_pdf)
        if not self.layer and self.layer_name:
            self.layer = self.layer_name
        if not self.layer_name and self.layer:
            self.layer_name = self.layer
        if not self.source_vector_reference and self.source_vector_id:
            self.source_vector_reference = self.source_vector_id


class DrawingDimensionObject(BaseModel):
    """Architectural dimension decoded from geometry and associated dimension text."""
    id: str
    page_number: int
    dimension_text: str
    text_object_id: str
    nominal_length_ft: Optional[float] = None
    measured_value: Optional[float] = None
    unit: Optional[str] = None  # "mm", "ft", "in", "m"
    start_pt: list[float]  # [x, y] in PDF points
    end_pt: list[float]    # [x, y] in PDF points
    start_pt_ft: Optional[list[float]] = None
    end_pt_ft: Optional[list[float]] = None
    measured_points_distance: float = 0.0  # distance in PDF points
    measured_length_ft: Optional[float] = None
    measured_length_mm: Optional[float] = None
    dimension_line_id: Optional[str] = None
    witness_line_ids: list[str] = Field(default_factory=list)
    associated_geometry_ids: list[str] = Field(default_factory=list)
    association_status: Literal["VERIFIED_EXPLICIT", "REVIEW_REQUIRED", "UNKNOWN"] = "REVIEW_REQUIRED"
    calibration_ratio: Optional[float] = None  # ft per pt
    is_calibrated: bool = False
    provenance: DataProvenanceStatus = DataProvenanceStatus.VERIFIED_EXPLICIT


class TextGeometryRelationship(BaseModel):
    """Deterministic spatial/semantic link between content and geometry."""
    relationship_id: str
    page_number: int
    relationship_type: str  # "SLOPE_TO_ROOF_BOUNDARY", "DIMENSION_TO_LINE", "GRID_LABEL_TO_LINE", etc.
    source_object_id: str   # e.g. text ID or dimension ID
    target_object_id: str   # e.g. geometry ID or roof ID
    method: Literal[
        "SPATIAL_CONTAINMENT",
        "PROXIMITY",
        "INTERSECTION",
        "ALIGNMENT",
        "WITNESS_GEOMETRY",
        "EXPLICIT_SYNTAX"
    ]
    distance_pt: float = 0.0
    is_contained: bool = False
    confidence: float = 1.0
    status: Literal["SUPPORTED", "REVIEW_REQUIRED", "UNKNOWN"] = "SUPPORTED"
    provenance: DataProvenanceStatus = DataProvenanceStatus.VERIFIED_EXPLICIT
    notes: Optional[str] = None


# Backwards compatibility alias
ContentGeometryAssociation = TextGeometryRelationship


class SemanticDrawingObject(BaseModel):
    """First-class architectural semantic object reconstructed from native drawing data."""
    id: str
    page_number: int
    object_type: DrawingObjectType
    layer: str  # "ROOF", "WALLS", "DIMENSIONS", "GRID", "TITLE_BLOCK", "HATCH", "ANNOTATIONS", etc.
    source_vector_ids: list[str] = Field(default_factory=list)
    source_text_ids: list[str] = Field(default_factory=list)
    source_points_pdf: list[list[float]] = Field(default_factory=list)
    normalized_points: list[list[float]] = Field(default_factory=list)
    transformed_points_ft: list[list[float]] = Field(default_factory=list)
    bbox_pdf: list[float] = Field(default_factory=list)
    transformed_bbox_ft: Optional[list[float]] = None
    label: Optional[str] = None
    properties: dict[str, Any] = Field(default_factory=dict)
    source_object_id: Optional[str] = None
    source_type: str = "PDF_VECTOR"
    semantic_type: str = "UNKNOWN"
    trade_scope: str = "NONE"
    qto_eligible: bool = False
    qto_reason: str = ""
    classification_method: str = "DIRECT_VECTOR_EXTRACTION"
    classification_evidence: str = ""
    classification_status: SemanticClassificationStatus = SemanticClassificationStatus.SUPPORTED
    confidence: float = 1.0
    provenance: DataProvenanceStatus = DataProvenanceStatus.VERIFIED_EXPLICIT
    qto_reference_id: Optional[str] = None


class DrawingLayerInfo(BaseModel):
    """Visual layer metadata for frontend canvas filtering."""
    name: str
    display_name: str
    object_count: int = 0
    color: str = "#94a3b8"
    is_visible: bool = True


class PDFPageCapabilities(BaseModel):
    """Detailed structural capabilities of a single PDF page."""
    page_number: int
    width_pt: float
    height_pt: float
    rotation: int = 0
    vector_path_count: int = 0
    drawing_command_count: int = 0
    text_char_count: int = 0
    text_word_count: int = 0
    text_block_count: int = 0
    image_count: int = 0
    page_pdf_type: PDFType = PDFType.VECTOR_PDF
    has_native_vectors: bool = False
    has_native_text: bool = False
    has_raster_images: bool = False
    confidence: float = 1.0


class PDFDocumentCapabilities(BaseModel):
    """Capability and type classification report for an uploaded PDF."""
    file_path: str
    file_name: str
    file_size_bytes: int
    source_hash: str  # SHA-256
    page_count: int
    pdf_type: PDFType
    total_vector_paths: int = 0
    total_drawing_commands: int = 0
    total_text_chars: int = 0
    total_images: int = 0
    is_vector_supported: bool = True
    readiness_notes: list[str] = Field(default_factory=list)
    pages: list[PDFPageCapabilities] = Field(default_factory=list)

    @property
    def is_supported(self) -> bool:
        return self.is_vector_supported



class GeometryValidationReport(BaseModel):
    """Phase 3 Frozen Specification: Full auditable summary of drawing geometry and topology."""
    source_identity: str = "PDF_DOCUMENT"
    source_hash: str
    page_number: int
    scale_status: ScaleStatus = ScaleStatus.SCALE_UNRESOLVED
    unresolved_scale: bool = False
    geometry_validity: bool = True
    closed_polygon_validity: bool = True
    has_self_intersections: bool = False
    has_degenerate_geometry: bool = False
    has_disconnected_components: bool = False
    native_pdf_paths: int = 0
    reconstructed_geometries: int = 0
    closed_boundaries: int = 0
    open_boundaries: int = 0
    fragmented_boundaries: int = 0
    repaired_boundaries: int = 0
    transformations_applied: list[TransformMetadata] = Field(default_factory=list)
    scale_evidence: ScaleEvidence = Field(default_factory=ScaleEvidence)
    missing_semantic_evidence: list[str] = Field(default_factory=list)
    associated_text_count: int = 0
    associated_dimension_count: int = 0
    ambiguous_associations_count: int = 0
    review_required_objects_count: int = 0
    reconciliation_results: dict[str, Any] = Field(default_factory=dict)
    validation_state: Literal["PASS", "REVIEW_REQUIRED", "BLOCKED"] = "PASS"
    validation_notes: list[str] = Field(default_factory=list)


class DrawingRegion(BaseModel):
    """Discrete architectural drawing context on a sheet (e.g. Page 10 multi-plan or Page 1 details)."""
    region_id: str
    page_number: int
    bbox_pdf: list[float]  # [x0, y0, x1, y1] in PDF points
    drawing_type: DrawingType
    title: str
    region_category: DrawingRegionCategory = DrawingRegionCategory.DRAWING_REGION
    takeoff_eligible: bool = True
    scale: ScaleEvidence = Field(default_factory=ScaleEvidence)
    units: str = "ft-in"
    source_objects: list[str] = Field(default_factory=list)
    source_vector_ids: list[str] = Field(default_factory=list)
    source_text_ids: list[str] = Field(default_factory=list)
    semantic_object_ids: list[str] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)


class CrossPageReference(BaseModel):
    """Auditable semantic reference linking entities across different sheets."""
    reference_id: str
    source_page: int
    source_region_id: Optional[str] = None
    target_page: int
    target_region_id: Optional[str] = None
    reference_type: str  # "SECTION_CALLOUT", "ELEVATION_PROJECTION", "ROOF_TO_SECTION"
    marker_text: str
    description: str


class TradeTakeoffItem(BaseModel):
    """Auditable takeoff line item for a specific trade adhering to Phase 7B contract."""
    item_id: str
    item_code: str = ""
    item: str = ""
    trade: str  # "DRYWALL", "FLOORING", "ROOFING", "PLUMBING", "OTHER"
    category: str = ""
    name: str = ""
    description: str = ""
    quantity: float = 0.0
    unit: str = "SF"  # "SF", "LF", "EA"
    gross_quantity: float = 0.0
    gross: float = 0.0
    deduction_quantity: float = 0.0
    deduction: float = 0.0
    net_quantity: float = 0.0
    net: float = 0.0
    material: str = ""
    source_sheet: str = ""
    source_page: int = 1
    page_number: int = 1
    region_id: Optional[str] = None
    source_region: str = "MAIN"
    source_object_id: str = ""
    canonical_object_id: str = ""
    source_object_ids: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    status: Literal["VERIFIED", "REVIEW_REQUIRED", "BLOCKED", "NOT_APPLICABLE", "NON_QTO"] = "VERIFIED"
    scope_status: str = "VERIFIED"
    validation_status: str = "VERIFIED"
    measurement_basis: str = ""
    provenance: str = ""
    provenance_notes: list[str] = Field(default_factory=list)
    calculation_details: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        if not self.item_code:
            self.item_code = self.item_id
        if not self.item:
            self.item = self.item_code
        if not self.description:
            self.description = self.name
        if not self.name:
            self.name = self.description
        if not self.gross:
            self.gross = self.gross_quantity
        if not self.gross_quantity:
            self.gross_quantity = self.gross
        if not self.deduction:
            self.deduction = self.deduction_quantity
        if not self.deduction_quantity:
            self.deduction_quantity = self.deduction
        if not self.net:
            self.net = self.net_quantity or self.quantity
        if not self.net_quantity:
            self.net_quantity = self.net
        if not self.quantity:
            self.quantity = self.net
        if not self.source_object_id and self.canonical_object_id:
            self.source_object_id = self.canonical_object_id
        if not self.canonical_object_id and self.source_object_id:
            self.canonical_object_id = self.source_object_id
        if not self.source_sheet:
            self.source_sheet = f"Sheet {self.source_page:02d}"


class PageTakeoffSummary(BaseModel):
    """Trade-specific takeoff totals and gating decisions for a single sheet/page."""
    page_number: int
    sheet_title: str
    drawing_type: DrawingType
    drywall_sf: float = 0.0
    flooring_sf: float = 0.0
    roofing_sf: float = 0.0
    drywall_status: str = "NOT_APPLICABLE"
    flooring_status: str = "NOT_APPLICABLE"
    roofing_status: str = "NOT_APPLICABLE"
    plumbing_status: str = "NOT_IMPLEMENTED"
    items: list[TradeTakeoffItem] = Field(default_factory=list)
    gating_decision: Literal["PASS", "REVIEW_REQUIRED", "BLOCKED"] = "PASS"
    gating_notes: list[str] = Field(default_factory=list)
    native_objects_count: int = 0
    canonical_objects_count: int = 0
    takeoff_objects_count: int = 0
    excluded_objects_count: int = 0
    review_objects_count: int = 0


class CanonicalDrawingPage(BaseModel):
    """Complete canonical drawing representation of one sheet/page."""
    page_number: int
    width_pt: float
    height_pt: float
    rotation: int = 0
    sheet_number: str = "UNASSIGNED"
    sheet_title: str = "ARCHITECTURAL SHEET"
    discipline: str = "Architectural"
    drawing_type: DrawingType = DrawingType.OTHER
    units: str = "ft-in"
    scale_evidence: ScaleEvidence = Field(default_factory=ScaleEvidence)
    regions: list[DrawingRegion] = Field(default_factory=list)
    cross_page_references: list[CrossPageReference] = Field(default_factory=list)
    native_text_count: int = 0
    native_vector_count: int = 0
    native_image_count: int = 0
    text_objects: list[DrawingTextObject] = Field(default_factory=list)
    geometry_objects: list[DrawingGeometryObject] = Field(default_factory=list)
    dimension_objects: list[DrawingDimensionObject] = Field(default_factory=list)
    closed_boundaries: list[DrawingGeometryObject] = Field(default_factory=list)
    associations: list[TextGeometryRelationship] = Field(default_factory=list)
    relationships: list[TextGeometryRelationship] = Field(default_factory=list)
    semantic_objects: list[SemanticDrawingObject] = Field(default_factory=list)
    layers: list[DrawingLayerInfo] = Field(default_factory=list)
    roof_planes: list[dict[str, Any]] = Field(default_factory=list)
    takeoff_summary: Optional[PageTakeoffSummary] = None
    trade_takeoff: Optional[dict[str, Any]] = None
    validation_report: Optional[GeometryValidationReport] = None


class CanonicalDrawingDocument(BaseModel):
    """Top-level Canonical Drawing Document matching the Canonical Model contract."""
    document_id: str
    source_file_name: str
    source_hash: str  # SHA-256
    file_size_bytes: int
    page_count: int
    pdf_type: PDFType = PDFType.VECTOR_PDF
    capabilities: Optional[PDFDocumentCapabilities] = None
    pages: list[CanonicalDrawingPage] = Field(default_factory=list)
    project_qto: Optional[dict[str, Any]] = None
    boq: list[dict[str, Any]] = Field(default_factory=list)
    sheet_audit_matrix: list[dict[str, Any]] = Field(default_factory=list)

