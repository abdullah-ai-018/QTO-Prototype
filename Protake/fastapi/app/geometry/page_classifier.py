"""Smart Page & Zone Classifier Module (Estimator-Grade Drawing Intelligence).

Classifies blueprint sheets based on PRIMARY DRAWING INTENT over incidental secondary keywords.
Separates primary drawing type, secondary content, geometry authority, schedule authority,
and takeoff eligibility.

Precedence Hierarchy:
1. Explicit Architectural Plan Titles (PARTITION PLAN, FLOOR PLAN, DEMO PLAN, RCP, ROOF PLAN, EGRESS PLAN)
2. Primary Discipline Codes (A-, S-, M-, E-, P-, C-)
3. Standalone Schedule Sheets (where schedule is the sole topic/title)
4. Density & Vector Geometry Fallbacks
"""

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any


class PageType(str, Enum):
    FLOOR_PLAN = "floor_plan"
    PARTITION_PLAN = "partition_plan"
    ROOF_PLAN = "roof_plan"
    SITE_PLAN = "site_plan"
    ELEVATION = "elevation"
    SECTION = "section"
    RCP = "rcp"  # reflected ceiling plan
    DEMOLITION_PLAN = "demolition_plan"
    LIFE_SAFETY_EGRESS_PLAN = "life_safety_egress_plan"
    FINISH_PLAN = "finish_plan"
    SCHEDULE_SPECIFICATION = "schedule_specification"
    NON_ARCHITECTURAL = "non_architectural"
    TEXT_SPECIFICATION = "text_specification"
    EMPTY_BLANK = "empty_blank"


class TradeRelevance(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NOT_RELEVANT = "NOT_RELEVANT"


def get_trade_relevance(page_type: PageType | str | None, trade: str | None) -> TradeRelevance:
    """Evaluates whether a sheet's primary drawing type is relevant to a specific trade.
    Prevents non-relevant sheets (e.g. roof plans for drywall, floor plans for roofing)
    from generating false candidates or takeoff quantities.
    """
    if not page_type:
        return TradeRelevance.NOT_RELEVANT
    
    pt = page_type.value if hasattr(page_type, "value") else str(page_type)
    tr = (trade.value if hasattr(trade, "value") else str(trade)).lower() if trade else None

    if not tr or tr in ("all", "none"):
        # Generic context
        if pt in (PageType.FLOOR_PLAN.value, PageType.PARTITION_PLAN.value, PageType.RCP.value):
            return TradeRelevance.HIGH
        elif pt in (PageType.ROOF_PLAN.value, PageType.SECTION.value, PageType.ELEVATION.value):
            return TradeRelevance.MEDIUM
        return TradeRelevance.NOT_RELEVANT

    if tr == "drywall":
        if pt in (PageType.PARTITION_PLAN.value, PageType.FLOOR_PLAN.value):
            return TradeRelevance.HIGH
        elif pt == PageType.RCP.value:
            return TradeRelevance.MEDIUM  # Ceiling GWB only
        else:
            # Elevations, sections, roof plans, site plans, demo plans, schedules, notes, MEP
            return TradeRelevance.NOT_RELEVANT



    if tr == "roofing":
        if pt == PageType.ROOF_PLAN.value:
            return TradeRelevance.HIGH
        elif pt in (PageType.SECTION.value, PageType.ELEVATION.value):
            return TradeRelevance.MEDIUM
        else:
            return TradeRelevance.NOT_RELEVANT

    if tr == "flooring":
        if pt in (PageType.FLOOR_PLAN.value, PageType.FINISH_PLAN.value):
            return TradeRelevance.HIGH
        elif pt == PageType.PARTITION_PLAN.value:
            return TradeRelevance.MEDIUM
        else:
            return TradeRelevance.NOT_RELEVANT

    if tr == "painting":
        if pt in (PageType.FLOOR_PLAN.value, PageType.PARTITION_PLAN.value, PageType.FINISH_PLAN.value):
            return TradeRelevance.HIGH
        elif pt in (PageType.ELEVATION.value, PageType.RCP.value):
            return TradeRelevance.MEDIUM
        else:
            return TradeRelevance.NOT_RELEVANT

    return TradeRelevance.NOT_RELEVANT


LEGACY_ARCHITECTURAL = "architectural"


def normalize_sheet_number(raw: str | None) -> str:
    """Normalizes architectural sheet numbers to canonical form (e.g. A401, A 401, A-401 -> A-401)."""
    if not raw:
        return "Sheet number unavailable from source"
    s = raw.strip().upper()
    if s in ("UNKNOWN", "NONE", ""):
        return "Sheet number unavailable from source"

    # Pattern 1: e.g. A-101, AD-101, S-301, M-201, E-101, P-101
    m1 = re.match(r"^([A-Z]{1,3})[\s\-_]+(\d{1,4}(?:\.\d{1,2})?)$", s)
    if m1:
        return f"{m1.group(1)}-{m1.group(2)}"

    # Pattern 2: e.g. A101, AD101, S301, M201, E101, P101
    m2 = re.match(r"^([A-Z]{1,3})(\d{2,4}(?:\.\d{1,2})?)$", s)
    if m2:
        return f"{m2.group(1)}-{m2.group(2)}"

    # Pattern 3: e.g. A0.1, A1.01
    m3 = re.match(r"^([A-Z]{1,3})(\d\.\d{1,2})$", s)
    if m3:
        return f"{m3.group(1)}-{m3.group(2)}"

    if re.match(r"^[A-Z]{1,3}\d+", s):
        return re.sub(r"^([A-Z]{1,3})\s*(\d)", r"\1-\2", s)

    return s


@dataclass
class ClassificationResult:
    page_type: PageType
    discipline: str  # Architectural, Electrical, Mechanical, Structural, Plumbing, Civil, General
    is_takeoff_eligible: bool
    skip_reason: str | None
    drawing_zone_bbox: dict[str, float]  # Normalized bbox for drawing area (excluding title block)
    primary_title: str = "ARCHITECTURAL SHEET"
    secondary_content: list[str] = field(default_factory=list)
    geometry_authority: str = "NONE"  # PARTITION_WALLS, CEILING_GWB, ROOF_SURFACES, DEMOLITION, CONTEXT_ONLY, NONE
    schedule_authority: str | None = None
    confidence: float = 0.95
    classification_evidence: list[str] = field(default_factory=list)
    exclusion_evidence: list[str] = field(default_factory=list)


@dataclass
class PageEvidence:
    page_number: int
    sheet_number: str
    sheet_title: str
    discipline: str
    page_type: str
    confidence: float = 0.95
    takeoff_eligible: bool = False
    scale: str = "1/4\" = 1'-0\""
    candidate_trades: list[str] = field(default_factory=list)
    contains: dict[str, bool] = field(default_factory=lambda: {
        "walls": False,
        "doors": False,
        "windows": False,
        "rooms": False,
        "dimensions": True,
        "grids": True,
        "details": False,
        "schedules": False,
        "elevations": False,
        "sections": False,
        "notes": True,
    })
    drawing_regions: list[dict[str, Any]] = field(default_factory=list)
    source_regions: list[dict[str, Any]] = field(default_factory=list)
    classification_evidence: list[str] = field(default_factory=list)
    exclusion_evidence: list[str] = field(default_factory=list)
    skip_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_number": self.page_number,
            "sheet_number": self.sheet_number,
            "sheet_title": self.sheet_title,
            "discipline": self.discipline,
            "page_type": self.page_type,
            "confidence": self.confidence,
            "takeoff_eligible": self.takeoff_eligible,
            "scale": self.scale,
            "candidate_trades": self.candidate_trades,
            "contains": self.contains,
            "drawing_regions": self.drawing_regions,
            "source_regions": self.source_regions,
            "classification_evidence": self.classification_evidence,
            "exclusion_evidence": self.exclusion_evidence,
            "skip_reason": self.skip_reason,
        }


# 1. Primary Architectural Drawing Title Patterns (Strict Precedence)
_PRIMARY_PARTITION_PLAN_RE = re.compile(
    r"\b(PARTITION\s+AND\s+HARDSCAPE\s+PLAN|PARTITION\s+PLAN|NEW\s+PARTITION\s+PLAN|TENANT\s+IMPROVEMENT\s+PLAN)\b",
    re.IGNORECASE,
)
_PRIMARY_FLOOR_PLAN_RE = re.compile(
    r"\b(FLOOR\s+PLAN|ARCHITECTURAL\s+FLOOR\s+PLAN|CONSTRUCTION\s+PLAN|OVERALL\s+FLOOR\s+PLAN|FIRST\s+FLOOR\s+PLAN|SECOND\s+FLOOR\s+PLAN|THIRD\s+FLOOR\s+PLAN|GROUND\s+FLOOR\s+PLAN|LEVEL\s+\d+\s+PLAN)\b",
    re.IGNORECASE,
)
_PRIMARY_DEMOLITION_PLAN_RE = re.compile(
    r"\b(DEMOLITION\s+PLAN|DEMO\s+PLAN|EXISTING\s+DEMOLITION\s+PLAN)\b",
    re.IGNORECASE,
)
_PRIMARY_EGRESS_PLAN_RE = re.compile(
    r"\b(MEANS\s+OF\s+EGRESS\s+PLAN|EGRESS\s+PLAN|LIFE\s+SAFETY\s+PLAN|CODE\s+COMPLIANCE\s+PLAN)\b",
    re.IGNORECASE,
)
_PRIMARY_RCP_RE = re.compile(
    r"\b(REFLECTED\s+CEILING\s+PLAN|REFLECTED\s+CEILING/CANOPY\s+PLAN|RCP|CEILING\s+PLAN)\b",
    re.IGNORECASE,
)
_PRIMARY_ROOF_PLAN_RE = re.compile(
    r"\b(ROOF\s+PLAN|ROOF\s+FRAMING\s+PLAN)\b",
    re.IGNORECASE,
)
_PRIMARY_FINISH_PLAN_RE = re.compile(
    r"\b(FINISH\s+PLAN|ROOM\s+FINISH\s+PLAN|FLOOR\s+FINISH\s+PLAN)\b",
    re.IGNORECASE,
)
_PRIMARY_ELEVATION_RE = re.compile(
    r"\b(EXTERIOR\s+ELEVATIONS?|BUILDING\s+ELEVATIONS?|INTERIOR\s+ELEVATIONS?)\b",
    re.IGNORECASE,
)
_PRIMARY_SECTION_RE = re.compile(
    r"\b(BUILDING\s+SECTIONS?|WALL\s+SECTIONS?|ARCHITECTURAL\s+SECTIONS?)\b",
    re.IGNORECASE,
)
_PRIMARY_SITE_PLAN_RE = re.compile(
    r"\b(CIVIL\s+SITE\s+PLAN|GRADING\s+PLAN|UTILITY\s+PLAN|OVERALL\s+SITE\s+PLAN)\b",
    re.IGNORECASE,
)

# 2. Pure Standalone Schedule Sheet Titles (Only when the sheet is solely a schedule)
_STANDALONE_SCHEDULE_RE = re.compile(
    r"\b(DOOR\s+&\s+WINDOW\s+SCHEDULE|DOOR\s+SCHEDULE|WINDOW\s+SCHEDULE|PARTITION\s+SCHEDULE\s+&\s+WALL\s+TYPES|"
    r"WALL\s+TYPE\s+SCHEDULE|ROOM\s+FINISH\s+SCHEDULE|FINISH\s+SCHEDULE\s+&\s+LEGEND|"
    r"TABLE\s+OF\s+CONTENTS|DRAWING\s+INDEX|COVER\s+SHEET)\b",
    re.IGNORECASE,
)

# 3. Non-Architectural Discipline Codes
_ELEC_MECH_SHEET_CODE_RE = re.compile(r"\b([EMPS])-(\d{3,4}|\d{1,2})\b", re.IGNORECASE)
_ELEC_MECH_LABEL_RE = re.compile(
    r"\b(ELECTRICAL|MECHANICAL|PLUMBING|STRUCTURAL)\s+(PLAN|DRAWING|LAYOUT|SCHEDULE|FRAMING)\b",
    re.IGNORECASE,
)

MIN_FLOOR_PLAN_LINE_SEGMENTS = 250


def classify_page_content(
    image_path: str | None,
    raw_text_tokens: list[str],
    line_segment_count: int,
) -> ClassificationResult:
    """Top-Level Estimator-Grade Page Classifier.
    Applies strict primary drawing intent precedence over incidental secondary keywords.
    Hard gates drywall takeoff eligibility based on verified sheet intent.
    """
    full_text = " ".join(raw_text_tokens).upper()

    # Rule 1: Empty or Blank Page Detection
    if line_segment_count < 15 and len(raw_text_tokens) < 5:
        return ClassificationResult(
            page_type=PageType.EMPTY_BLANK,
            discipline="General",
            is_takeoff_eligible=False,
            skip_reason="Blank or empty page — line density under minimum threshold",
            drawing_zone_bbox={"minX": 0.0, "minY": 0.0, "maxX": 1.0, "maxY": 1.0},
            primary_title="BLANK PAGE",
            geometry_authority="NONE",
            confidence=0.99,
            exclusion_evidence=["insufficient_linework", "insufficient_text"],
        )

    # Rule 2: Secondary Content Discovery
    secondary_items = []
    if "HARDSCAPE" in full_text:
        secondary_items.append("HARDSCAPE")
    if "OCCUPANCY SUMMARY" in full_text or "OCCUPANCY" in full_text:
        secondary_items.append("OCCUPANCY_SUMMARY")
    if "EGRESS WIDTH SUMMARY" in full_text:
        secondary_items.append("EGRESS_WIDTH_SUMMARY")
    if "GENERAL NOTES" in full_text:
        secondary_items.append("GENERAL_NOTES")
    if "KEYNOTES" in full_text:
        secondary_items.append("KEYNOTES")

    # High-Precedence 2A0: Sheet Index, General Notes, and Cover Sheets
    # (Must evaluate BEFORE Floor Plan regex because index tables list 'A2.1 Floor Plan' in their text)
    _PRIMARY_COVER_INDEX_NOTES_RE = re.compile(
        r"\b(SHEET\s+INDEX\s+AND\s+NOTES|SHEET\s+INDEX|DRAWING\s+INDEX|INDEX\s+OF\s+DRAWINGS|"
        r"GENERAL\s+NOTES\s+AND\s+INDEX|COVER\s+SHEET|PROJECT\s+DIRECTORY|ABBREVIATIONS\s+&\s+SYMBOLS|"
        r"TITLE\s+SHEET|TITLE\s+PAGE)\b",
        re.IGNORECASE,
    )
    if _PRIMARY_COVER_INDEX_NOTES_RE.search(full_text):
        return ClassificationResult(
            page_type=PageType.SCHEDULE_SPECIFICATION,
            discipline="General",
            is_takeoff_eligible=False,
            skip_reason="Sheet index / General notes sheet — table linework excluded from wall geometry takeoff",
            drawing_zone_bbox={"minX": 0.0, "minY": 0.0, "maxX": 1.0, "maxY": 1.0},
            primary_title="SHEET INDEX & NOTES",
            secondary_content=secondary_items,
            geometry_authority="NONE",
            schedule_authority="STANDALONE_SCHEDULE",
            confidence=0.98,
            classification_evidence=["title_match: SHEET INDEX & NOTES"],
            exclusion_evidence=["index_and_general_notes_sheet"],
        )


    # 2A. Means of Egress / Life Safety Plan (Strict Context Only — HARD GATE: NO DRYWALL TAKEOFF)
    if _PRIMARY_EGRESS_PLAN_RE.search(full_text):
        return ClassificationResult(
            page_type=PageType.LIFE_SAFETY_EGRESS_PLAN,
            discipline="Architectural",
            is_takeoff_eligible=False,
            skip_reason="Life safety / Means of egress plan — not eligible for drywall partition takeoff",
            drawing_zone_bbox={"minX": 0.05, "minY": 0.05, "maxX": 0.88, "maxY": 0.92},
            primary_title="MEANS OF EGRESS PLAN",
            secondary_content=secondary_items,
            geometry_authority="CONTEXT_ONLY",
            confidence=0.98,
            classification_evidence=["title_match: MEANS OF EGRESS PLAN", "life_safety_indicators"],
            exclusion_evidence=["life_safety_egress_plan", "no_drywall_partition_scope"],
        )

    # 2B. Partition Plan (Primary Drywall Geometry Authority — TAKEOFF ELIGIBLE)
    if _PRIMARY_PARTITION_PLAN_RE.search(full_text):
        return ClassificationResult(
            page_type=PageType.PARTITION_PLAN,
            discipline="Architectural",
            is_takeoff_eligible=True,
            skip_reason=None,
            drawing_zone_bbox={"minX": 0.05, "minY": 0.05, "maxX": 0.88, "maxY": 0.92},
            primary_title="PARTITION AND FLOOR PLAN",
            secondary_content=secondary_items,
            geometry_authority="PARTITION_WALLS",
            schedule_authority=None,
            confidence=0.96,
            classification_evidence=["title_match: PARTITION PLAN", "partition_wall_types_referenced"],
        )

    # 2C. Demolition Plan (Demolition Scope Only — HARD GATE FOR NEW DRYWALL TAKEOFF)
    if _PRIMARY_DEMOLITION_PLAN_RE.search(full_text):
        return ClassificationResult(
            page_type=PageType.DEMOLITION_PLAN,
            discipline="Architectural",
            is_takeoff_eligible=False,
            skip_reason="Demolition plan — demolition scope only, excluded from new drywall takeoff",
            drawing_zone_bbox={"minX": 0.05, "minY": 0.05, "maxX": 0.88, "maxY": 0.92},
            primary_title="DEMOLITION PLAN",
            secondary_content=secondary_items,
            geometry_authority="DEMOLITION",
            confidence=0.95,
            classification_evidence=["title_match: DEMOLITION PLAN"],
            exclusion_evidence=["demolition_scope_only", "no_new_drywall_scope"],
        )

    # 2D. Reflected Ceiling Plan (Ceiling GWB Authority — TAKEOFF ELIGIBLE FOR CEILINGS)
    if _PRIMARY_RCP_RE.search(full_text):
        return ClassificationResult(
            page_type=PageType.RCP,
            discipline="Architectural",
            is_takeoff_eligible=True,
            skip_reason=None,
            drawing_zone_bbox={"minX": 0.05, "minY": 0.05, "maxX": 0.88, "maxY": 0.92},
            primary_title="REFLECTED CEILING PLAN",
            secondary_content=secondary_items,
            geometry_authority="CEILING_GWB",
            confidence=0.95,
            classification_evidence=["title_match: REFLECTED CEILING PLAN"],
        )

    # 2E. Finish Plan (Room & Floor Finish Authority — Not Primary Partition Wall Source)
    if _PRIMARY_FINISH_PLAN_RE.search(full_text):
        return ClassificationResult(
            page_type=PageType.FINISH_PLAN,
            discipline="Architectural",
            is_takeoff_eligible=False,
            skip_reason="Room finish plan — finish schedule authority only, not primary partition wall LF source",
            drawing_zone_bbox={"minX": 0.05, "minY": 0.05, "maxX": 0.88, "maxY": 0.92},
            primary_title="ROOM FINISH PLAN",
            secondary_content=secondary_items,
            geometry_authority="FINISH_SCOPE",
            confidence=0.92,
            classification_evidence=["title_match: FINISH PLAN"],
            exclusion_evidence=["finish_schedule_scope_only"],
        )

    # Rule 3: Non-Architectural Discipline Checks (E-, M-, P-, S-, C-, FP-)
    sheet_code_match = _ELEC_MECH_SHEET_CODE_RE.search(full_text)
    label_match = _ELEC_MECH_LABEL_RE.search(full_text)
    if sheet_code_match or label_match:
        if sheet_code_match:
            matched_discipline = {"E": "Electrical", "M": "Mechanical", "P": "Plumbing", "S": "Structural"}[
                sheet_code_match.group(1).upper()
            ]
        else:
            matched_discipline = label_match.group(1).title()
        return ClassificationResult(
            page_type=PageType.NON_ARCHITECTURAL,
            discipline=matched_discipline,
            is_takeoff_eligible=False,
            skip_reason=f"{matched_discipline} drawing detected — architectural partition takeoff excluded",
            drawing_zone_bbox={"minX": 0.05, "minY": 0.05, "maxX": 0.85, "maxY": 0.92},
            primary_title=f"{matched_discipline.upper()} DRAWING",
            geometry_authority="NONE",
            confidence=0.98,
            classification_evidence=[f"non_architectural_discipline: {matched_discipline}"],
            exclusion_evidence=[f"{matched_discipline.lower()}_trade_exclusion"],
        )

    # 2F. Standard Floor Plan (Primary Architectural Takeoff Eligible)
    if _PRIMARY_FLOOR_PLAN_RE.search(full_text):
        return ClassificationResult(
            page_type=PageType.FLOOR_PLAN,
            discipline="Architectural",
            is_takeoff_eligible=True,
            skip_reason=None,
            drawing_zone_bbox={"minX": 0.05, "minY": 0.05, "maxX": 0.88, "maxY": 0.92},
            primary_title="FLOOR PLAN",
            secondary_content=secondary_items,
            geometry_authority="PARTITION_WALLS",
            confidence=0.94,
            classification_evidence=["title_match: FLOOR PLAN"],
        )

    # 2G. Roof Plan (Roofing Authority)
    if _PRIMARY_ROOF_PLAN_RE.search(full_text):
        return ClassificationResult(
            page_type=PageType.ROOF_PLAN,
            discipline="Architectural",
            is_takeoff_eligible=True,
            skip_reason=None,
            drawing_zone_bbox={"minX": 0.05, "minY": 0.05, "maxX": 0.88, "maxY": 0.92},
            primary_title="ROOF PLAN",
            secondary_content=secondary_items,
            geometry_authority="ROOF_SURFACES",
            confidence=0.94,
            classification_evidence=["title_match: ROOF PLAN"],
        )

    # 2H. Elevations & Sections (Not Primary Wall LF Source)
    if _PRIMARY_ELEVATION_RE.search(full_text):
        return ClassificationResult(
            page_type=PageType.ELEVATION,
            discipline="Architectural",
            is_takeoff_eligible=False,
            skip_reason="Building / Interior elevations — vertical height reference, not primary wall LF source",
            drawing_zone_bbox={"minX": 0.05, "minY": 0.05, "maxX": 0.88, "maxY": 0.92},
            primary_title="BUILDING ELEVATIONS",
            geometry_authority="ELEVATION_HEIGHTS",
            confidence=0.95,
            classification_evidence=["title_match: ELEVATIONS"],
            exclusion_evidence=["elevation_sheet_not_plan_view"],
        )

    if _PRIMARY_SECTION_RE.search(full_text):
        return ClassificationResult(
            page_type=PageType.SECTION,
            discipline="Architectural",
            is_takeoff_eligible=False,
            skip_reason="Wall & building sections — assembly details, not primary partition wall LF source",
            drawing_zone_bbox={"minX": 0.05, "minY": 0.05, "maxX": 0.88, "maxY": 0.92},
            primary_title="WALL & BUILDING SECTIONS",
            geometry_authority="SECTION_ASSEMBLIES",
            confidence=0.95,
            classification_evidence=["title_match: SECTIONS"],
            exclusion_evidence=["section_detail_sheet"],
        )

    # Rule 4: Standalone Specification / Schedule Sheets (when no plan title matches)
    if _STANDALONE_SCHEDULE_RE.search(full_text):
        return ClassificationResult(
            page_type=PageType.SCHEDULE_SPECIFICATION,
            discipline="General",
            is_takeoff_eligible=False,
            skip_reason="Standalone schedule table or index sheet — physical room/wall takeoff skipped",
            drawing_zone_bbox={"minX": 0.0, "minY": 0.0, "maxX": 1.0, "maxY": 1.0},
            primary_title="SCHEDULE & SPECIFICATIONS",
            geometry_authority="NONE",
            schedule_authority="STANDALONE_SCHEDULE",
            confidence=0.96,
            classification_evidence=["title_match: SCHEDULE/INDEX"],
            exclusion_evidence=["schedule_table_only"],
        )

    # Rule 5: Pure Civil / Site Plan (only when no architectural building plan title matches)
    if _PRIMARY_SITE_PLAN_RE.search(full_text):
        return ClassificationResult(
            page_type=PageType.SITE_PLAN,
            discipline="Civil",
            is_takeoff_eligible=False,
            skip_reason="Civil site/grading plan detected — architectural interior takeoff skipped",
            drawing_zone_bbox={"minX": 0.05, "minY": 0.05, "maxX": 0.90, "maxY": 0.90},
            primary_title="CIVIL SITE PLAN",
            geometry_authority="NONE",
            confidence=0.96,
            classification_evidence=["title_match: SITE PLAN"],
            exclusion_evidence=["civil_site_scope_only"],
        )

    # Rule 6: Geometry Density Fallback
    if line_segment_count < MIN_FLOOR_PLAN_LINE_SEGMENTS:
        return ClassificationResult(
            page_type=PageType.TEXT_SPECIFICATION,
            discipline="General",
            is_takeoff_eligible=False,
            skip_reason=f"No drawing-type label found and only {line_segment_count} line segments detected",
            drawing_zone_bbox={"minX": 0.0, "minY": 0.0, "maxX": 1.0, "maxY": 1.0},
            primary_title="GENERAL NOTES & COVER",
            geometry_authority="NONE",
            confidence=0.85,
            exclusion_evidence=["insufficient_line_density"],
        )

    # Default to Floor Plan if high line density architectural linework exists
    return ClassificationResult(
        page_type=PageType.FLOOR_PLAN,
        discipline="Architectural",
        is_takeoff_eligible=True,
        skip_reason=None,
        drawing_zone_bbox={"minX": 0.05, "minY": 0.05, "maxX": 0.88, "maxY": 0.92},
        primary_title="FLOOR PLAN",
        geometry_authority="PARTITION_WALLS",
        confidence=0.85,
        classification_evidence=["high_density_vector_fallback"],
    )


# A sheet-code-shaped token immediately preceded by "<digits>/" is a detail
# or section CALLOUT referencing another sheet (e.g. "3/A401"), not this
# page's own sheet number — must never be confused with one.
_CALLOUT_PREFIX_RE = re.compile(r"\d\s*/\s*$")

_SHEET_NUMBER_TOKEN_RE = re.compile(
    r"\b([A-Z]{1,3}\s*\d{1,2}\.\d{1,2}|[A-Z]{1,3}\s*[-–—]\s*\d{1,4}|[A-Z]{1,3}\s*\d{2,4})\b"
)


def extract_sheet_number_from_page(page: Any) -> tuple[str | None, float]:
    """Real, multi-signal, title-block-localized sheet number extraction
    directly from a PDF page's own native text layer (no OCR — this reads
    the same PyMuPDF text blocks the rest of this module already uses).

    Evidence priority: the title-block quadrant (bottom-right, right edge,
    or bottom edge — the same region used by extract_page_evidence below)
    is searched first; only when nothing there matches does this fall back
    to any other text block on the page, at lower confidence. A candidate
    immediately preceded by "<digit>/" is rejected outright — that shape is
    a detail/section callout referencing a DIFFERENT sheet (e.g. "3/A401"),
    never this page's own sheet number.

    Returns (None, 0.0) when nothing can be confidently read. Callers must
    treat that as "sheet number unavailable from source" — never fall back
    to a page-index-derived placeholder like "A101"/"A102".
    """
    try:
        w_p, h_p = page.rect.width, page.rect.height
        raw_blocks = page.get_text("blocks")
        if isinstance(raw_blocks, dict):
            raw_blocks = raw_blocks.get("blocks", [])

        normalized_blocks = []
        for b in raw_blocks:
            if isinstance(b, (list, tuple)) and len(b) >= 5:
                normalized_blocks.append((b[0], b[1], b[2], b[3], str(b[4])))
            elif isinstance(b, dict):
                bbox = b.get("bbox", [0, 0, 0, 0])
                txt = b.get("text", "")
                if not txt and "lines" in b:
                    txt = " ".join(
                        span.get("text", "")
                        for line in b.get("lines", [])
                        for span in line.get("spans", [])
                    )
                normalized_blocks.append((bbox[0], bbox[1], bbox[2], bbox[3], txt))

        tb_blocks = [
            b for b in normalized_blocks
            if (b[0] / w_p > 0.80 and b[1] / h_p > 0.60) or (b[0] / w_p > 0.85) or (b[1] / h_p > 0.85 and b[0] / w_p > 0.50)
        ]
        other_blocks = [b for b in normalized_blocks if b not in tb_blocks]

        for block_group, confidence in ((tb_blocks, 0.90), (other_blocks, 0.55)):
            for block in block_group:
                b_text = block[4]
                for m in _SHEET_NUMBER_TOKEN_RE.finditer(b_text):
                    if _CALLOUT_PREFIX_RE.search(b_text[: m.start()]):
                        continue
                    normalized = normalize_sheet_number(m.group(1))
                    if normalized and normalized != "Sheet number unavailable from source":
                        return normalized, confidence
        return None, 0.0
    except Exception:
        return None, 0.0


def extract_page_evidence(pdf_path: str, page_number: int, line_segment_count: int = 100) -> PageEvidence:
    """Extracts rich, auditable PageEvidence for an arbitrary PDF sheet."""
    try:
        import fitz
        doc = fitz.open(pdf_path)
        if page_number < 1 or page_number > len(doc):
            return PageEvidence(
                page_number=page_number,
                sheet_number=f"P{page_number}",
                sheet_title="UNKNOWN",
                discipline="GENERAL",
                page_type="UNKNOWN",
                confidence=0.0,
                takeoff_eligible=False,
                skip_reason="Page number out of range",
            )
        page = doc[page_number - 1]
        drawings = page.get_drawings()
        real_line_count = sum(len(d.get("items", [])) for d in drawings)
        if real_line_count > 0:
            line_segment_count = real_line_count

        text_tokens = [w[4].strip() for w in page.get_text("words") if w[4].strip()]
        res = classify_page_content(None, text_tokens, line_segment_count)

        sheet_num = f"P{page_number}"
        sheet_title = res.primary_title
        evidence_notes = list(res.classification_evidence)
        exclusion_notes = list(res.exclusion_evidence)

        # Discover sheet number and title: prioritize title-block quadrant (bottom-right x > 0.80, y > 0.60 or right edge x > 0.85 or bottom edge x > 0.50, y > 0.85)
        w_p, h_p = page.rect.width, page.rect.height
        tb_blocks = [b for b in page.get_text("blocks") if (b[0] / w_p > 0.80 and b[1] / h_p > 0.60) or (b[0] / w_p > 0.85) or (b[1] / h_p > 0.85 and b[0] / w_p > 0.50)]
        other_blocks = [b for b in page.get_text("blocks") if b not in tb_blocks]

        found_sheet_num = None
        for block in tb_blocks + other_blocks:
            b_text = block[4].strip()
            num_m = re.search(r"\b([A-Z]{1,3}\s*\d{1,2}\.\d{1,2}|[A-Z]{1,3}\s*[-–—]\s*\d{1,4}|[A-Z]{1,3}\s*\d{2,4})\b", b_text)
            if num_m:
                found_sheet_num = normalize_sheet_number(num_m.group(1))
                evidence_notes.append(f"sheet_number_found: {found_sheet_num}")
                break

        if found_sheet_num:
            sheet_num = found_sheet_num

        # Check for title in title block
        title_candidates = []
        for block in tb_blocks:
            lines = [l.strip() for l in block[4].split("\n") if l.strip()]
            for line in lines:
                l_up = line.upper()
                if any(kw in l_up for kw in ("PLAN", "SCHEDULE", "ELEVATION", "SECTION", "DETAILS", "COVER", "INDEX", "SPECIFICATION")):
                    if len(line) < 60 and not re.match(r"^\d+$", line):
                        title_candidates.append(line)
        if title_candidates:
            sheet_title = title_candidates[0]

        # Sheet number rule signal
        if sheet_num.startswith("A0."):
            evidence_notes.append("sheet_family: A0_general_code_safety")
            if res.page_type not in (PageType.PARTITION_PLAN, PageType.FLOOR_PLAN):
                exclusion_notes.append("sheet_number_prefix_A0_non_takeoff")
        elif sheet_num.startswith("A1."):
            evidence_notes.append("sheet_family: A1_floor_plans")
        elif sheet_num.startswith("A2."):
            evidence_notes.append("sheet_family: A2_partition_plans")
        elif sheet_num.startswith("A3."):
            evidence_notes.append("sheet_family: A3_elevations_rcp")
        elif sheet_num.startswith("A4.") or sheet_num.startswith("A5."):
            evidence_notes.append("sheet_family: A4_A5_sections_finishes")
        elif sheet_num.startswith("A7.") or sheet_num.startswith("A6."):
            evidence_notes.append("sheet_family: A6_A7_schedules_details")

        scale_str = "1/4\" = 1'-0\""
        scale_m = re.search(r"(\d+/\d+\"\s*=\s*\d+['-]\d*\"|\d+\"\s*=\s*\d+['-]\d*\")", " ".join(text_tokens))
        if scale_m:
            scale_str = scale_m.group(1)
            evidence_notes.append(f"scale_annotation: {scale_str}")

        disc = res.discipline.upper()
        is_eligible = res.is_takeoff_eligible
        skip_rsn = res.skip_reason

        # Prefix-based discipline authority
        if re.match(r"^E\d", sheet_num):
            disc = "ELECTRICAL"
            is_eligible = False
            skip_rsn = "Electrical sheet — excluded from architectural drywall takeoff"
        elif re.match(r"^M\d", sheet_num):
            disc = "MECHANICAL"
            is_eligible = False
            skip_rsn = "Mechanical sheet — excluded from architectural drywall takeoff"
        elif re.match(r"^P\d{2,}", sheet_num):
            disc = "PLUMBING"
            is_eligible = False
            skip_rsn = "Plumbing sheet — excluded from architectural drywall takeoff"
        elif re.match(r"^S\d", sheet_num):
            disc = "STRUCTURAL"
            is_eligible = False
            skip_rsn = "Structural sheet — excluded from architectural drywall takeoff"
        elif re.match(r"^C\d", sheet_num):
            disc = "CIVIL"
            is_eligible = False
            skip_rsn = "Civil sheet — excluded from architectural drywall takeoff"
        elif re.match(r"^FP\d", sheet_num):
            disc = "FIRE_PROTECTION"
            is_eligible = False
            skip_rsn = "Fire protection sheet — excluded from architectural drywall takeoff"
        elif re.match(r"^A\d", sheet_num) or re.match(r"^AD\d", sheet_num):
            disc = "ARCHITECTURAL"

        candidate_trades = []
        is_partition_eligible = is_eligible and (res.geometry_authority == "PARTITION_WALLS")
        if is_partition_eligible:
            candidate_trades.extend(["DRYWALL", "PAINTING", "FLOORING"])
        elif res.geometry_authority == "FINISH_SCOPE":
            candidate_trades.extend(["PAINTING", "FLOORING"])
        elif res.geometry_authority == "CEILING_GWB":
            candidate_trades.append("DRYWALL")
        elif res.page_type == PageType.ROOF_PLAN:
            candidate_trades.append("ROOFING")

        type_str = res.page_type.value.upper()
        if res.geometry_authority == "CONTEXT_ONLY":
            type_str = "LIFE_SAFETY_EGRESS_PLAN"
        elif res.geometry_authority == "DEMOLITION":
            type_str = "DEMOLITION_PLAN"
        elif res.geometry_authority == "FINISH_SCOPE":
            type_str = "FINISH_PLAN"

        # Semantic drawing regions inferred dynamically
        drawing_regions = [
            {"region_type": "DRAWING_ZONE", "bbox_norm": res.drawing_zone_bbox, "takeoff_allowed": res.is_takeoff_eligible},
            {"region_type": "TITLE_BLOCK", "bbox_norm": {"minX": 0.88, "minY": 0.0, "maxX": 1.0, "maxY": 1.0}, "takeoff_allowed": False},
        ]
        if "GENERAL_NOTES" in res.secondary_content or "KEYNOTES" in res.secondary_content:
            drawing_regions.append({"region_type": "NOTES", "bbox_norm": {"minX": 0.0, "minY": 0.75, "maxX": 0.40, "maxY": 1.0}, "takeoff_allowed": False})
        if "OCCUPANCY_SUMMARY" in res.secondary_content or "EGRESS_WIDTH_SUMMARY" in res.secondary_content:
            drawing_regions.append({"region_type": "SCHEDULE", "bbox_norm": {"minX": 0.65, "minY": 0.70, "maxX": 0.88, "maxY": 0.95}, "takeoff_allowed": False})
        if "HARDSCAPE" in res.secondary_content:
            drawing_regions.append({"region_type": "SITE_HARDSCAPE", "bbox_norm": {"minX": 0.05, "minY": 0.05, "maxX": 0.50, "maxY": 0.50}, "takeoff_allowed": False})

        return PageEvidence(
            page_number=page_number,
            sheet_number=sheet_num,
            sheet_title=sheet_title,
            discipline=disc,
            page_type=type_str,
            confidence=res.confidence,
            takeoff_eligible=is_eligible,
            scale=scale_str,
            candidate_trades=candidate_trades,
            contains={
                "walls": is_partition_eligible,
                "doors": is_partition_eligible,
                "windows": is_partition_eligible,
                "rooms": is_partition_eligible,
                "dimensions": True,
                "grids": True,
                "details": "DETAIL" in res.primary_title,
                "schedules": res.schedule_authority is not None,
                "elevations": res.page_type == PageType.ELEVATION,
                "sections": res.page_type == PageType.SECTION,
                "notes": True,
            },
            drawing_regions=drawing_regions,
            source_regions=drawing_regions,
            classification_evidence=evidence_notes,
            exclusion_evidence=exclusion_notes,
            skip_reason=skip_rsn,
        )
    except Exception as exc:
        return PageEvidence(
            page_number=page_number,
            sheet_number=f"P{page_number}",
            sheet_title="ERROR_READING_PAGE",
            discipline="GENERAL",
            page_type="UNKNOWN",
            confidence=0.0,
            takeoff_eligible=False,
            classification_evidence=[str(exc)],
            exclusion_evidence=[f"error: {exc}"],
            skip_reason=str(exc),
        )
