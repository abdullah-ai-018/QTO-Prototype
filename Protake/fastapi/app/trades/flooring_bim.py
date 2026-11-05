"""BIM Flooring Takeoff Engine: Deterministic, IFC-auditable quantity takeoff
strictly conforming to the FLOORING_SURFACE scope contract.
Zero premature estimating packages, boxes, baseboard LF, transitions, or labor hours.
"""
from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field

from app.bim.models import (
    CanonicalBIMModel,
    CanonicalFlooringElement,
    DataProvenanceStatus,
    FlooringCategory,
    FlooringEligibilityStatus,
)


class BIMFlooringLineItem(BaseModel):
    item_id: str
    ifc_guid: str
    trade: str = "FLOORING"
    category: str = "FLOORING_SURFACE"
    source_name: str
    storey_id: str = ""
    storey_name: str = "Level 01"
    flooring_category: str
    finish_material_name: str
    thickness_in: Optional[float] = None
    net_area_sqft: float
    unit: str = "SQFT"
    provenance_status: str
    qto_eligibility: str
    eligibility_reasons: list[str] = Field(default_factory=list)
    superseded_by_guid: Optional[str] = None


class BIMFlooringSummary(BaseModel):
    engine_version: str = "2.0.0-flooring-surface"
    model_sha256: Optional[str] = None
    snapshot_created_at: Optional[str] = None
    total_floor_area_sqft: float = 0.0
    total_elements_count: int = 0
    material_types_count: int = 0
    review_count: int = 0
    blocked_count: int = 0
    total_elements_evaluated: int = 0
    line_items: list[BIMFlooringLineItem] = Field(default_factory=list)


class BIMFlooringEngine:
    """Calculates engineering-grade flooring quantity takeoffs from Canonical BIM models
    strictly scoped to net FLOORING_SURFACE area with full IFC GUID provenance.
    """

    def __init__(self, default_waste_factor: float = 0.0, labor_rate_per_hour: float = 0.0):
        # Waste factors and labor rates are not part of the strict Step 2 FLOORING_SURFACE contract
        self.default_waste_factor = 0.0
        self.labor_rate_per_hour = 0.0

    def calculate(self, model: CanonicalBIMModel) -> BIMFlooringSummary:
        """Executes full canonical flooring QTO calculation strictly for FLOORING_SURFACE."""
        elements = model.flooring_elements
        if not elements and (model.slabs or model.spaces):
            # Fallback: normalize on demand if not pre-populated
            from app.bim.flooring_normalizer import FlooringNormalizer
            raw_dict = {
                "coverings": [],
                "slabs": [s.model_dump() for s in model.slabs],
                "spaces": [s.model_dump() for s in model.spaces],
                "storeys": [s.model_dump() for s in model.storeys],
            }
            elements = FlooringNormalizer().normalize(raw_dict)

        line_items: list[BIMFlooringLineItem] = []
        total_floor_area = 0.0
        categories_seen = set()
        review_count = 0
        blocked_count = 0
        eligible_count = 0

        for elem in elements:
            cat_val = elem.flooring_category.value if hasattr(elem.flooring_category, "value") else str(elem.flooring_category)
            prov_val = elem.provenance_status.value if hasattr(elem.provenance_status, "value") else str(elem.provenance_status)
            elig_val = elem.qto_eligibility.value if hasattr(elem.qto_eligibility, "value") else str(elem.qto_eligibility)

            if elig_val == "ELIGIBLE":
                eligible_count += 1
                total_floor_area += elem.net_area_sqft
                categories_seen.add(cat_val)
            elif elig_val == "REVIEW_REQUIRED":
                review_count += 1
            else:
                blocked_count += 1

            line_items.append(
                BIMFlooringLineItem(
                    item_id=f"FLR-{elem.ifc_guid}",
                    ifc_guid=elem.ifc_guid,
                    trade="FLOORING",
                    category="FLOORING_SURFACE",
                    source_name=elem.source_name,
                    storey_id=elem.storey_id,
                    storey_name=elem.storey_name,
                    flooring_category=cat_val,
                    finish_material_name=elem.finish_material_name or "Unassigned Finish",
                    thickness_in=elem.thickness_in,
                    net_area_sqft=round(elem.net_area_sqft, 2),
                    unit="SQFT",
                    provenance_status=prov_val,
                    qto_eligibility=elig_val,
                    eligibility_reasons=elem.eligibility_reasons,
                    superseded_by_guid=elem.superseded_by_guid,
                )
            )

        return BIMFlooringSummary(
            engine_version="2.0.0-flooring-surface",
            total_floor_area_sqft=round(total_floor_area, 2),
            total_elements_count=eligible_count,
            material_types_count=len(categories_seen),
            review_count=review_count,
            blocked_count=blocked_count,
            total_elements_evaluated=len(elements),
            line_items=line_items,
        )
