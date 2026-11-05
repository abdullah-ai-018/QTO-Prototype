"""Multi-Page Blueprint Sheet Classifier & Drawing Set Indexer.

Classifies drawing discipline, sheet type, drawing titles, and floor elevations
across multi-page architectural blueprint sets.
"""

import re
from typing import Any
from app.models.project_knowledge_graph import (
    SheetMetadata,
    SheetDiscipline,
    SheetType,
)


class BlueprintSheetClassifier:
    """Classifies blueprint pages into architectural disciplines and sheet roles."""

    def classify_sheet(
        self,
        page_id: int,
        page_number: int,
        text_content: str,
        filename: str | None = None,
    ) -> SheetMetadata:
        text_upper = text_content.upper()

        # 1. Extract Sheet Number (e.g. A-101, A101, ARCH-01)
        from app.geometry.page_classifier import normalize_sheet_number
        sheet_num_match = re.search(r"\b([A-Z]{1,3}[-\s]?\d{3,4}|[A-Z]{1,2}[-\s]?\d{1,2}(?:\.\d{1,2})?)\b", text_upper)
        sheet_number: str | None = normalize_sheet_number(sheet_num_match.group(1)) if sheet_num_match else None

        # 2. Extract Drawing Title
        sheet_title = "ARCHITECTURAL SHEET"
        if "FLOOR PLAN" in text_upper:
            title_match = re.search(r"([A-Z0-9\s\-]+FLOOR PLAN)", text_upper)
            sheet_title = title_match.group(1).strip() if title_match else "FLOOR PLAN"
        elif "PARTITION SCHEDULE" in text_upper or "WALL TYPE" in text_upper:
            sheet_title = "PARTITION SCHEDULE & WALL TYPES"
        elif "DOOR SCHEDULE" in text_upper or "WINDOW SCHEDULE" in text_upper:
            sheet_title = "DOOR & WINDOW SCHEDULE"
        elif "REFLECTED CEILING" in text_upper or "RCP" in text_upper:
            sheet_title = "REFLECTED CEILING PLAN"
        elif "WALL SECTION" in text_upper or "BUILDING SECTION" in text_upper:
            sheet_title = "WALL & BUILDING SECTIONS"
        elif "FINISH SCHEDULE" in text_upper:
            sheet_title = "ROOM FINISH SCHEDULE"
        elif "COVER" in text_upper or "INDEX" in text_upper:
            sheet_title = "COVER SHEET & INDEX"

        # 3. Determine Discipline
        discipline = SheetDiscipline.ARCHITECTURAL
        s_num = sheet_number or ""
        if s_num.startswith("S-") or (s_num.startswith("S") and len(s_num) > 1 and s_num[1].isdigit()) or "STRUCTURAL" in text_upper:
            discipline = SheetDiscipline.STRUCTURAL
        elif s_num.startswith("M-") or (s_num.startswith("M") and len(s_num) > 1 and s_num[1].isdigit()) or "MECHANICAL" in text_upper or "HVAC" in text_upper:
            discipline = SheetDiscipline.MECHANICAL
        elif s_num.startswith("E-") or (s_num.startswith("E") and len(s_num) > 1 and s_num[1].isdigit()) or "ELECTRICAL" in text_upper:
            discipline = SheetDiscipline.ELECTRICAL
        elif s_num.startswith("P-") or (s_num.startswith("P") and len(s_num) > 1 and s_num[1].isdigit()) or "PLUMBING" in text_upper:
            discipline = SheetDiscipline.PLUMBING
        elif s_num.startswith("C-") or (s_num.startswith("C") and len(s_num) > 1 and s_num[1].isdigit()) or "CIVIL" in text_upper:
            discipline = SheetDiscipline.CIVIL

        # 4. Determine Sheet Type
        sheet_type = SheetType.UNKNOWN
        is_drywall_auth = False

        if "PARTITION SCHEDULE" in text_upper or "WALL TYPE" in text_upper or "WALL SCHEDULE" in text_upper:
            sheet_type = SheetType.PARTITION_SCHEDULE
            is_drywall_auth = True
        elif "DOOR SCHEDULE" in text_upper or "WINDOW SCHEDULE" in text_upper:
            sheet_type = SheetType.DOOR_WINDOW_SCHEDULE
            is_drywall_auth = True
        elif "FINISH SCHEDULE" in text_upper or "ROOM FINISH" in text_upper:
            sheet_type = SheetType.FINISH_SCHEDULE
            is_drywall_auth = True
        elif "REFLECTED CEILING" in text_upper or "RCP" in text_upper:
            sheet_type = SheetType.REFLECTED_CEILING_PLAN
            is_drywall_auth = True
        elif "WALL SECTION" in text_upper or "BUILDING SECTION" in text_upper:
            sheet_type = SheetType.WALL_SECTIONS
            is_drywall_auth = True
        elif "FLOOR PLAN" in text_upper or "THIRD FLOOR" in text_upper or "SECOND FLOOR" in text_upper or "FIRST FLOOR" in text_upper:
            sheet_type = SheetType.FLOOR_PLAN
            is_drywall_auth = True
        elif "COVER" in text_upper or "INDEX" in text_upper or "DRAWING LIST" in text_upper:
            sheet_type = SheetType.COVER_INDEX

        # 5. Extract Scale String & Elevation
        scale_match = re.search(r"\b(SCALE\s*[:\s]?\s*[\d/]+[\"']?\s*=\s*[\d'\"]+|SC\s*1:\d{2,3}|1:\d{2,3})\b", text_upper)
        scale_str = scale_match.group(1) if scale_match else None

        elev_match = re.search(r"([+-]\d+\.\d{2}M?)", text_upper)
        level_elevation = elev_match.group(1) if elev_match else None

        return SheetMetadata(
            page_id=page_id,
            page_number=page_number,
            sheet_number=sheet_number,
            sheet_title=sheet_title,
            discipline=discipline,
            sheet_type=sheet_type,
            scale_str=scale_str,
            level_elevation=level_elevation,
            is_drywall_authoritative=is_drywall_auth,
            text_content_sample=text_content[:300],
            text_content_full=text_content,
        )
