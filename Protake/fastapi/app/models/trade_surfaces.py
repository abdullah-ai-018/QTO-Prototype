"""Multi-Trade Surface & Takeoff Interval Models.

Defines explicit trade-specific surface interpretations attached to canonical physical walls:
    PHYSICAL WALL
          ↓
      WALL FACES (Face A, Face B)
          ↓
    TRADE-SPECIFIC SURFACES (Drywall, Framing, Painting)
          ↓
    TAKEOFF INTERVALS & QUANTITIES
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TradeSurfaceType(str, Enum):
    DRYWALL = "drywall"
    FRAMING = "framing"
    PAINTING = "painting"
    INSULATION = "insulation"
    BASEBOARD = "baseboard"


@dataclass
class TradeSurfaceFace:
    """Individual face of a physical wall (Face A or Face B) with explicit trade scope."""
    face_id: str                          # "face_a" or "face_b"
    is_active: bool = True
    adjacent_room_id: int | None = None
    adjacent_room_name: str | None = None
    length_ft: float = 0.0
    height_ft: float = 9.0
    layers: int = 1
    board_type: str = "5/8\" Type X Gypsum Board"
    finish_level: int = 4
    gross_area_sqft: float = 0.0
    opening_deduction_sqft: float = 0.0
    net_area_sqft: float = 0.0
    source_segment_ids: list[int] = field(default_factory=list)


@dataclass
class DrywallTradeSurface:
    """Drywall-specific surface and layer specification."""
    total_layers: int = 2
    face_a: TradeSurfaceFace | None = None
    face_b: TradeSurfaceFace | None = None
    fire_rating_hr: float | None = 1.0
    sound_rating_stc: float | None = 50.0
    gross_sf: float = 0.0
    deduction_sf: float = 0.0
    net_sf: float = 0.0
    qto_eligible: bool = True
    scope_reason: str = "interior_gypsum_board_partition"


@dataclass
class FramingTradeSurface:
    """Framing-specific structural and stud specification."""
    stud_depth_in: float = 3.625
    stud_gauge: str = "20 GA"
    stud_spacing_in: float = 16.0
    linear_ft: float = 0.0
    height_ft: float = 9.0
    top_track_ft: float = 0.0
    bottom_track_ft: float = 0.0
    stud_count_estimated: int = 0


@dataclass
class PaintingTradeSurface:
    """Painting and coating surface specification."""
    coats: int = 2
    primer_required: bool = True
    finish_level: int = 4
    gross_paint_sf: float = 0.0
    net_paint_sf: float = 0.0


@dataclass
class CanonicalTradeTakeoffEntity:
    """Unified multi-trade takeoff entity for a single physical architectural wall."""
    physical_wall_id: str
    page_id: int
    source_segment_ids: list[int] = field(default_factory=list)
    constituent_wall_ids: list[str] = field(default_factory=list)
    parent_wall_id: str | None = None
    
    # Core geometry
    centerline_length_ft: float = 0.0
    height_ft: float = 9.0
    thickness_in: float = 4.875
    wall_tag: str | None = None
    
    # Trade-specific surface interpretations
    drywall: DrywallTradeSurface = field(default_factory=DrywallTradeSurface)
    framing: FramingTradeSurface = field(default_factory=FramingTradeSurface)
    painting: PaintingTradeSurface = field(default_factory=PaintingTradeSurface)
    
    # Audit & provenance
    evidence_proof: dict[str, Any] = field(default_factory=dict)
