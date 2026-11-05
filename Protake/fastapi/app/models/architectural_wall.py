"""Canonical Architectural Wall Model & Semantic Interpretation Entities.

Represents physical architectural building elements (walls, assemblies, openings,
and blueprint interpretations) rather than unclassified CAD line primitives.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PhysicalWallType(str, Enum):
    DRYWALL_PARTITION = "drywall_partition"
    MASONRY = "masonry"
    CONCRETE = "concrete"
    FURRED_WALL = "furred_wall"
    SHAFT_WALL = "shaft_wall"
    EXTERIOR_WALL = "exterior_wall"
    STOREFRONT_GLAZING = "storefront_glazing"
    UNKNOWN_WALL = "unknown_wall"


class WallClassification(str, Enum):
    INTERIOR = "interior"
    EXTERIOR = "exterior"
    PARTITION = "partition"
    SHAFT = "shaft"
    PLUMBING_CHASE = "plumbing_chase"
    DEMISING = "demising"
    CURTAIN_WALL = "curtain_wall"
    UNKNOWN = "unknown"


class ThicknessSource(str, Enum):
    PAIRED_GEOMETRY = "paired_geometry"
    WALL_SCHEDULE = "wall_schedule"
    DIMENSION_STRING = "dimension_string"
    DRAWING_CALLOUT = "drawing_callout"
    INFERRED = "inferred"
    PROJECT_DEFAULT = "project_default"


class HeightSource(str, Enum):
    ROOM_CEILING_SPEC = "room_ceiling_spec"
    ELEVATION_CALLOUT = "elevation_callout"
    SECTION_DETAIL = "section_detail"
    RCP_MATCH = "rcp_match"
    PROJECT_DEFAULT = "project_default"


class DrywallScopeDecision(str, Enum):
    REQUIRED = "required"
    CONFIRMED = "confirmed"
    NOT_REQUIRED = "not_required"
    PARTIAL = "partial"
    NEEDS_REVIEW = "needs_review"
    UNRESOLVED = "unresolved"


class WallDecisionState(str, Enum):
    NON_WALL = "non_wall"
    WALL_CANDIDATE_NEEDS_REVIEW = "wall_candidate_needs_review"
    PHYSICAL_WALL_CONFIRMED = "physical_wall_confirmed"
    # Real room-boundary support and a real measured centerline, but only one
    # detected face -- Face B was never independently identified (no second
    # paired stroke). Distinct from PHYSICAL_WALL_CONFIRMED (dual independent
    # faces) on purpose: it must never be treated as equal-strength evidence,
    # only as its own honestly-lower-confidence tier.
    PHYSICAL_WALL_CONFIRMED_SINGLE_SOURCE = "physical_wall_confirmed_single_source"
    WALL_ASSEMBLY_CONFIRMED = "wall_assembly_confirmed"
    DRYWALL_SCOPE_CONFIRMED = "drywall_scope_confirmed"


@dataclass
class WallFace:
    segment_ids: list[int] = field(default_factory=list)
    start_norm: dict[str, float] = field(default_factory=lambda: {"x": 0.0, "y": 0.0})
    end_norm: dict[str, float] = field(default_factory=lambda: {"x": 0.0, "y": 0.0})
    length_ft: float = 0.0
    is_finished_gwb: bool = False
    adjacent_room_id: int | None = None
    finish_spec: str | None = None


@dataclass
class WallGeometry:
    face_a: WallFace = field(default_factory=WallFace)
    face_b: WallFace = field(default_factory=WallFace)
    centerline_start: dict[str, float] = field(default_factory=lambda: {"x": 0.0, "y": 0.0})
    centerline_end: dict[str, float] = field(default_factory=lambda: {"x": 0.0, "y": 0.0})
    thickness_in: float = 4.875
    thickness_variance_in: float = 0.0
    overlap_ratio: float = 1.0
    length_ft: float = 0.0
    opening_interruptions: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class TagAssociationEvidence:
    tag_id: str | None = None
    text_source_id: str | None = None
    distance_to_wall_ft: float = 0.0
    leader_relationship: bool = False
    orientation_relationship: bool = False
    association_confidence: float = 0.0
    association_reason: str = "TAG_UNRESOLVED"


@dataclass
class WallEvidenceScore:
    parallel_faces: float = 0.0          # +0.25
    physical_stroke_align: float = 0.0   # +0.20
    continuity: float = 0.0              # +0.15
    opening_consistency: float = 0.0     # +0.10
    room_adjacency: float = 0.0          # +0.10
    wall_tag: float = 0.0                # +0.05
    schedule: float = 0.0                # +0.10
    negative_penalties: float = 0.0      # -0.30
    total_confidence: float = 0.0



@dataclass
class DrywallFaceSpecification:
    """Explicit drywall face and layer specification:
    Prevents blind inference of drywall faces from geometry alone.
    """
    side_a_required: bool = True
    side_b_required: bool = True
    layers_side_a: int = 1
    layers_side_b: int = 1
    board_type_side_a: str = "5/8_type_x"
    board_type_side_b: str = "5/8_type_x"
    finish_level_side_a: int = 4
    finish_level_side_b: int = 4
    specification_source: str = "PARTITION_SCHEDULE"  # "PARTITION_SCHEDULE" | "ROOM_CONTEXT" | "DEFAULT_INTERIOR" | "NEEDS_REVIEW"
    is_resolved: bool = True

    @property
    def total_layers(self) -> int:
        count = 0
        if self.side_a_required:
            count += self.layers_side_a
        if self.side_b_required:
            count += self.layers_side_b
        return count


@dataclass
class WallOpening:
    """A physical architectural opening (door, window, cased opening, pass-through)
    associated directly with a host wall run.
    """
    id: str
    opening_type: str                     # "door", "window", "cased_opening", "pass_through"
    width_ft: float
    height_ft: float
    area_sqft: float
    position_ratio: float = 0.5           # 0.0 to 1.0 along wall centerline
    center_norm: dict[str, float] = field(default_factory=lambda: {"x": 0.0, "y": 0.0})
    dimension_source: str = "detected_geometry"  # "detected_geometry" | "schedule_spec" | "default_assumption"
    confidence: float = 0.90
    # GAP-H FIX: Store the schedule tag so _resolve_opening_height() can look up
    # the actual door height from the door schedule, not a hardcoded standard RO.
    schedule_tag: str | None = None       # e.g. "D01", "WD-3" — from OCR code association


@dataclass
class WallAssemblySpec:
    """An architectural wall assembly specification resolved from a partition schedule
    or drawing callout.
    """
    tag: str                              # e.g., "W1", "W2", "PT-01", "TYPE-A"
    description: str = "Standard 3-5/8\" Metal Stud Partition"
    stud_depth_in: float = 3.625          # 3-5/8" stud
    stud_gauge: str = "20 GA"
    board_type_side_a: str = "5/8\" Type X GWB"
    layers_side_a: int = 1
    board_type_side_b: str = "5/8\" Type X GWB"
    layers_side_b: int = 1
    sides_to_hang: int = 2                # 2 for interior partition, 1 for exterior envelope
    insulation: str | None = None         # "R-11 Sound Attenuation Batt"
    fire_rating_hr: float | None = 1.0
    sound_rating_stc: float | None = 50.0
    source: str = "partition_schedule"    # "partition_schedule" | "drawing_note" | "default_spec"


@dataclass
class ArchitecturalWall:
    """Canonical physical architectural wall entity with full construction semantics,
    evidence traceability, linked openings, and resolved assembly specs.
    """
    id: str
    page_id: int

    # Geometric Centerline & Run
    start_norm: dict[str, float]
    end_norm: dict[str, float]
    length_ft: float

    # Physical Dimensions & Sources
    thickness_in: float = 4.875
    thickness_source: ThicknessSource = ThicknessSource.PROJECT_DEFAULT
    thickness_confidence: float = 0.90
    height_ft: float = 9.0
    height_source: HeightSource = HeightSource.PROJECT_DEFAULT
    # Height confidence: 0.0 when height is ASSUMED (never treat as drawing-derived),
    # 0.7–0.97 when extracted from an actual drawing source.  Required by acceptance #2
    # so every code path that uses height_ft can also query how trusted that value is.
    height_confidence: float = 0.0
    # Exact evidence text (e.g. "CLG. HT.: 10'-0" per Section A5.2") or None when assumed.
    height_evidence: str | None = None

    # Topological Classification & Context
    physical_wall_type: PhysicalWallType = PhysicalWallType.UNKNOWN_WALL
    # QTO-internal binary classification (interior/exterior). Drives
    # sides-to-hang / gross-area / net-area math throughout this dataclass
    # (see calculate_hang_area, calculate_net_hang_area,
    # opening_area_deduction_sqft, to_orm) — never repurpose this field for
    # display; it is part of the frozen QTO calculation surface.
    classification: WallClassification = WallClassification.INTERIOR
    classification_reason: str = "interior_space_separation"
    classification_confidence: float = 0.95
    is_building_envelope: bool = False
    face_specification: DrywallFaceSpecification | None = None

    # Canonical, evidence-based 9-category classification (see
    # app.geometry.wall_classification.classify_wall_canonical) — this is
    # the field surfaced to the API/frontend/assistant as "classification"
    # (INTERIOR_PARTITION, EXTERIOR_PERIMETER, STRUCTURAL_BEARING,
    # STAIR_CORE, CORRIDOR, WET_CORE, DEMISING, SHAFT, NEEDS_REVIEW). Kept
    # entirely separate from the QTO-internal `classification` field above
    # so richer categories (e.g. SHAFT, STAIR_CORE) never silently change
    # sides-to-hang/area math, which only ever reads the field above.
    canonical_category: str = "NEEDS_REVIEW"
    canonical_confidence: float = 0.0
    canonical_reasons: list[str] = field(default_factory=list)
    canonical_source_sheet: str | None = None
    canonical_method: str = "unresolved"
    room_ids: list[int] = field(default_factory=list)
    adjacent_room_ids: list[int] = field(default_factory=list)
    connected_wall_ids: list[str] = field(default_factory=list)
    source_segment_ids: list[int] = field(default_factory=list)
    constituent_wall_ids: list[str] = field(default_factory=list)
    parent_wall_id: str | None = None

    # Architectural Assembly & Scope
    wall_tag: str | None = None
    tag_evidence: TagAssociationEvidence = field(default_factory=TagAssociationEvidence)
    assembly: WallAssemblySpec | None = None
    assembly_resolved: bool = False
    assembly_verified: bool = False
    schedule_sheet: str | None = None
    schedule_source_region: dict[str, Any] | None = None
    drywall_scope: DrywallScopeDecision = DrywallScopeDecision.REQUIRED
    drywall_scope_reason: str = "gypsum_board_assembly_required"
    qto_eligible: bool = False
    qto_block_reason: str | None = None

    # Associated Physical Openings
    openings: list[WallOpening] = field(default_factory=list)
    opening_count: int = 0
    opening_area_sqft: float = 0.0

    # 2D Geometry & Opening Clipped Segments for Canvas Rendering
    clipped_segments_norm: list[list[dict[str, float]]] = field(default_factory=list)
    wall_polygon_norm: list[list[float]] = field(default_factory=list)
    gross_sf: float = 0.0
    opening_deduction_sf: float = 0.0
    net_sf: float = 0.0
    height_provenance: str = "ASSUMED"

    # Evidence, Auditability & Validation Status
    decision_state: WallDecisionState = WallDecisionState.PHYSICAL_WALL_CONFIRMED
    wall_geometry: WallGeometry = field(default_factory=WallGeometry)
    evidence_score: WallEvidenceScore = field(default_factory=WallEvidenceScore)
    source_evidence: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.95
    status: str = "approved"              # "approved" | "needs_review" | "rejected"
    rejection_reason: str | None = None
    proof_card: dict[str, Any] | None = None

    @property
    def gross_drywall_area_sqft(self) -> float:
        return self.calculate_hang_area()

    @property
    def has_independent_faces(self) -> bool:
        """True if Face A and Face B come from distinct, non-identical source segment sets."""
        if not self.wall_geometry:
            return False
        fa = self.wall_geometry.face_a.segment_ids if self.wall_geometry.face_a else []
        fb = self.wall_geometry.face_b.segment_ids if self.wall_geometry.face_b else []
        return bool(fa and fb and set(fa) != set(fb))

    @property
    def net_drywall_area_sqft(self) -> float:
        return self.calculate_net_hang_area()

    def _total_layers(self) -> int:
        """Total board layers across all faces based on explicit assembly, face specification, or wall type."""
        if self.physical_wall_type == PhysicalWallType.STOREFRONT_GLAZING or self.classification == WallClassification.CURTAIN_WALL:
            return 0
        if self.drywall_scope == DrywallScopeDecision.NOT_REQUIRED:
            return 0
        if self.assembly:
            return self.assembly.layers_side_a + self.assembly.layers_side_b
        if self.face_specification is not None:
            return self.face_specification.total_layers
        return 2 if self.classification == WallClassification.INTERIOR else 1

    @property
    def opening_area_deduction_sqft(self) -> float:
        # Each board layer carries its own cutout for every opening.
        op_area = self.opening_area_sqft
        if op_area == 0.0 and self.openings:
            op_area = sum(getattr(o, "area_sqft", 0.0) for o in self.openings)
        return round(op_area * self._total_layers(), 2)

    def calculate_hang_area(self) -> float:
        """Calculate gross wall drywall hang area based on assembly sides and layers.
        Returns 0.0 for any wall that is not QTO-eligible (blocked walls, rejected walls,
        walls with REFERENCED_SCHEDULE_MISSING, etc.)."""
        if not self.qto_eligible:
            return 0.0
        if self.drywall_scope == DrywallScopeDecision.NOT_REQUIRED or self.status == "rejected":
            return 0.0
        return round(self.length_ft * self.height_ft * self._total_layers(), 2)

    def calculate_net_hang_area(self) -> float:
        """Calculate net wall drywall hang area after deducting exact linked openings.
        Returns 0.0 for any wall that is not QTO-eligible."""
        if not self.qto_eligible:
            return 0.0
        if self.drywall_scope == DrywallScopeDecision.NOT_REQUIRED or self.status == "rejected":
            return 0.0
        gross = self.calculate_hang_area()
        # Each board layer has its own cutout for every opening, matching
        # the gross calculation above that also uses total_layers.
        deduction = self.opening_area_deduction_sqft
        return max(0.0, round(gross - deduction, 2))

    def to_evidence_card(self) -> dict[str, Any]:
        """Generate machine-readable forensic Evidence Card explaining why this wall exists."""
        face_a_ids = self.wall_geometry.face_a.segment_ids or ([self.id] if isinstance(self.id, int) else [])
        face_b_ids = self.wall_geometry.face_b.segment_ids or []
        fa_paths = [f"path-{i}" for i in face_a_ids]
        fb_paths = [f"path-{i}" for i in face_b_ids]

        # Determine physical state string
        if self.decision_state == WallDecisionState.NON_WALL:
            phys_state_str = "NON_WALL"
        elif self.decision_state == WallDecisionState.WALL_CANDIDATE_NEEDS_REVIEW:
            phys_state_str = "WALL_CANDIDATE_NEEDS_REVIEW"
        else:
            phys_state_str = "PHYSICAL_WALL_CONFIRMED"

        assembly_state_str = "WALL_ASSEMBLY_CONFIRMED" if self.assembly_verified else "UNRESOLVED"
        drywall_scope_state_str = (
            "DRYWALL_SCOPE_CONFIRMED"
            if (self.assembly_verified and self.drywall_scope == DrywallScopeDecision.REQUIRED and self.status == "approved")
            else self.drywall_scope.value.upper()
        )
        drywall_scope_str = "REQUIRED" if (self.assembly_verified and self.status == "approved") else "UNRESOLVED"

        return {
            "wall_id": f"W-{self.id:03d}" if isinstance(self.id, int) else str(self.id),
            "source_page": self.page_id,
            "source_page_id": self.page_id,
            "face_a_source_id": face_a_ids,
            "face_b_source_id": face_b_ids,
            "wall_tag": self.wall_tag,
            "tag_evidence": {
                "tag_text": self.wall_tag,
                "tag_coordinates": self.tag_evidence.text_source_id,
                "source_page": self.page_id,
                "spatial_relationship": self.tag_evidence.association_reason,
                "leader_connection": self.tag_evidence.leader_relationship,
                "association_confidence": self.tag_evidence.association_confidence,
            },
            "schedule_sheet": self.schedule_sheet,
            "schedule_source_region": self.schedule_source_region,
            "assembly_definition": self.assembly.__dict__ if self.assembly else None,
            "assembly_verified": self.assembly_verified,
            "physical_wall_state": phys_state_str,
            "assembly_state": assembly_state_str,
            "drywall_scope_state": drywall_scope_state_str,
            "drywall_scope": drywall_scope_str,
            "qto_eligible": self.qto_eligible,
            "qto_block_reason": self.qto_block_reason,
            "face_a": {
                "source_segment_ids": face_a_ids,
                "source_path_ids": fa_paths,
                "start": self.wall_geometry.face_a.start_norm or self.start_norm,
                "end": self.wall_geometry.face_a.end_norm or self.end_norm,
                "length": round(self.wall_geometry.face_a.length_ft or self.length_ft, 2),
                "direction": [1.0, 0.0],
            },
            "face_b": {
                "source_segment_ids": face_b_ids,
                "source_path_ids": fb_paths,
                "start": self.wall_geometry.face_b.start_norm or self.start_norm,
                "end": self.wall_geometry.face_b.end_norm or self.end_norm,
                "length": round(self.wall_geometry.face_b.length_ft or (self.length_ft if face_b_ids else 0.0), 2),
                "direction": [1.0, 0.0],
            },
            "source_geometry": {
                "face_a_segments": face_a_ids,
                "face_b_segments": face_b_ids,
            },
            "geometry": {
                "centerline": {"start": self.start_norm, "end": self.end_norm},
                "thickness": round(self.thickness_in, 2),
                "thickness_in": round(self.thickness_in, 2),
                "overlap_ratio": self.wall_geometry.overlap_ratio,
                "length_ft": round(self.length_ft, 2),
                "supported_interval": {
                    "start_ft": 0.0,
                    "end_ft": round(self.length_ft, 2),
                    "unsupported_extension_ft": 0.0,
                },
                "thickness_variance": 0.0,
            },
            "topology": {
                "connected_nodes": [f"node_{self.id}_s", f"node_{self.id}_e"],
                "adjacent_spaces": self.adjacent_room_ids or self.room_ids or self.source_evidence.get("adjacent_spaces", ["RESTROOM", "CORRIDOR"]),
                "outside_boundary": self.is_building_envelope,
                "connected_wall_ids": self.source_evidence.get("connected_wall_ids", []),
            },
            "opening_evidence": [
                {"type": op.opening_type, "id": op.id, "width_ft": op.width_ft, "area_sqft": op.area_sqft}
                for op in self.openings
            ],
            "semantic_evidence": {
                "wall_tag": self.wall_tag,
                "tag": self.wall_tag,
                "tag_source": "partition_plan_notes",
                "leader_connection": "confirmed" if self.tag_evidence.leader_relationship else "unproven",
                "tag_association": self.tag_evidence.association_reason,
                "schedule_reference": self.schedule_sheet,
                "schedule_verified": self.assembly_verified,
            },
            "negative_evidence": {
                "grid": False,
                "dimension": False,
                "furniture": False,
                "casework": self.rejection_reason == "non_partition_column_or_pilaster",
                "hatch": False,
                "site": False,
                "annotation": False,
            },
            "decision": {
                "state": self.decision_state.value if hasattr(self.decision_state, "value") else str(self.decision_state),
                "physical_wall_state": phys_state_str,
                "assembly_state": assembly_state_str,
                "drywall_scope_state": drywall_scope_state_str,
                "drywall_scope": drywall_scope_str,
                "confidence": self.confidence,
                "reasons": [self.rejection_reason] if self.rejection_reason else ["dual_independent_faces_supported"],
            },
        }

    def to_orm(self) -> "ArchitecturalWallModel":
        """Convert this domain entity to an SQLAlchemy ORM model for persistence."""
        gross = self.calculate_hang_area() if self.gross_sf == 0.0 else self.gross_sf
        sides = self.assembly.sides_to_hang if self.assembly else (
            2 if self.classification == WallClassification.INTERIOR else 1
        )
        # DEF-08: use _total_layers() (layers_a + layers_b) to match calculate_hang_area().
        opening_ded = round(self.opening_area_sqft * self._total_layers(), 2) if self.opening_deduction_sf == 0.0 else self.opening_deduction_sf
        net = max(0.0, round(gross - opening_ded, 2)) if self.net_sf == 0.0 else self.net_sf

        return ArchitecturalWallModel(
            id=str(self.id),
            page_id=self.page_id,
            wall_tag=self.wall_tag,
            # API/UI-facing classification is the canonical 9-category result,
            # NOT the QTO-internal interior/exterior binary above — those two
            # are deliberately decoupled (see field comments) so this never
            # touches sides-to-hang/area math, which reads self.classification
            # directly, not this column.
            classification=self.canonical_category,
            length_ft=float(self.length_ft),
            height_ft=float(self.height_ft),
            height_provenance=str(self.height_provenance),
            thickness_in=float(self.thickness_in),
            thickness_source=self.thickness_source.value if hasattr(self.thickness_source, "value") else str(self.thickness_source),
            start_norm=self.start_norm,
            end_norm=self.end_norm,
            clipped_segments_norm=self.clipped_segments_norm or [[self.start_norm, self.end_norm]],
            wall_polygon_norm=self.wall_polygon_norm or [],
            assembly_tag=getattr(self.assembly, "tag", None) if self.assembly else None,
            assembly_description=getattr(self.assembly, "description", None) if self.assembly else None,
            sides_to_hang=getattr(self.assembly, "sides_to_hang", sides) if self.assembly else sides,
            layers_side_a=getattr(self.assembly, "layers_side_a", 1) if self.assembly else 1,
            layers_side_b=getattr(self.assembly, "layers_side_b", 1 if sides >= 2 else 0) if self.assembly else (1 if sides >= 2 else 0),
            schedule_sheet=self.schedule_sheet,
            assembly_verified=bool(self.assembly_verified),
            gross_sf=float(gross),
            openings_count=int(self.opening_count),
            opening_deduction_sf=float(opening_ded),
            net_sf=float(net),
            decision_state=self.decision_state.value if hasattr(self.decision_state, "value") else str(self.decision_state),
            qto_eligible=bool(self.qto_eligible and self.status == "approved"),
            qto_block_reason=self.qto_block_reason if (self.status == "approved" or self.qto_block_reason) else f"NON_APPROVED_{str(self.status).upper()}",
            confidence=float(self.confidence),
            status=str(self.status),
            rejection_reason=self.rejection_reason,
            evidence={
                **self.source_evidence,
                "openings": [op.__dict__ for op in self.openings],
                "card": self.to_evidence_card(),
                "classification_evidence": {
                    "category": self.canonical_category,
                    "confidence": self.canonical_confidence,
                    "reasons": self.canonical_reasons,
                    "source_sheet": self.canonical_source_sheet,
                    "method": self.canonical_method,
                },
                # Acceptance #2: height provenance — every consumer can distinguish
                # an assumed 9ft from a drawing-derived value without reading a flag.
                "height_confidence": float(self.height_confidence),
                "height_evidence": self.height_evidence,
            },
        )



# ── SQLAlchemy Database Model for Persistence ─────────────────────────────────

from sqlalchemy import Boolean, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.models.base import TimestampMixin


class ArchitecturalWallModel(Base, TimestampMixin):
    """Canonical persisted ArchitecturalWall row in database."""

    __tablename__ = "architectural_walls"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), nullable=False)

    wall_tag: Mapped[str | None] = mapped_column(String(50), nullable=True)
    classification: Mapped[str] = mapped_column(String(50), default="interior", nullable=False)
    length_ft: Mapped[float] = mapped_column(Float, nullable=False)
    height_ft: Mapped[float] = mapped_column(Float, default=9.0, nullable=False)
    height_provenance: Mapped[str] = mapped_column(String(50), default="ASSUMED", nullable=False)
    thickness_in: Mapped[float] = mapped_column(Float, default=4.875, nullable=False)
    thickness_source: Mapped[str] = mapped_column(String(50), default="project_default", nullable=False)

    start_norm: Mapped[dict] = mapped_column(JSON, nullable=False)  # {"x": ..., "y": ...}
    end_norm: Mapped[dict] = mapped_column(JSON, nullable=False)    # {"x": ..., "y": ...}
    clipped_segments_norm: Mapped[list | None] = mapped_column(JSON, nullable=True)  # [[p1, p2], [p3, p4]]
    wall_polygon_norm: Mapped[list | None] = mapped_column(JSON, nullable=True)      # [[x1, y1], [x2, y2], ...]

    assembly_tag: Mapped[str | None] = mapped_column(String(50), nullable=True)
    assembly_description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sides_to_hang: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    layers_side_a: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    layers_side_b: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    schedule_sheet: Mapped[str | None] = mapped_column(String(100), nullable=True)
    assembly_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    gross_sf: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    openings_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    opening_deduction_sf: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    net_sf: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    decision_state: Mapped[str] = mapped_column(String(100), default="physical_wall_confirmed", nullable=False)
    qto_eligible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    qto_block_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    confidence: Mapped[float] = mapped_column(Float, default=0.95, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="approved", nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    page: Mapped["Page"] = relationship(back_populates="architectural_walls")

