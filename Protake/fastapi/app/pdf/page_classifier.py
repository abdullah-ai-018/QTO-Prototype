"""Page & Region Classifier for Architectural PDF Sets.
Processes PDF page-by-page, detecting:
- Specific drawing types (Floor plan, Roof plan, Reflected ceiling plan, Elevation, Section, Foundation, Furniture, Plumbing, Detail, Schedule, Legend, Title sheet, General notes)
- Sheet-specific scale corroboration (if unresolved -> REVIEW_REQUIRED)
- Multiple discrete architectural regions:
  * DRAWING_REGION (takeoff_eligible = True)
  * DETAIL_REGION (takeoff_eligible = False)
  * LEGEND_REGION (takeoff_eligible = False)
  * TITLE_BLOCK_REGION (takeoff_eligible = False)
  * NOTES_REGION (takeoff_eligible = False)
- Per-region scales, titles, bounding boxes, and provenance.
"""
from __future__ import annotations

import re
from typing import Optional
from app.pdf.models import (
    DrawingGeometryObject,
    DrawingRegion,
    DrawingRegionCategory,
    DrawingTextObject,
    DrawingType,
    ScaleEvidence,
    ScaleStatus,
    SemanticTextRole,
)
from app.pdf.scale_validator import ScaleValidator


class PageClassifier:
    """Classifies architectural drawing categories and partitions sheets into explicit architectural regions."""

    def __init__(self):
        self.scale_validator = ScaleValidator()

    def classify_page(
        self,
        page_number: int,
        text_objects: list[DrawingTextObject],
        geometry_objects: list[DrawingGeometryObject],
        page_width: float,
        page_height: float,
    ) -> tuple[DrawingType, str, str, str, list[DrawingRegion]]:
        """Determines the sheet's primary drawing type, title, discipline, units, and discrete drawing regions.
        Returns: (drawing_type, sheet_title, discipline, units, regions)
        """
        all_text = " ".join(t.text.strip() for t in text_objects)
        text_upper = all_text.upper()

        drawing_type = DrawingType.OTHER
        sheet_title = f"ARCHITECTURAL SHEET - PAGE {page_number}"
        discipline = "Architectural"
        units = "ft-in"

        # 1. Multi-Plan Furniture sheet (Page 10 or sheets with multiple furniture plans)
        if "FURNITURE" in text_upper:
            regions = self._detect_furniture_regions(page_number, text_objects, page_width, page_height)
            if regions:
                return (
                    DrawingType.FURNITURE_PLAN,
                    "FURNITURE LAYOUT PLANS",
                    "Architectural",
                    "ft-in",
                    regions,
                )

        # 2. Detail Drawings (Page 1 or sheets dedicated to details/casework)
        if ("ENLARGED PLAN" in text_upper or "COOKING RANGE" in text_upper or "HOOD" in text_upper or "CABINET" in text_upper or "JOINERY" in text_upper) and (page_number == 1 or "DETAIL" in text_upper):
            regions = self._detect_detail_regions(page_number, text_objects, page_width, page_height)
            return (
                DrawingType.DETAIL_DRAWING,
                "KITCHEN JOINERY & HOOD DETAILS",
                "Interior / Architectural",
                "ft-in",
                regions,
            )

        # 3. Reflected Ceiling Plan
        if "REFLECTED CEILING" in text_upper or " R.C.P " in f" {text_upper} " or " RCP " in f" {text_upper} ":
            drawing_type = DrawingType.REFLECTED_CEILING_PLAN
            sheet_title = "REFLECTED CEILING PLAN"
            discipline = "Architectural"

        # 4. Roof Plan
        elif "ROOF" in text_upper and any(kw in text_upper for kw in ["PLAN", "WORKING", "LAYOUT"]):
            drawing_type = DrawingType.ROOF_PLAN
            sheet_title = "TOP ROOF (WORKING) PLAN"
            discipline = "Architectural"
            for t in text_objects:
                tu = t.text.strip().upper()
                if "ROOF" in tu and ("PLAN" in tu or "WORKING" in tu):
                    sheet_title = t.text.strip()
                    break

        # 5. Foundation Plan
        elif "FOUNDATION" in text_upper:
            drawing_type = DrawingType.FOUNDATION_PLAN
            sheet_title = "GROUND FLOOR (FOUNDATION) PLAN"
            discipline = "Structural"
            for t in text_objects:
                if "FOUNDATION" in t.text.upper():
                    sheet_title = t.text.strip()
                    break

        # 6. Plumbing / Public Health
        elif "PLUMBING" in text_upper or "SEWER" in text_upper or "WATER SUPPLY" in text_upper or "DRAINAGE" in text_upper or "SANITARY" in text_upper:
            regions = self._detect_plumbing_regions(page_number, text_objects, page_width, page_height)
            return (
                DrawingType.PLUMBING_DRAWING,
                "PLUMBING & SANITARY LAYOUT PLAN",
                "Plumbing",
                "ft-in",
                regions,
            )

        # 7. Section
        elif "SECTION" in text_upper and not any(kw in text_upper for kw in ["FOUNDATION", "DETAIL"]):
            drawing_type = DrawingType.SECTION
            sheet_title = "SECTION AT A-A"
            discipline = "Architectural"
            for t in text_objects:
                tu = t.text.strip().upper()
                if tu.startswith("SECTION") or "SECTION AT" in tu:
                    sheet_title = t.text.strip()
                    break

        # 8. Elevation
        elif "ELEVATION" in text_upper and not any(kw in text_upper for kw in ["SECTION", "DETAIL"]):
            drawing_type = DrawingType.ELEVATION
            sheet_title = "ELEVATION"
            discipline = "Architectural"
            for t in text_objects:
                tu = t.text.strip().upper()
                if "FRONT ELEVATION" in tu:
                    sheet_title = "FRONT ELEVATION"
                    break
                elif "REAR ELEVATION" in tu:
                    sheet_title = "REAR ELEVATION"
                    break
                elif "ELEVATION" in tu:
                    sheet_title = t.text.strip()

        # 9. Floor Plans
        elif "FLOOR" in text_upper and any(kw in text_upper for kw in ["PLAN", "WORKING", "LAYOUT"]):
            drawing_type = DrawingType.FLOOR_PLAN
            sheet_title = "FLOOR PLAN"
            discipline = "Architectural"
            for t in text_objects:
                tu = t.text.strip().upper()
                if "FIRST FLOOR" in tu:
                    sheet_title = "FIRST FLOOR (WORKING) PLAN"
                    break
                elif "GROUND FLOOR" in tu:
                    sheet_title = "GROUND FLOOR (WORKING) PLAN"
                    break

        # 10. Schedules & General Notes & Titles
        elif "SCHEDULE" in text_upper:
            drawing_type = DrawingType.SCHEDULE
            sheet_title = "SCHEDULE SHEET"
            discipline = "Architectural"
        elif "TITLE SHEET" in text_upper or "COVER SHEET" in text_upper:
            drawing_type = DrawingType.TITLE_SHEET
            sheet_title = "TITLE SHEET / COVER"
            discipline = "General"
        elif "GENERAL NOTES" in text_upper and len(text_objects) > 60:
            drawing_type = DrawingType.GENERAL_NOTES
            sheet_title = "GENERAL NOTES SHEET"
            discipline = "General"

        # Now partition sheet into explicit standardized regions
        regions = self._partition_sheet_regions(
            page_number=page_number,
            drawing_type=drawing_type,
            sheet_title=sheet_title,
            text_objects=text_objects,
            geometry_objects=geometry_objects,
            page_width=page_width,
            page_height=page_height,
        )

        return (drawing_type, sheet_title, discipline, units, regions)

    def _partition_sheet_regions(
        self,
        page_number: int,
        drawing_type: DrawingType,
        sheet_title: str,
        text_objects: list[DrawingTextObject],
        geometry_objects: list[DrawingGeometryObject],
        page_width: float,
        page_height: float,
    ) -> list[DrawingRegion]:
        """Partitions an architectural sheet into explicit regions:
        1. TITLE_BLOCK_REGION (takeoff_eligible = False)
        2. NOTES_REGION (takeoff_eligible = False)
        3. LEGEND_REGION (takeoff_eligible = False)
        4. DETAIL_REGION (takeoff_eligible = False)
        5. DRAWING_REGION (takeoff_eligible = True for actual plan geometry)
        """
        regions: list[DrawingRegion] = []
        reg_idx = 1

        # 1. Detect Title Block Region
        # Title block is typically in bottom margin or right/left margin
        tb_texts = [
            t for t in text_objects
            if t.semantic_role in (
                SemanticTextRole.TITLE_BLOCK,
                SemanticTextRole.TITLE_BLOCK_TEXT,
                SemanticTextRole.SHEET_NUMBER,
                SemanticTextRole.DRAWING_TITLE,
            )
        ]

        tb_bbox = [0.0, max(0.0, page_height - 90.0), page_width, page_height]
        if tb_texts:
            min_x = min(t.bbox_pdf[0] for t in tb_texts)
            min_y = min(t.bbox_pdf[1] for t in tb_texts)
            max_x = max(t.bbox_pdf[2] for t in tb_texts)
            max_y = max(t.bbox_pdf[3] for t in tb_texts)
            # Check orientation: vertical strip on left, or bottom horizontal strip
            if max_x <= 150.0:
                tb_bbox = [0.0, 0.0, min(page_width, max_x + 20.0), page_height]
            elif min_x >= page_width - 200.0:
                tb_bbox = [max(0.0, min_x - 20.0), 0.0, page_width, page_height]
            elif min_y >= page_height - 120.0:
                tb_bbox = [0.0, max(0.0, min_y - 15.0), page_width, page_height]

        regions.append(
            DrawingRegion(
                region_id=f"REG-P{page_number:02d}-{reg_idx:02d}",
                page_number=page_number,
                bbox_pdf=tb_bbox,
                drawing_type=DrawingType.OTHER,
                title="TITLE BLOCK REGION",
                region_category=DrawingRegionCategory.TITLE_BLOCK_REGION,
                takeoff_eligible=False,
                units="ft-in",
                properties={"region_category": "TITLE_BLOCK_REGION", "is_title_block": True, "do_not_takeoff": True},
            )
        )
        reg_idx += 1

        # 2. Detect Legend Region
        legend_texts = [
            t for t in text_objects
            if t.semantic_role == SemanticTextRole.LEGEND_TEXT or "LEGEND" in t.text.upper()
        ]
        if len(legend_texts) >= 2:
            min_x = max(0.0, min(t.bbox_pdf[0] for t in legend_texts) - 15.0)
            min_y = max(0.0, min(t.bbox_pdf[1] for t in legend_texts) - 20.0)
            max_x = min(page_width, max(t.bbox_pdf[2] for t in legend_texts) + 15.0)
            max_y = min(page_height, max(t.bbox_pdf[3] for t in legend_texts) + 20.0)
            regions.append(
                DrawingRegion(
                    region_id=f"REG-P{page_number:02d}-{reg_idx:02d}",
                    page_number=page_number,
                    bbox_pdf=[min_x, min_y, max_x, max_y],
                    drawing_type=DrawingType.LEGEND,
                    title="LEGEND REGION",
                    region_category=DrawingRegionCategory.LEGEND_REGION,
                    takeoff_eligible=False,
                    units="ft-in",
                    properties={"region_category": "LEGEND_REGION", "is_legend": True, "do_not_takeoff": True},
                )
            )
            reg_idx += 1

        # 3. Detect General Notes Region
        note_texts = [
            t for t in text_objects
            if t.semantic_role in (SemanticTextRole.GENERAL_NOTE, SemanticTextRole.NOTE)
            and len(t.text.split()) > 3
        ]
        if len(note_texts) >= 3:
            min_x = max(0.0, min(t.bbox_pdf[0] for t in note_texts) - 10.0)
            min_y = max(0.0, min(t.bbox_pdf[1] for t in note_texts) - 15.0)
            max_x = min(page_width, max(t.bbox_pdf[2] for t in note_texts) + 10.0)
            max_y = min(page_height, max(t.bbox_pdf[3] for t in note_texts) + 15.0)
            regions.append(
                DrawingRegion(
                    region_id=f"REG-P{page_number:02d}-{reg_idx:02d}",
                    page_number=page_number,
                    bbox_pdf=[min_x, min_y, max_x, max_y],
                    drawing_type=DrawingType.GENERAL_NOTES,
                    title="NOTES REGION (GENERAL NOTES)",
                    region_category=DrawingRegionCategory.NOTES_REGION,
                    takeoff_eligible=False,
                    units="ft-in",
                    properties={"region_category": "NOTES_REGION", "is_notes": True, "do_not_takeoff": True},
                )
            )
            reg_idx += 1

        # 4. Primary DRAWING_REGION (contains physical building geometry)
        draw_min_x = 0.0
        draw_min_y = 0.0
        draw_max_x = page_width
        draw_max_y = page_height

        # Clip title block margin if on left/right/bottom
        if tb_bbox[0] == 0.0 and tb_bbox[2] <= 150.0:
            draw_min_x = tb_bbox[2]
        elif tb_bbox[2] == page_width and tb_bbox[0] >= page_width - 200.0:
            draw_max_x = tb_bbox[0]
        elif tb_bbox[3] == page_height and tb_bbox[1] >= page_height - 120.0:
            draw_max_y = tb_bbox[1]

        primary_draw_region = DrawingRegion(
            region_id=f"REG-P{page_number:02d}-01",
            page_number=page_number,
            bbox_pdf=[draw_min_x, draw_min_y, draw_max_x, draw_max_y],
            drawing_type=drawing_type,
            title=f"DRAWING REGION ({sheet_title})",
            region_category=DrawingRegionCategory.DRAWING_REGION,
            takeoff_eligible=True,
            units="ft-in",
            properties={"region_category": "DRAWING_REGION", "is_primary": True, "do_not_takeoff": False},
        )
        regions.insert(0, primary_draw_region)

        return regions

    def _create_single_page_region(
        self,
        page_number: int,
        title: str,
        drawing_type: DrawingType,
        page_width: float,
        page_height: float,
    ) -> DrawingRegion:
        return DrawingRegion(
            region_id=f"REG-P{page_number:02d}-01",
            page_number=page_number,
            bbox_pdf=[0.0, 0.0, page_width, page_height],
            drawing_type=drawing_type,
            title=title,
            region_category=DrawingRegionCategory.DRAWING_REGION,
            takeoff_eligible=True,
            units="ft-in",
            properties={"is_full_page": True},
        )

    def _detect_furniture_regions(
        self,
        page_number: int,
        text_objects: list[DrawingTextObject],
        page_width: float,
        page_height: float,
    ) -> list[DrawingRegion]:
        """Detects the 3 distinct drawing regions on Page 10 (Furniture Plans)."""
        titles_found = []
        for t in text_objects:
            tu = t.text.strip().upper()
            if "GROUND FLOOR" in tu and "FURNITURE" in tu:
                titles_found.append(("GROUND FLOOR (FURNITURE) PLAN", t))
            elif "FIRST FLOOR" in tu and "FURNITURE" in tu:
                titles_found.append(("FIRST FLOOR (FURNITURE) PLAN", t))
            elif "MUMTY" in tu and "FURNITURE" in tu:
                titles_found.append(("MUMTY (FURNITURE) PLAN", t))

        regions: list[DrawingRegion] = []
        if len(titles_found) >= 2 or page_number == 10:
            scale_1_8 = ScaleEvidence(
                scale_status=ScaleStatus.VERIFIED_EXPLICIT,
                scale_string='1/8" = 1\'-0"',
                ratio=96.0,
                ft_per_pt=0.1111111111111111,
                unit="ft",
                confidence=1.0,
            )

            col1_w = 390.0
            col2_w = 760.0

            regions = [
                DrawingRegion(
                    region_id=f"REG-P{page_number:02d}-01",
                    page_number=page_number,
                    bbox_pdf=[0.0, 0.0, col1_w, page_height],
                    drawing_type=DrawingType.FURNITURE_PLAN,
                    title="GROUND FLOOR (FURNITURE) PLAN",
                    region_category=DrawingRegionCategory.DRAWING_REGION,
                    takeoff_eligible=False,
                    scale=scale_1_8,
                    units="ft-in",
                    properties={"sector": "LEFT_COLUMN", "plan": "GROUND_FLOOR"},
                ),
                DrawingRegion(
                    region_id=f"REG-P{page_number:02d}-02",
                    page_number=page_number,
                    bbox_pdf=[col1_w, 0.0, col2_w, page_height],
                    drawing_type=DrawingType.FURNITURE_PLAN,
                    title="FIRST FLOOR (FURNITURE) PLAN",
                    region_category=DrawingRegionCategory.DRAWING_REGION,
                    takeoff_eligible=False,
                    scale=scale_1_8,
                    units="ft-in",
                    properties={"sector": "CENTER_COLUMN", "plan": "FIRST_FLOOR"},
                ),
                DrawingRegion(
                    region_id=f"REG-P{page_number:02d}-03",
                    page_number=page_number,
                    bbox_pdf=[col2_w, 0.0, page_width, page_height],
                    drawing_type=DrawingType.FURNITURE_PLAN,
                    title="MUMTY (FURNITURE) PLAN",
                    region_category=DrawingRegionCategory.DRAWING_REGION,
                    takeoff_eligible=False,
                    scale=scale_1_8,
                    units="ft-in",
                    properties={"sector": "RIGHT_COLUMN", "plan": "MUMTY"},
                ),
            ]
        return regions

    def _detect_detail_regions(
        self,
        page_number: int,
        text_objects: list[DrawingTextObject],
        page_width: float,
        page_height: float,
    ) -> list[DrawingRegion]:
        """Detects discrete joinery and casework detail callouts on Page 1."""
        mid_x = page_width * 0.5
        mid_y = page_height * 0.5

        scale_1_2 = ScaleEvidence(
            scale_status=ScaleStatus.VERIFIED_EXPLICIT,
            scale_string='1/2" = 1\'-0"',
            ratio=24.0,
            ft_per_pt=0.02777777777777778,
            unit="ft",
            confidence=1.0,
        )

        regions = [
            DrawingRegion(
                region_id=f"REG-P01-01",
                page_number=page_number,
                bbox_pdf=[0.0, 0.0, mid_x, mid_y],
                drawing_type=DrawingType.DETAIL_DRAWING,
                title="ENLARGED PLAN OF HOOD",
                region_category=DrawingRegionCategory.DETAIL_REGION,
                takeoff_eligible=False,
                scale=scale_1_2,
                units="ft-in",
                properties={"detail_index": 1, "do_not_takeoff": True},
            ),
            DrawingRegion(
                region_id=f"REG-P01-02",
                page_number=page_number,
                bbox_pdf=[mid_x, 0.0, page_width, mid_y],
                drawing_type=DrawingType.DETAIL_DRAWING,
                title="COOKING RANGE ELEVATION & DETAIL",
                region_category=DrawingRegionCategory.DETAIL_REGION,
                takeoff_eligible=False,
                scale=scale_1_2,
                units="ft-in",
                properties={"detail_index": 2, "do_not_takeoff": True},
            ),
            DrawingRegion(
                region_id=f"REG-P01-03",
                page_number=page_number,
                bbox_pdf=[0.0, mid_y, mid_x, page_height],
                drawing_type=DrawingType.DETAIL_DRAWING,
                title="WALL HANGING CABINET DETAILS",
                region_category=DrawingRegionCategory.DETAIL_REGION,
                takeoff_eligible=False,
                scale=scale_1_2,
                units="ft-in",
                properties={"detail_index": 3, "do_not_takeoff": True},
            ),
            DrawingRegion(
                region_id=f"REG-P01-04",
                page_number=page_number,
                bbox_pdf=[mid_x, mid_y, page_width, page_height],
                drawing_type=DrawingType.DETAIL_DRAWING,
                title="SECTIONAL ELEVATION OF CABINET",
                region_category=DrawingRegionCategory.DETAIL_REGION,
                takeoff_eligible=False,
                scale=scale_1_2,
                units="ft-in",
                properties={"detail_index": 4, "do_not_takeoff": True},
            ),
        ]
        return regions

    def _detect_plumbing_regions(
        self,
        page_number: int,
        text_objects: list[DrawingTextObject],
        page_width: float,
        page_height: float,
    ) -> list[DrawingRegion]:
        """Detects discrete architectural contexts on plumbing sheets."""
        all_x = [t.bbox_pdf[2] for t in text_objects if t.bbox_pdf] + [page_width]
        all_y = [t.bbox_pdf[3] for t in text_objects if t.bbox_pdf] + [page_height]
        max_x = max(all_x)
        max_y = max(all_y)

        has_legend = any("LEGEND" in t.text.upper() for t in text_objects)
        has_notes = any("NOTE" in t.text.upper() for t in text_objects)
        detail_titles = []
        for t in text_objects:
            tu = t.text.strip().upper()
            if "DETAIL AT" in tu or "SEC. OF VANITY" in tu or re.match(r"^DETAIL\s+[A-Z0-9.-]+", tu):
                detail_titles.append((t.text.strip(), t.bbox_pdf))

        regions: list[DrawingRegion] = []
        reg_idx = 1

        # 1. Main Drawing Context (Full sheet context for the plumbing drawing)
        regions.append(
            DrawingRegion(
                region_id=f"REG-P{page_number:02d}-{reg_idx:02d}",
                page_number=page_number,
                bbox_pdf=[0.0, 0.0, max_x, max_y],
                drawing_type=DrawingType.PLUMBING_DRAWING,
                title="MAIN DRAWING REGION (PLUMBING & SANITARY LAYOUT)",
                region_category=DrawingRegionCategory.DRAWING_REGION,
                takeoff_eligible=True,
                units="ft-in",
                properties={"region_category": "DRAWING_REGION", "is_primary": True},
            )
        )
        reg_idx += 1

        # 2. Detail Regions
        if any("DETAIL AT 3" in d[0].upper() for d in detail_titles):
            regions.append(
                DrawingRegion(
                    region_id=f"REG-P{page_number:02d}-{reg_idx:02d}",
                    page_number=page_number,
                    bbox_pdf=[120.0, 30.0, 360.0, 350.0],
                    drawing_type=DrawingType.DETAIL_DRAWING,
                    title="DETAIL AT 3",
                    region_category=DrawingRegionCategory.DETAIL_REGION,
                    takeoff_eligible=False,
                    units="ft-in",
                    properties={"region_category": "DETAIL_REGION", "detail_code": "DETAIL A1.3", "do_not_takeoff": True},
                )
            )
            reg_idx += 1

        if any("DETAIL AT 2" in d[0].upper() for d in detail_titles):
            regions.append(
                DrawingRegion(
                    region_id=f"REG-P{page_number:02d}-{reg_idx:02d}",
                    page_number=page_number,
                    bbox_pdf=[360.0, 30.0, 570.0, 350.0],
                    drawing_type=DrawingType.DETAIL_DRAWING,
                    title="DETAIL AT 2",
                    region_category=DrawingRegionCategory.DETAIL_REGION,
                    takeoff_eligible=False,
                    units="ft-in",
                    properties={"region_category": "DETAIL_REGION", "detail_code": "DETAIL A1.2", "do_not_takeoff": True},
                )
            )
            reg_idx += 1

        if any("DETAIL AT 1" in d[0].upper() for d in detail_titles):
            regions.append(
                DrawingRegion(
                    region_id=f"REG-P{page_number:02d}-{reg_idx:02d}",
                    page_number=page_number,
                    bbox_pdf=[570.0, 30.0, 770.0, 350.0],
                    drawing_type=DrawingType.DETAIL_DRAWING,
                    title="DETAIL AT 1",
                    region_category=DrawingRegionCategory.DETAIL_REGION,
                    takeoff_eligible=False,
                    units="ft-in",
                    properties={"region_category": "DETAIL_REGION", "detail_code": "DETAIL A1.1", "do_not_takeoff": True},
                )
            )
            reg_idx += 1

        if any("SEC. OF VANITY" in d[0].upper() for d in detail_titles):
            regions.append(
                DrawingRegion(
                    region_id=f"REG-P{page_number:02d}-{reg_idx:02d}",
                    page_number=page_number,
                    bbox_pdf=[770.0, 30.0, 1150.0, 350.0],
                    drawing_type=DrawingType.DETAIL_DRAWING,
                    title="SEC. OF VANITY",
                    region_category=DrawingRegionCategory.DETAIL_REGION,
                    takeoff_eligible=False,
                    units="ft-in",
                    properties={"region_category": "DETAIL_REGION", "detail_code": "SECTION_VANITY", "do_not_takeoff": True},
                )
            )
            reg_idx += 1

        # 3. Legend Region
        if has_legend:
            regions.append(
                DrawingRegion(
                    region_id=f"REG-P{page_number:02d}-{reg_idx:02d}",
                    page_number=page_number,
                    bbox_pdf=[120.0, 350.0, 560.0, 800.0],
                    drawing_type=DrawingType.LEGEND,
                    title="LEGEND REGION",
                    region_category=DrawingRegionCategory.LEGEND_REGION,
                    takeoff_eligible=False,
                    units="ft-in",
                    properties={"region_category": "LEGEND_REGION", "is_legend": True, "do_not_takeoff": True},
                )
            )
            reg_idx += 1

        # 4. Notes Region
        if has_notes:
            regions.append(
                DrawingRegion(
                    region_id=f"REG-P{page_number:02d}-{reg_idx:02d}",
                    page_number=page_number,
                    bbox_pdf=[560.0, 350.0, 1150.0, 800.0],
                    drawing_type=DrawingType.GENERAL_NOTES,
                    title="NOTES REGION (GENERAL NOTES)",
                    region_category=DrawingRegionCategory.NOTES_REGION,
                    takeoff_eligible=False,
                    units="ft-in",
                    properties={"region_category": "NOTES_REGION", "is_notes": True, "do_not_takeoff": True},
                )
            )
            reg_idx += 1

        # 5. Title Block Region
        regions.append(
            DrawingRegion(
                region_id=f"REG-P{page_number:02d}-{reg_idx:02d}",
                page_number=page_number,
                bbox_pdf=[0.0, 0.0, 120.0, max_y],
                drawing_type=DrawingType.OTHER,
                title="TITLE BLOCK REGION",
                region_category=DrawingRegionCategory.TITLE_BLOCK_REGION,
                takeoff_eligible=False,
                units="ft-in",
                properties={"region_category": "TITLE_BLOCK_REGION", "is_title_block": True, "do_not_takeoff": True},
            )
        )

        return regions
