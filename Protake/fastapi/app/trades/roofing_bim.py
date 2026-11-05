"""BIM Roofing Takeoff Engine: Deterministic, IFC-auditable ROOFING_SURFACE quantity takeoff
conforming strictly to Canonical BIM geometry and provenance standards.
Zero legacy bundles, rolls, nails, labor, or synthetic roof heuristics.
"""
from __future__ import annotations

import math
from typing import Any, Optional
from pydantic import BaseModel, Field

from app.bim.models import (
    CanonicalBIMModel,
    CanonicalRoof,
    DataProvenanceStatus,
    QTOEligibilityStatus,
)


class RoofingProvenance(BaseModel):
    ifc_guid: str
    storey_name: str
    element_name: str
    source_type: str = "IfcRoof"
    roof_type: str = "UNKNOWN"
    pitch_ratio: Optional[str] = None
    slope_degrees: Optional[float] = None
    pitch_multiplier: Optional[float] = None
    plan_area_sqft: float
    true_surface_area_sqft: float
    primary_material: str = "UNASSIGNED"
    material_evidence: Optional[str] = None
    formula: str
    status: str = "CONFIRMED"
    geometry_provenance: DataProvenanceStatus = DataProvenanceStatus.DERIVED_GEOMETRIC
    material_provenance: DataProvenanceStatus = DataProvenanceStatus.UNKNOWN_UNRESOLVED
    slope_provenance: DataProvenanceStatus = DataProvenanceStatus.UNKNOWN_UNRESOLVED
    qto_eligibility: QTOEligibilityStatus = QTOEligibilityStatus.ELIGIBLE
    review_reasons: list[str] = Field(default_factory=list)


class BIMRoofingLineItem(BaseModel):
    item_id: str
    trade: str = "ROOFING"
    category: str = "ROOFING_SURFACE"
    item_code: str
    description: str
    unit: str = "SF"
    quantity: float
    unit_cost: float = 0.0
    total_cost: float = 0.0
    source_guid: str
    provenance: RoofingProvenance


class BIMRoofingSummary(BaseModel):
    engine_version: str = "2.0.0-roofing-canonical"
    model_sha256: Optional[str] = None
    snapshot_created_at: Optional[str] = None
    total_plan_area_sqft: float
    total_true_surface_area_sqft: float
    total_elements_evaluated: int
    eligible_elements_count: int
    review_elements_count: int
    blocked_elements_count: int
    verified_slope_count: int
    line_items: list[BIMRoofingLineItem] = Field(default_factory=list)


class BIMRoofingEngine:
    """Calculates engineering-grade ROOFING_SURFACE quantity takeoffs from Canonical BIM models
    conforming strictly to IFC geometry and auditable provenance.
    """

    def __init__(
        self,
        default_waste_factor: float = 0.0,
    ):
        # Waste factor is kept as an audit parameter only, not applied to primary canonical surface SF
        self.default_waste_factor = default_waste_factor

    def calculate_roofing_qto(self, model: CanonicalBIMModel) -> BIMRoofingSummary:
        """Alias for calculate."""
        return self.calculate(model)

    def calculate(self, model: CanonicalBIMModel) -> BIMRoofingSummary:
        """Executes roof-by-roof canonical surface QTO calculation."""
        line_items: list[BIMRoofingLineItem] = []

        total_plan_area = 0.0
        total_true_area = 0.0
        elements_evaluated = 0
        eligible_count = 0
        review_count = 0
        blocked_count = 0
        verified_slope_count = 0

        # Strictly evaluate canonical roofs present in the model (zero synthetic fabrication)
        roofs_to_process: list[CanonicalRoof] = list(model.roofs)

        for rf in roofs_to_process:
            elements_evaluated += 1

            plan_sqft = rf.plan_area_sqft
            true_sqft = rf.true_surface_area_sqft if rf.true_surface_area_sqft > 0 else plan_sqft

            if rf.slope_degrees is not None:
                verified_slope_count += 1

            if rf.qto_eligibility == QTOEligibilityStatus.ELIGIBLE:
                eligible_count += 1
                total_plan_area += plan_sqft
                total_true_area += true_sqft
            elif rf.qto_eligibility == QTOEligibilityStatus.REVIEW_REQUIRED:
                review_count += 1
                total_plan_area += plan_sqft
                total_true_area += true_sqft
            else:
                blocked_count += 1

            # Formula documentation
            if rf.pitch_multiplier and rf.pitch_multiplier > 1.0:
                formula_str = f"{round(plan_sqft, 1)} Plan SF × {rf.pitch_multiplier} Pitch Mult = {round(true_sqft, 1)} True Surface SF"
            elif rf.slope_degrees == 0.0:
                formula_str = f"{round(plan_sqft, 1)} Plan SF (Flat Roof, Slope 0.0°) = {round(true_sqft, 1)} True Surface SF"
            else:
                formula_str = f"{round(true_sqft, 1)} True Surface SF (Derived from IFC geometry)"

            prov = RoofingProvenance(
                ifc_guid=rf.ifc_guid,
                storey_name=rf.storey_name,
                element_name=rf.name,
                source_type=rf.source_type,
                roof_type=rf.roof_type,
                pitch_ratio=rf.pitch_ratio,
                slope_degrees=rf.slope_degrees,
                pitch_multiplier=rf.pitch_multiplier,
                plan_area_sqft=round(plan_sqft, 2),
                true_surface_area_sqft=round(true_sqft, 2),
                primary_material=rf.primary_material,
                material_evidence=rf.material_evidence,
                formula=formula_str,
                status="REVIEW" if rf.qto_eligibility == QTOEligibilityStatus.REVIEW_REQUIRED else "CONFIRMED",
                geometry_provenance=rf.area_provenance,
                material_provenance=rf.material_provenance,
                slope_provenance=rf.slope_provenance,
                qto_eligibility=rf.qto_eligibility,
                review_reasons=rf.review_reasons,
            )

            # Single Canonical Line Item per Roof: ROOFING_SURFACE
            line_items.append(
                BIMRoofingLineItem(
                    item_id=f"ROOF-{rf.ifc_guid}-SURFACE",
                    trade="ROOFING",
                    category="ROOFING_SURFACE",
                    item_code="ROOF-QTO-SURFACE-SF",
                    description=f"{rf.name} ({rf.roof_type} Roof, {rf.pitch_ratio or 'Pitch N/A'}, {rf.primary_material})",
                    unit="SF",
                    quantity=round(true_sqft, 2),
                    unit_cost=0.0,
                    total_cost=0.0,
                    source_guid=rf.ifc_guid,
                    provenance=prov,
                )
            )

        return BIMRoofingSummary(
            total_plan_area_sqft=round(total_plan_area, 2),
            total_true_surface_area_sqft=round(total_true_area, 2),
            total_elements_evaluated=elements_evaluated,
            eligible_elements_count=eligible_count,
            review_elements_count=review_count,
            blocked_elements_count=blocked_count,
            verified_slope_count=verified_slope_count,
            line_items=line_items,
        )
