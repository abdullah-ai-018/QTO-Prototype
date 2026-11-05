"""Professional Roofing Models for Comprehensive Takeoff Analysis"""

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin
from app.models.enums import (
    DetectionSource, 
    ReviewStatus, 
    RoofType, 
    RoofMaterialType, 
    RoofComplexity,
    FlashingType
)


class RoofPlane(Base, TimestampMixin):
    """Individual roof plane/face with specific geometry and pitch"""
    
    __tablename__ = "roof_planes"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), nullable=False)
    roof_id: Mapped[int] = mapped_column(ForeignKey("roofs.id", ondelete="CASCADE"), nullable=False)
    
    # Plane identification
    plane_name: Mapped[str] = mapped_column(String(100), nullable=False)  # "Front", "Back", "Left", "Right"
    plane_number: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Geometry in normalized coordinates
    polygon_norm: Mapped[list] = mapped_column(JSON, nullable=False)  # Plane boundary
    centroid_norm: Mapped[dict] = mapped_column(JSON, nullable=False)  # {x, y}
    
    # Measurements
    length_ft: Mapped[float] = mapped_column(Float, nullable=False)
    width_ft: Mapped[float] = mapped_column(Float, nullable=False)
    flat_area_sqft: Mapped[float] = mapped_column(Float, nullable=False)
    sloped_area_sqft: Mapped[float] = mapped_column(Float, nullable=False)
    
    # Pitch information
    pitch_rise: Mapped[float] = mapped_column(Float, nullable=False)  # Rise in inches
    pitch_run: Mapped[float] = mapped_column(Float, default=12.0, nullable=False)  # Usually 12
    pitch_angle_degrees: Mapped[float] = mapped_column(Float, nullable=False)
    pitch_factor: Mapped[float] = mapped_column(Float, nullable=False)  # Multiplier for area
    
    # Detection metadata
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    source: Mapped[DetectionSource] = mapped_column(Enum(DetectionSource), default=DetectionSource.GEOMETRY, nullable=False)
    status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus), default=ReviewStatus.PENDING, nullable=False)
    
    # Relationships (one-directional only to avoid Page model coupling)
    roof: Mapped["Roof"] = relationship(back_populates="planes")
    edges: Mapped[list["RoofEdge"]] = relationship(back_populates="plane")


class Roof(Base, TimestampMixin):
    """Complete roof system with all planes and features"""
    
    __tablename__ = "roofs"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), nullable=False)
    
    # Roof classification
    roof_type: Mapped[RoofType] = mapped_column(Enum(RoofType), nullable=False)
    material_type: Mapped[RoofMaterialType] = mapped_column(Enum(RoofMaterialType), nullable=False)
    complexity: Mapped[RoofComplexity] = mapped_column(Enum(RoofComplexity), default=RoofComplexity.MEDIUM, nullable=False)
    
    # Overall measurements
    total_flat_area_sqft: Mapped[float] = mapped_column(Float, nullable=False)
    total_sloped_area_sqft: Mapped[float] = mapped_column(Float, nullable=False)
    total_squares: Mapped[float] = mapped_column(Float, nullable=False)  # Sloped area / 100
    
    # Perimeter measurements
    total_perimeter_ft: Mapped[float] = mapped_column(Float, nullable=False)
    eave_length_ft: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    rake_length_ft: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    ridge_length_ft: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    hip_length_ft: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    valley_length_ft: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    
    # Building characteristics
    stories: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    roof_height_ft: Mapped[float] = mapped_column(Float, default=10.0, nullable=False)
    overhang_ft: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    
    # Access and safety
    is_steep_roof: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # > 6/12 pitch
    requires_crane: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    requires_safety_harness: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Waste factor based on complexity
    waste_factor_pct: Mapped[float] = mapped_column(Float, default=8.0, nullable=False)
    
    # Detection metadata
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    source: Mapped[DetectionSource] = mapped_column(Enum(DetectionSource), default=DetectionSource.GEOMETRY, nullable=False)
    status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus), default=ReviewStatus.PENDING, nullable=False)
    
    # Relationships (page is foreign key only, no back_populates to avoid Page model coupling)
    planes: Mapped[list["RoofPlane"]] = relationship(back_populates="roof", cascade="all, delete-orphan")
    edges: Mapped[list["RoofEdge"]] = relationship(back_populates="roof")
    openings: Mapped[list["RoofOpening"]] = relationship(back_populates="roof", cascade="all, delete-orphan")
    penetrations: Mapped[list["RoofPenetration"]] = relationship(back_populates="roof", cascade="all, delete-orphan")
    flashing: Mapped[list["RoofFlashing"]] = relationship(back_populates="roof", cascade="all, delete-orphan")


class RoofEdge(Base, TimestampMixin):
    """Roof edges: ridge, hip, valley, eave, rake"""
    
    __tablename__ = "roof_edges"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), nullable=False)
    roof_id: Mapped[int] = mapped_column(ForeignKey("roofs.id", ondelete="CASCADE"), nullable=False)
    plane_id: Mapped[int | None] = mapped_column(ForeignKey("roof_planes.id", ondelete="SET NULL"), nullable=True)
    
    # Edge properties
    edge_type: Mapped[str] = mapped_column(String(50), nullable=False)  # ridge, hip, valley, eave, rake
    
    # Geometry
    start_norm: Mapped[dict] = mapped_column(JSON, nullable=False)  # {x, y}
    end_norm: Mapped[dict] = mapped_column(JSON, nullable=False)    # {x, y}
    length_ft: Mapped[float] = mapped_column(Float, nullable=False)
    
    # Material calculations
    linear_ft_required: Mapped[float] = mapped_column(Float, nullable=False)  # May include waste
    
    # Detection metadata
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    source: Mapped[DetectionSource] = mapped_column(Enum(DetectionSource), default=DetectionSource.GEOMETRY, nullable=False)
    status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus), default=ReviewStatus.PENDING, nullable=False)
    
    # Relationships (page and roof are foreign keys, one-directional only)
    roof: Mapped["Roof"] = relationship(back_populates="edges")
    plane: Mapped["RoofPlane | None"] = relationship(back_populates="edges")


class RoofOpening(Base, TimestampMixin):
    """Roof openings: skylights, chimneys, roof hatches"""
    
    __tablename__ = "roof_openings"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), nullable=False)
    roof_id: Mapped[int] = mapped_column(ForeignKey("roofs.id", ondelete="CASCADE"), nullable=False)
    
    # Opening type
    opening_type: Mapped[str] = mapped_column(String(50), nullable=False)  # skylight, chimney, hatch
    opening_name: Mapped[str] = mapped_column(String(100), nullable=True)
    
    # Geometry
    polygon_norm: Mapped[list] = mapped_column(JSON, nullable=False)
    centroid_norm: Mapped[dict] = mapped_column(JSON, nullable=False)  # {x, y}
    
    # Measurements  
    length_ft: Mapped[float] = mapped_column(Float, nullable=False)
    width_ft: Mapped[float] = mapped_column(Float, nullable=False)
    area_sqft: Mapped[float] = mapped_column(Float, nullable=False)
    perimeter_ft: Mapped[float] = mapped_column(Float, nullable=False)
    
    # Material impact
    requires_flashing: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    flashing_perimeter_ft: Mapped[float] = mapped_column(Float, nullable=False)
    
    # Detection metadata
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    source: Mapped[DetectionSource] = mapped_column(Enum(DetectionSource), default=DetectionSource.YOLO, nullable=False)
    status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus), default=ReviewStatus.PENDING, nullable=False)
    
    # Relationships (page and roof are foreign keys, one-directional only)
    roof: Mapped["Roof"] = relationship(back_populates="openings")


class RoofPenetration(Base, TimestampMixin):
    """Small roof penetrations: vents, pipes, exhausts"""
    
    __tablename__ = "roof_penetrations"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), nullable=False)
    roof_id: Mapped[int] = mapped_column(ForeignKey("roofs.id", ondelete="CASCADE"), nullable=False)
    
    # Penetration type
    penetration_type: Mapped[str] = mapped_column(String(50), nullable=False)  # plumbing_vent, hvac, exhaust_fan, solar_pipe
    
    # Location
    centroid_norm: Mapped[dict] = mapped_column(JSON, nullable=False)  # {x, y}
    
    # Size (typically small)
    diameter_inches: Mapped[float] = mapped_column(Float, default=4.0, nullable=False)
    
    # Material requirements
    requires_boot: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    requires_flashing: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Detection metadata
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    source: Mapped[DetectionSource] = mapped_column(Enum(DetectionSource), default=DetectionSource.YOLO, nullable=False)
    status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus), default=ReviewStatus.PENDING, nullable=False)
    
    # Relationships (page and roof are foreign keys, one-directional only)
    roof: Mapped["Roof"] = relationship(back_populates="penetrations")


class RoofFlashing(Base, TimestampMixin):
    """Roof flashing requirements calculated from geometry"""
    
    __tablename__ = "roof_flashing"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), nullable=False)
    roof_id: Mapped[int] = mapped_column(ForeignKey("roofs.id", ondelete="CASCADE"), nullable=False)
    
    # Flashing details
    flashing_type: Mapped[FlashingType] = mapped_column(Enum(FlashingType), nullable=False)
    location_description: Mapped[str] = mapped_column(String(200), nullable=True)
    
    # Measurements
    length_ft: Mapped[float] = mapped_column(Float, nullable=False)
    width_inches: Mapped[float] = mapped_column(Float, default=8.0, nullable=False)  # Standard width
    
    # Material calculations
    square_ft_required: Mapped[float] = mapped_column(Float, nullable=False)
    linear_ft_required: Mapped[float] = mapped_column(Float, nullable=False)
    
    # Special requirements
    requires_ice_shield: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    requires_sealant: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Detection metadata
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    source: Mapped[DetectionSource] = mapped_column(Enum(DetectionSource), default=DetectionSource.GEOMETRY, nullable=False)
    status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus), default=ReviewStatus.PENDING, nullable=False)
    
    # Relationships (page and roof are foreign keys, one-directional only)
    roof: Mapped["Roof"] = relationship(back_populates="flashing")