"""Drywall Standards & Buildability Validation Module.

Encapsulates engineering standards and buildability rules for drywall construction:
- GA-216: Specifications for the Application and Finishing of Gypsum Panel Products (limiting unsupported heights, stud spacing)
- ASTM C754: Standard Specification for Installation of Steel Framing Members (framing deflection, gauge requirements)
- ASTM C840: Standard Specification for Application and Finishing of Gypsum Board (layering and fire rating compliance)

Note on Architectural & Estimating Responsibility:
1. Standards do NOT detect or manufacture geometric walls.
   Geometry + Pixel Evidence + Topology detect and construct physical walls.
2. Standards validate whether the wall's assembly, framing, board configuration,
   and height are structurally buildable and code compliant.
3. Material consumption rates (fasteners/SF, mud gal/SF, tape LF/SF) are
   estimating reference baselines provided for informational guidance; actual
   bill-of-quantities calculation and pricing factors are governed dynamically
   by the project estimating configuration rules (PricingService / TradeConfig).
"""

from dataclasses import dataclass, field
import logging
from typing import Any

from app.models.architectural_wall import WallAssemblySpec, PhysicalWallType

logger = logging.getLogger(__name__)


@dataclass
class DrywallStandardValidationResult:
    """Result of validating a physical wall against GA-216 / ASTM standards."""
    is_buildable: bool
    is_compliant: bool
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    recommended_stud_gauge: str = "25 GA"
    estimating_default_fastener_rate: float = 1.5   # screws per SF (estimating baseline)
    estimating_default_mud_gal_per_sf: float = 0.053 # gallons per SF (estimating baseline)
    estimating_default_tape_lf_per_sf: float = 0.37  # LF tape per SF (estimating baseline)
    recommended_stud_spacing_in: float = 16.0 # 16" O.C. standard

    @property
    def recommended_fastener_rate(self) -> float:
        return self.estimating_default_fastener_rate

    @property
    def recommended_mud_gal_per_sf(self) -> float:
        return self.estimating_default_mud_gal_per_sf

    @property
    def recommended_tape_lf_per_sf(self) -> float:
        return self.estimating_default_tape_lf_per_sf



class DrywallStandardsEngine:
    """Evaluates buildability, structural framing limits, and assembly compliance."""


    # GA-216 Maximum Limiting Heights (ft) for standard non-load bearing steel studs at 16" O.C. (5 psf lateral load, L/240 deflection)
    LIMITING_HEIGHTS_16_OC: dict[tuple[str, str], float] = {
        # (stud_depth, gauge): max_height_ft
        ("1-5/8\"", "25 GA"): 8.5,
        ("2-1/2\"", "25 GA"): 12.0,
        ("3-5/8\"", "25 GA"): 15.5,
        ("3-5/8\"", "20 GA"): 18.0,
        ("4\"", "20 GA"): 20.0,
        ("6\"", "25 GA"): 21.0,
        ("6\"", "20 GA"): 26.0,
    }

    # Standard Nominal Thicknesses (inches)
    NOMINAL_BOARD_THICKNESS: dict[str, float] = {
        "1/4\"": 0.25,
        "3/8\"": 0.375,
        "1/2\"": 0.50,
        "5/8\"": 0.625,
        "3/4\"": 0.75,
    }

    NOMINAL_STUD_DEPTH: dict[str, float] = {
        "1-5/8\"": 1.625,
        "2-1/2\"": 2.50,
        "3-1/2\"": 3.50,
        "3-5/8\"": 3.625,
        "4\"": 4.0,
        "6\"": 6.0,
        "8\"": 8.0,
    }

    @classmethod
    def validate_assembly(
        cls,
        assembly: WallAssemblySpec | None,
        physical_thickness_in: float,
        height_ft: float,
        physical_wall_type: PhysicalWallType = PhysicalWallType.DRYWALL_PARTITION,
    ) -> DrywallStandardValidationResult:
        """Validates a proposed wall assembly against physical measurements and GA-216 / ASTM rules."""
        issues: list[str] = []
        warnings: list[str] = []

        if not assembly:
            return DrywallStandardValidationResult(
                is_buildable=True,
                is_compliant=False,
                warnings=["NO_ASSEMBLY_SPECIFIED"],
            )

        # 1. Parse framing dimensions
        stud_depth_str = getattr(assembly, "stud_depth", "3-5/8\"") or "3-5/8\""
        stud_gauge_str = getattr(assembly, "stud_gauge", "25 GA") or "25 GA"
        stud_spacing = float(getattr(assembly, "stud_spacing_in", 16.0) or 16.0)

        # 2. Check Height vs Limiting Height (ASTM C754 / GA-216)
        max_h = cls.LIMITING_HEIGHTS_16_OC.get((stud_depth_str, stud_gauge_str), 15.0)
        if stud_spacing > 16.0:
            max_h *= 0.85  # 24" O.C. reduces allowable limiting height by ~15%

        if height_ft > max_h + 0.5:
            warnings.append(
                f"HEIGHT_EXCEEDS_GA216_LIMIT: Height {height_ft:.1f}' exceeds maximum unsupported height {max_h:.1f}' "
                f"for {stud_depth_str} {stud_gauge_str} @ {stud_spacing}\" O.C. Requires heavier gauge (20 GA) or deflection bracing."
            )

        # 3. Calculate expected nominal thickness from assembly specs
        layers_a = getattr(assembly, "board_layers_side_a", 1) or 1
        layers_b = getattr(assembly, "board_layers_side_b", 1) or 1
        board_thick = getattr(assembly, "board_thickness_in", 0.625) or 0.625

        stud_depth_val = cls.NOMINAL_STUD_DEPTH.get(stud_depth_str, 3.625)
        expected_thickness = stud_depth_val + (layers_a + layers_b) * board_thick

        # 4. Compare expected assembly thickness with physically measured vector thickness
        thickness_diff = abs(physical_thickness_in - expected_thickness)
        if physical_thickness_in > 0 and thickness_diff > 2.0:
            warnings.append(
                f"THICKNESS_DISCREPANCY: Measured CAD thickness ({physical_thickness_in:.2f}\") differs from "
                f"assembly nominal thickness ({expected_thickness:.2f}\") by {thickness_diff:.2f}\"."
            )

        # 5. Fire Rating and Layering Check (GA-600 / ASTM E119)
        fire_rating = getattr(assembly, "fire_rating_hours", 0.0) or 0.0
        total_layers = layers_a + layers_b
        if fire_rating >= 2.0 and total_layers < 4:
            warnings.append("FIRE_RATING_LAYER_MISMATCH: 2-Hour fire rating typically requires 2 layers 5/8\" Type X each side (4 layers total).")
        elif fire_rating >= 1.0 and total_layers < 2:
            warnings.append("FIRE_RATING_LAYER_MISMATCH: 1-Hour fire rating requires at least 1 layer 5/8\" Type X each side.")

        # 6. Recommended fasteners & finish materials (ASTM C840)
        # 1-layer: 1.5 screws/SF; 2-layer: ~2.2 screws/SF
        fastener_rate = 1.5 if total_layers <= 2 else 2.2
        # Joint compound: ~0.053 gal/SF for single layer, ~0.075 gal/SF for multi-layer taped joints
        mud_rate = 0.053 if total_layers <= 2 else 0.075
        tape_rate = 0.37

        is_buildable = len(issues) == 0
        is_compliant = len(issues) == 0 and len(warnings) == 0

        return DrywallStandardValidationResult(
            is_buildable=is_buildable,
            is_compliant=is_compliant,
            issues=issues,
            warnings=warnings,
            recommended_stud_gauge="20 GA" if height_ft > 14.0 else "25 GA",
            estimating_default_fastener_rate=fastener_rate,
            estimating_default_mud_gal_per_sf=mud_rate,
            estimating_default_tape_lf_per_sf=tape_rate,
            recommended_stud_spacing_in=stud_spacing,
        )

