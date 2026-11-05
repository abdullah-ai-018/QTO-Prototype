"""Trade-Specific Takeoff Engine for Multi-Page Architectural Drawings.
Computes auditable, trade-gated quantities for:
- DRYWALL: Wall perimeter * ceiling height (10 ft) minus doors/openings = Net SF
- FLOORING: Enclosed room floor surfaces minus exterior areas = Net SF
- ROOFING: Validated closed roof planes * pitch multiplier = True SF
- OTHER: Plumbing, Elevations, Sections, Details, Foundations correctly marked NOT_APPLICABLE.
"""
from __future__ import annotations

from typing import Optional
from app.pdf.models import (
    DataProvenanceStatus,
    DrawingObjectType,
    DrawingType,
    PageTakeoffSummary,
    ScaleEvidence,
    ScaleStatus,
    SemanticDrawingObject,
    TradeTakeoffItem,
)


class MultiTradeTakeoffEngine:
    """Calculates trade-specific QTO quantities with strict verification gating."""

    def calculate_page_takeoff(
        self,
        page_number: int,
        sheet_title: str,
        drawing_type: DrawingType,
        semantic_objects: list[SemanticDrawingObject],
        roof_planes: list[dict],
        scale_evidence: ScaleEvidence,
    ) -> PageTakeoffSummary:
        """Evaluates takeoff eligibility and computes quantities for eligible trades on this sheet."""
        scale_ok = scale_evidence.scale_status == ScaleStatus.VERIFIED_EXPLICIT

        items: list[TradeTakeoffItem] = []
        drywall_sf = 0.0
        flooring_sf = 0.0
        roofing_sf = 0.0

        drywall_status = "NOT_APPLICABLE"
        flooring_status = "NOT_APPLICABLE"
        roofing_status = "NOT_APPLICABLE"
        gating_decision = "PASS"
        gating_notes: list[str] = []

        # -------------------------------------------------------------------------
        # 1. FLOOR PLAN TAKEOFF (DRYWALL & FLOORING) - Pages 7, 8
        # -------------------------------------------------------------------------
        if drawing_type == DrawingType.FLOOR_PLAN:
            if not scale_ok:
                drywall_status = "REVIEW_REQUIRED"
                flooring_status = "REVIEW_REQUIRED"
                gating_decision = "REVIEW_REQUIRED"
                gating_notes.append("Floor plan scale is uncorroborated. QTO quantities blocked.")
            else:
                drywall_status = "VERIFIED"
                flooring_status = "VERIFIED"

                # 1A. Flooring Takeoff from verified Room objects
                rooms = [
                    o for o in semantic_objects
                    if o.object_type == DrawingObjectType.ROOM and o.properties.get("is_enclosed_interior", True)
                ]

                for r in rooms:
                    room_sf = float(r.properties.get("plan_area_sqft", 0.0))
                    flooring_sf += room_sf
                    items.append(
                        TradeTakeoffItem(
                            item_id=f"QTO-FLR-P{page_number:02d}-{r.id}",
                            trade="FLOORING",
                            category="FINISH_FLOORING",
                            name=f"Tile / Hardwood Floor - {r.label}",
                            page_number=page_number,
                            quantity=round(room_sf, 2),
                            unit="SF",
                            status="VERIFIED",
                            provenance_notes=[
                                f"Enclosed interior space '{r.label}' with verified scale {scale_evidence.scale_string}"
                            ],
                            source_object_ids=[r.id],
                        )
                    )

                # 1B. Drywall Takeoff from verified Wall segments
                # Wall gross area = length * 10 ft ceiling height
                # Openings deducted per door swing (3 ft * 7 ft = 21 SF per door)
                walls = [o for o in semantic_objects if o.object_type == DrawingObjectType.WALL]
                doors = [o for o in semantic_objects if o.object_type == DrawingObjectType.DOOR]

                total_wall_lf = sum(float(w.properties.get("wall_length_ft", 0.0)) for w in walls)
                ceiling_height_ft = 10.0
                gross_drywall_sf = total_wall_lf * ceiling_height_ft * 2.0  # two sides of interior wall
                openings_deduction_sf = len(doors) * 21.0 * 2.0

                drywall_sf = max(0.0, gross_drywall_sf - openings_deduction_sf)

                items.append(
                    TradeTakeoffItem(
                        item_id=f"QTO-DRY-P{page_number:02d}-WALLS",
                        trade="DRYWALL",
                        category="GYPSUM_BOARD",
                        name="1/2\" Regular Drywall Partition Assembly",
                        page_number=page_number,
                        quantity=round(drywall_sf, 2),
                        unit="SF",
                        status="VERIFIED",
                        provenance_notes=[
                            f"Total linear wall length {total_wall_lf:.1f} LF with 10'-0\" ceiling height, less {openings_deduction_sf:.1f} SF openings"
                        ],
                        source_object_ids=[w.id for w in walls[:20]],
                    )
                )

        # -------------------------------------------------------------------------
        # 2. ROOF PLAN TAKEOFF (ROOFING) - Page 6 / A2.1
        # -------------------------------------------------------------------------
        elif drawing_type == DrawingType.ROOF_PLAN:
            if not scale_ok or len(roof_planes) == 0:
                roofing_status = "REVIEW_REQUIRED"
                gating_decision = "REVIEW_REQUIRED"
                gating_notes.append("No verified closed roof boundary polygons found on sheet. Zero geometry fabricated.")
            else:
                roofing_status = "VERIFIED"
                for rp in roof_planes:
                    true_area = float(rp.get("true_surface_area_sqft", 0.0))
                    roofing_sf += true_area
                    items.append(
                        TradeTakeoffItem(
                            item_id=f"QTO-ROOF-P{page_number:02d}-{rp.get('plane_id')}",
                            trade="ROOFING",
                            category="ROOFING_SURFACE",
                            name=rp.get("name", "Roof Plane"),
                            page_number=page_number,
                            quantity=round(true_area, 2),
                            unit="SF",
                            status="VERIFIED",
                            provenance_notes=[
                                f"Pitch {rp.get('pitch_ratio')}, multiplier {rp.get('pitch_multiplier')}, scale {scale_evidence.scale_string}"
                            ],
                            source_object_ids=rp.get("source_vector_ids", []),
                        )
                    )

        # -------------------------------------------------------------------------
        # 3. NON-TAKEOFF SHEETS (Elevations, Sections, Foundation, Plumbing, Details)
        # -------------------------------------------------------------------------
        else:
            gating_decision = "PASS"
            gating_notes.append(
                f"Sheet classified as {drawing_type.value}. Excluded from Roofing/Drywall QTO to prevent false takeoffs."
            )

        return PageTakeoffSummary(
            page_number=page_number,
            sheet_title=sheet_title,
            drawing_type=drawing_type,
            drywall_sf=round(drywall_sf, 2),
            flooring_sf=round(flooring_sf, 2),
            roofing_sf=round(roofing_sf, 2),
            drywall_status=drywall_status,
            flooring_status=flooring_status,
            roofing_status=roofing_status,
            items=items,
            gating_decision=gating_decision,
            gating_notes=gating_notes,
        )
