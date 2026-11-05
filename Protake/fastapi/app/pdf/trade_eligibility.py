"""Central Deterministic Trade Eligibility Matrix.
Defines authoritative, trade-aware QTO rules across architectural and engineering sheets.
Governs which objects and sheets enter drywall, flooring, roofing, and plumbing takeoff.
"""
from __future__ import annotations

from typing import Any
from app.pdf.models import DrawingObjectType, DrawingType


class TradeEligibilityMatrix:
    """Central deterministic Trade Eligibility Matrix governing QTO scope.
    
    Object                 DRYWALL   FLOORING   ROOFING   PLUMBING
    ----------------------------------------------------------------
    Drywall Partition       YES        NO         NO         NO
    Masonry Wall            REVIEW     NO         NO         NO
    Room Floor              NO         YES        NO         NO
    Roof Plane              NO         NO         YES        NO
    Door                    DEDUCT     NO         NO         NO
    Window                  DEDUCT     NO         NO         NO
    Section Line             NO         NO         NO         NO
    Dimension                SUPPORT    SUPPORT    SUPPORT    SUPPORT
    Room Label               NO         SUPPORT    NO         NO
    Text                     NO         NO         NO         NO
    Annotation               NO         NO         NO         NO
    Legend Symbol            NO         NO         NO         NO
    Detail Geometry          NO         NO         NO         NO
    Title Block              NO         NO         NO         NO
    """

    MATRIX: dict[str, dict[str, str]] = {
        "DRYWALL_PARTITION": {"DRYWALL": "YES", "FLOORING": "NO", "ROOFING": "NO", "PLUMBING": "NO"},
        "PARTITION_WALL": {"DRYWALL": "YES", "FLOORING": "NO", "ROOFING": "NO", "PLUMBING": "NO"},
        "MASONRY_WALL": {"DRYWALL": "REVIEW", "FLOORING": "NO", "ROOFING": "NO", "PLUMBING": "NO"},
        "PHYSICAL_WALL": {"DRYWALL": "REVIEW", "FLOORING": "NO", "ROOFING": "NO", "PLUMBING": "NO"},
        "CONCRETE_WALL": {"DRYWALL": "NO", "FLOORING": "NO", "ROOFING": "NO", "PLUMBING": "NO"},
        "ROOM_FLOOR": {"DRYWALL": "NO", "FLOORING": "YES", "ROOFING": "NO", "PLUMBING": "NO"},
        "ROOM": {"DRYWALL": "NO", "FLOORING": "YES", "ROOFING": "NO", "PLUMBING": "NO"},
        "ROOF_PLANE": {"DRYWALL": "NO", "FLOORING": "NO", "ROOFING": "YES", "PLUMBING": "NO"},
        "ROOF": {"DRYWALL": "NO", "FLOORING": "NO", "ROOFING": "YES", "PLUMBING": "NO"},
        "DOOR": {"DRYWALL": "DEDUCT", "FLOORING": "NO", "ROOFING": "NO", "PLUMBING": "NO"},
        "WINDOW": {"DRYWALL": "DEDUCT", "FLOORING": "NO", "ROOFING": "NO", "PLUMBING": "NO"},
        "SECTION_LINE": {"DRYWALL": "NO", "FLOORING": "NO", "ROOFING": "NO", "PLUMBING": "NO"},
        "SECTION_WALL_REPRESENTATION": {"DRYWALL": "NO", "FLOORING": "NO", "ROOFING": "NO", "PLUMBING": "NO"},
        "SECTION_LEVEL_LINE": {"DRYWALL": "NO", "FLOORING": "NO", "ROOFING": "NO", "PLUMBING": "NO"},
        "SECTION_STRUCTURAL_LINE": {"DRYWALL": "NO", "FLOORING": "NO", "ROOFING": "NO", "PLUMBING": "NO"},
        "SLAB": {"DRYWALL": "NO", "FLOORING": "NO", "ROOFING": "NO", "PLUMBING": "NO"},
        "DIMENSION": {"DRYWALL": "SUPPORT", "FLOORING": "SUPPORT", "ROOFING": "SUPPORT", "PLUMBING": "SUPPORT"},
        "ROOM_LABEL": {"DRYWALL": "NO", "FLOORING": "SUPPORT", "ROOFING": "NO", "PLUMBING": "NO"},
        "TEXT": {"DRYWALL": "NO", "FLOORING": "NO", "ROOFING": "NO", "PLUMBING": "NO"},
        "ANNOTATION": {"DRYWALL": "NO", "FLOORING": "NO", "ROOFING": "NO", "PLUMBING": "NO"},
        "LEGEND_SYMBOL": {"DRYWALL": "NO", "FLOORING": "NO", "ROOFING": "NO", "PLUMBING": "NO"},
        "DETAIL_GEOMETRY": {"DRYWALL": "NO", "FLOORING": "NO", "ROOFING": "NO", "PLUMBING": "NO"},
        "TITLE_BLOCK": {"DRYWALL": "NO", "FLOORING": "NO", "ROOFING": "NO", "PLUMBING": "NO"},
        "PLUMBING_FIXTURE": {"DRYWALL": "NO", "FLOORING": "NO", "ROOFING": "NO", "PLUMBING": "YES"},
        "SOIL_LINE": {"DRYWALL": "NO", "FLOORING": "NO", "ROOFING": "NO", "PLUMBING": "YES"},
        "WASTE_LINE": {"DRYWALL": "NO", "FLOORING": "NO", "ROOFING": "NO", "PLUMBING": "YES"},
        "VENT": {"DRYWALL": "NO", "FLOORING": "NO", "ROOFING": "NO", "PLUMBING": "YES"},
    }

    SHEET_TRADE_SCOPE: dict[DrawingType, dict[str, str]] = {
        DrawingType.SECTION: {
            "DRYWALL": "NOT_APPLICABLE — SECTION SHEET",
            "FLOORING": "NOT_APPLICABLE — SECTION SHEET",
            "ROOFING": "NOT_APPLICABLE — SECTION SHEET",
            "PLUMBING": "NOT_APPLICABLE — SECTION SHEET",
        },
        DrawingType.ELEVATION: {
            "DRYWALL": "NOT_APPLICABLE — ELEVATION SHEET",
            "FLOORING": "NOT_APPLICABLE — ELEVATION SHEET",
            "ROOFING": "NOT_APPLICABLE — ELEVATION SHEET",
            "PLUMBING": "NOT_APPLICABLE — ELEVATION SHEET",
        },
        DrawingType.DETAIL_DRAWING: {
            "DRYWALL": "NOT_APPLICABLE — DETAIL SHEET",
            "FLOORING": "NOT_APPLICABLE — DETAIL SHEET",
            "ROOFING": "NOT_APPLICABLE — DETAIL SHEET",
            "PLUMBING": "NOT_APPLICABLE — DETAIL SHEET",
        },
        DrawingType.PLUMBING_DRAWING: {
            "DRYWALL": "NOT_APPLICABLE — PLUMBING MEP SHEET",
            "FLOORING": "NOT_APPLICABLE — PLUMBING MEP SHEET",
            "ROOFING": "NOT_APPLICABLE — PLUMBING MEP SHEET",
            "PLUMBING": "NOT_IMPLEMENTED",
        },
        DrawingType.FOUNDATION_PLAN: {
            "DRYWALL": "NOT_APPLICABLE — FOUNDATION PLAN",
            "FLOORING": "NOT_APPLICABLE — FOUNDATION PLAN",
            "ROOFING": "NOT_APPLICABLE — FOUNDATION PLAN",
            "PLUMBING": "NOT_APPLICABLE — FOUNDATION PLAN",
        },
        DrawingType.FURNITURE_PLAN: {
            "DRYWALL": "NOT_APPLICABLE — PRESENTATION PLAN",
            "FLOORING": "NOT_APPLICABLE — PRESENTATION PLAN",
            "ROOFING": "NOT_APPLICABLE — PRESENTATION PLAN",
            "PLUMBING": "NOT_APPLICABLE — PRESENTATION PLAN",
        },
        DrawingType.FLOOR_PLAN: {
            "DRYWALL": "VERIFIED",
            "FLOORING": "VERIFIED",
            "ROOFING": "NOT_APPLICABLE — FLOOR PLAN SHEET",
            "PLUMBING": "NOT_IMPLEMENTED",
        },
        DrawingType.ROOF_PLAN: {
            "DRYWALL": "NOT_APPLICABLE — ROOF PLAN SHEET",
            "FLOORING": "NOT_APPLICABLE — ROOF PLAN SHEET",
            "ROOFING": "VERIFIED",
            "PLUMBING": "NOT_IMPLEMENTED",
        },
        DrawingType.OTHER: {
            "DRYWALL": "NOT_APPLICABLE",
            "FLOORING": "NOT_APPLICABLE",
            "ROOFING": "NOT_APPLICABLE",
            "PLUMBING": "NOT_IMPLEMENTED",
        },
    }

    @classmethod
    def evaluate_object(
        cls,
        drawing_type: DrawingType,
        object_type: DrawingObjectType | str,
        semantic_type: str = "UNKNOWN",
        is_legend: bool = False,
        is_detail: bool = False,
        is_notes: bool = False,
        is_title_block: bool = False,
    ) -> tuple[str, bool, str]:
        """Evaluates (trade_scope, qto_eligible, qto_reason) for a semantic drawing object.
        
        Returns:
            trade_scope: "DRYWALL" | "FLOORING" | "ROOFING" | "PLUMBING" | "SUPPORTING_EVIDENCE" | "NONE"
            qto_eligible: bool
            qto_reason: str
        """
        # 1. Non-QTO region constraints: Legend, General Notes, Title Block, Details
        if is_legend:
            return ("NONE", False, "Legend region symbol/text; excluded from project takeoff.")
        if is_title_block:
            return ("NONE", False, "Title block metadata; excluded from project geometry.")
        if is_notes:
            return ("NONE", False, "General specifications note; excluded from physical takeoff.")
        if is_detail:
            return ("NONE", False, "Enlarged detail linework; excluded from building finish takeoff.")

        obj_name = object_type.value if hasattr(object_type, "value") else str(object_type)
        sem_name = (semantic_type or "").upper()

        # 2. Section Drawing: All linework is non-QTO section geometry
        if drawing_type == DrawingType.SECTION:
            if "DIMENSION" in obj_name or "DIMENSION" in sem_name:
                return ("SUPPORTING_EVIDENCE", False, "Section dimension datum (supporting evidence).")
            if "LEVEL" in obj_name or "LEVEL" in sem_name:
                return ("SUPPORTING_EVIDENCE", False, "Section level marker (clear ceiling datum).")
            return ("NONE", False, "Section linework (structural cut representation; non-QTO sheet).")

        # 3. Elevation Drawing: Facade linework is vertical projection
        if drawing_type == DrawingType.ELEVATION:
            return ("NONE", False, "Elevation facade linework; excluded from finish takeoff.")

        # 4. Plumbing Drawing: MEP linework is out of current scope
        if drawing_type == DrawingType.PLUMBING_DRAWING:
            if "PLUMBING" in obj_name or "PIPE" in obj_name or "FIXTURE" in obj_name:
                return ("PLUMBING", False, "Plumbing trade linework (trade takeoff currently not implemented).")
            return ("NONE", False, "Plumbing MEP sheet linework.")

        # 5. Floor Plan: Trade-specific rules
        if drawing_type == DrawingType.FLOOR_PLAN:
            if obj_name in ("DRYWALL_PARTITION", "PARTITION_WALL") or sem_name == "DRYWALL_PARTITION":
                return ("DRYWALL", True, "Interior partition wall eligible for drywall finish.")
            if obj_name in ("MASONRY_WALL", "PHYSICAL_WALL", "WALL") or "WALL" in sem_name:
                return ("DRYWALL", True, "Masonry/perimeter wall eligible for drywall lining.")
            if obj_name in ("DOOR", "WINDOW"):
                return ("DRYWALL", False, "Opening deduction host (subtracts from gross wall area).")
            if obj_name in ("ROOM", "ROOM_FLOOR") or sem_name == "ROOM_FLOOR":
                return ("FLOORING", True, "Indoor room boundary eligible for flooring surface takeoff.")
            if obj_name == "DIMENSION":
                return ("SUPPORTING_EVIDENCE", False, "Floor plan dimension (supporting evidence).")
            if obj_name in ("ROOM_LABEL", "TEXT"):
                return ("SUPPORTING_EVIDENCE", False, "Room semantic label.")
            return ("NONE", False, "Non-finish floor plan linework.")

        # 6. Roof Plan: Roof planes
        if drawing_type == DrawingType.ROOF_PLAN:
            if obj_name in ("ROOF_PLANE", "ROOF") or sem_name == "ROOF_PLANE":
                return ("ROOFING", True, "Validated roof plane eligible for roofing membrane takeoff.")
            if obj_name in ("SLOPE_ARROW", "RIDGE", "VALLEY", "EAVE", "RAKE"):
                return ("ROOFING", False, "Roof geometric feature line.")
            if obj_name == "DIMENSION":
                return ("SUPPORTING_EVIDENCE", False, "Roof plan dimension.")
            return ("NONE", False, "Roof drafting linework.")

        return ("NONE", False, f"Linework on {drawing_type.value} drawing.")
