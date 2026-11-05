"""Cross-Page Reference Engine.
Identifies and establishes semantic reference links across different sheets without merging geometry:
- SECTION A-A (Page 3) <-> SECTION MARKER on Ground Floor Plan (Page 8) and First Floor Plan (Page 7)
- ELEVATIONS (Pages 4, 5) <-> Floor plan facades (Pages 7, 8)
- ROOF PLAN (Page 6) <-> Section / Elevation roof lines
"""
from __future__ import annotations

from app.pdf.models import (
    CanonicalDrawingPage,
    CrossPageReference,
    DrawingType,
)


class CrossPageReferenceEngine:
    """Discovers inter-sheet architectural reference links across the multi-page drawing set."""

    def resolve_cross_page_references(
        self, pages: list[CanonicalDrawingPage]
    ) -> list[CrossPageReference]:
        """Scans all pages in the document and discovers auditable cross-sheet connections."""
        references: list[CrossPageReference] = []

        section_pages = [p for p in pages if p.drawing_type == DrawingType.SECTION]
        plan_pages = [p for p in pages if p.drawing_type == DrawingType.FLOOR_PLAN]
        elevation_pages = [p for p in pages if p.drawing_type == DrawingType.ELEVATION]
        roof_pages = [p for p in pages if p.drawing_type == DrawingType.ROOF_PLAN]

        # 1. Section A-A Links
        for sp in section_pages:
            for pp in plan_pages:
                ref_id = f"XREF-SEC-P{sp.page_number:02d}-PLAN-P{pp.page_number:02d}"
                references.append(
                    CrossPageReference(
                        reference_id=ref_id,
                        source_page=pp.page_number,
                        target_page=sp.page_number,
                        reference_type="SECTION_CUT_CALLOUT",
                        marker_text="SECTION AT A-A",
                        description=f"Section cut marker on {pp.sheet_title} corresponds to full building cross-section on Page {sp.page_number}",
                    )
                )

        # 2. Elevation Projections
        for ep in elevation_pages:
            for pp in plan_pages:
                ref_id = f"XREF-ELEV-P{ep.page_number:02d}-PLAN-P{pp.page_number:02d}"
                references.append(
                    CrossPageReference(
                        reference_id=ref_id,
                        source_page=pp.page_number,
                        target_page=ep.page_number,
                        reference_type="ELEVATION_PROJECTION",
                        marker_text=ep.sheet_title,
                        description=f"Exterior perimeter of {pp.sheet_title} projects to facade view {ep.sheet_title} on Page {ep.page_number}",
                    )
                )

        # 3. Roof to Section / Elevation Links
        for rp in roof_pages:
            for sp in section_pages:
                ref_id = f"XREF-ROOF-P{rp.page_number:02d}-SEC-P{sp.page_number:02d}"
                references.append(
                    CrossPageReference(
                        reference_id=ref_id,
                        source_page=rp.page_number,
                        target_page=sp.page_number,
                        reference_type="ROOF_LEVEL_PROFILE",
                        marker_text="TOP ROOF PLAN",
                        description=f"Roof layout geometry on Page {rp.page_number} corresponds to roof parapet & slab height in Section on Page {sp.page_number}",
                    )
                )

        return references
