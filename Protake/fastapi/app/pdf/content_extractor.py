"""Native PDF Content Extractor.
Extracts and semantically classifies text, titles, room labels, roof labels,
notes, dimensions, scale labels, and slope annotations directly from PDF content streams.
Preserves exact PDF coordinates, bounding boxes, font metadata, and full provenance.
Implements text layout policies, duplicate text grouping, and visual priority ranking.
"""
from __future__ import annotations

import hashlib
import re
from typing import Optional
import fitz  # PyMuPDF

from app.bim.models import DataProvenanceStatus
from app.pdf.models import (
    DrawingTextObject,
    SemanticContentType,
    SemanticTextRole,
)


# Architectural Regex Patterns
_SLOPE_PATTERNS = [
    re.compile(r"SLOPE\s*(\d{1,2})\s*:\s*(\d{1,2})", re.IGNORECASE),
    re.compile(r"PITCH\s*(\d{1,2})\s*[:/]\s*(\d{1,2})", re.IGNORECASE),
    re.compile(r"(\d{1,2})\s*:\s*(\d{1,2})\s*SLOPE", re.IGNORECASE),
    re.compile(r"(\d{1,2})\s*:\s*(\d{1,2})\s*PITCH", re.IGNORECASE),
    re.compile(r"(\d+(?:\.\d+)?)\s*%\s*SLOPE", re.IGNORECASE),
    re.compile(r"SLOPE\s*(\d+(?:\.\d+)?)\s*%", re.IGNORECASE),
    re.compile(r"(\d+(?:\.\d+)?)\s*\"\s*(?:PER|/)\s*(?:FT|FOOT|12\")", re.IGNORECASE),
]

_SCALE_PATTERNS = [
    re.compile(r"(?:SCALE|SC)\s*[:.]?\s*(\d+)\s*:\s*(\d+)", re.IGNORECASE),
    re.compile(r"(?:SCALE|SC)\s*[:.]?\s*(\d+/\d+|\d+)\s*\"\s*=\s*(\d+)(?:'-0\"|'|\s*FT)", re.IGNORECASE),
    re.compile(r"^(\d+)\s*:\s*(\d+)$"),
]

_DIMENSION_PATTERNS = [
    # Millimeters: e.g. "17652 mm", "10176mm"
    re.compile(r"(\d+(?:\.\d+)?)\s*mm\b", re.IGNORECASE),
    # Feet and inches: e.g. 24'-0", 12'-6 1/2", 8' - 4"
    re.compile(r"(\d{1,3})'\s*-\s*(\d{1,2}(?:\s+\d/\d)?)\""),
    re.compile(r"(\d{1,3})'\s*(\d{1,2})\""),
]

_ROOF_LABEL_PATTERNS = [
    re.compile(r"\b(?:UPPER\s+ROOF|LOWER\s+ROOF|MAIN\s+ROOF|HIGH\s+ROOF|LOW\s+ROOF)\b", re.IGNORECASE),
    re.compile(r"\b(?:RIDGE|EAVE|VALLEY|HIP|RAKE|GABLE|PARAPET)\b", re.IGNORECASE),
    re.compile(r"\bLINE\s+OF\s+(?:UPPER|LOWER)\s+ROOF\b", re.IGNORECASE),
]

_DRAWING_TITLE_PATTERNS = [
    re.compile(r"\b(?:PROPOSED\s+)?ROOF\s+PLAN\b", re.IGNORECASE),
    re.compile(r"\bROOF\s+(?:FRAMING|DRAINAGE)\s+PLAN\b", re.IGNORECASE),
    re.compile(r"\bFLOOR\s+PLAN\b", re.IGNORECASE),
    re.compile(r"\bREFLECTED\s+CEILING\s+PLAN\b", re.IGNORECASE),
]

_MATERIAL_PATTERNS = [
    re.compile(r"\b(?:METAL\s+ROOF|STANDING\s+SEAM|PREFINISHED\s+METAL|ASPHALT\s+SHINGLE|TPO|EPDM|MEMBRANE|TERRAZZO)\b", re.IGNORECASE),
    re.compile(r"\b(?:COPPER\s+DOWN\s*PIPE|ROOF\s+PANEL)\b", re.IGNORECASE),
]


class PDFContentExtractor:
    """Extracts and semantically classifies native text from PDF pages with full provenance and overlap handling."""

    def extract_page_content(self, page: fitz.Page, page_number: int) -> list[DrawingTextObject]:
        """Extracts all text elements from a PDF page with exact coordinates, priority ranking, and provenance."""
        text_objects: list[DrawingTextObject] = []
        text_dict = page.get_text("dict")
        blocks = text_dict.get("blocks", [])

        obj_counter = 1

        for b_idx, block in enumerate(blocks):
            if block.get("type") != 0:
                continue

            for l_idx, line in enumerate(block.get("lines", [])):
                for s_idx, span in enumerate(line.get("spans", [])):
                    raw_text = span.get("text", "").strip()
                    if not raw_text:
                        continue

                    bbox = [float(x) for x in span.get("bbox", [0, 0, 0, 0])]
                    origin = [float(x) for x in span.get("origin", [bbox[0], bbox[1]])]
                    font_name = span.get("font")
                    font_size = float(span.get("size", 0.0))
                    color_int = span.get("color", 0)

                    # Extract RGB color components & hex
                    r = (color_int >> 16) & 255
                    g = (color_int >> 8) & 255
                    b = color_int & 255
                    color_rgb = (r, g, b)
                    color_hex = f"#{r:02x}{g:02x}{b:02x}"

                    # Classify semantic content type & architectural semantic role
                    semantic_type = self.classify_text_semantic(raw_text)
                    semantic_role = self.classify_text_role(raw_text, semantic_type)

                    # Assign visual display priority according to Section 3 priority ladder
                    display_priority = self.get_display_priority(semantic_role)

                    obj_id = f"TXT-P{page_number:02d}-{obj_counter:05d}"
                    obj_counter += 1

                    # Cryptographic source hash for tamper-proof provenance
                    hash_str = f"P{page_number}:{bbox}:{origin}:{font_name}:{font_size}:{raw_text}"
                    src_hash = hashlib.sha256(hash_str.encode("utf-8")).hexdigest()

                    # Map architectural layer for text
                    layer_name = self.map_text_layer(semantic_role)

                    w = round(abs(bbox[2] - bbox[0]), 2)
                    h = round(abs(bbox[3] - bbox[1]), 2)

                    text_objects.append(
                        DrawingTextObject(
                            id=obj_id,
                            text_id=obj_id,
                            source_text_id=obj_id,
                            page=page_number,
                            page_number=page_number,
                            text=raw_text,
                            content=raw_text,
                            semantic_type=semantic_type,
                            semantic_role=semantic_role,
                            bbox_pdf=bbox,
                            bbox=bbox,
                            origin_pdf=origin,
                            x=round(origin[0], 2),
                            y=round(origin[1], 2),
                            width=w,
                            height=h,
                            font=font_name,
                            font_name=font_name,
                            font_size=font_size,
                            rotation=float(span.get("flags", 0)),
                            rotation_deg=float(span.get("flags", 0)),
                            color=color_hex,
                            color_rgb=color_rgb,
                            layer=layer_name,
                            confidence=1.0,
                            provenance=DataProvenanceStatus.VERIFIED_EXPLICIT,
                            source="PDF_NATIVE_TEXT",
                            source_hash=src_hash,
                            display_priority=display_priority,
                            is_duplicate=False,
                            is_suppressed_in_clean_mode=False,
                        )
                    )

        # 1. Merge adjacent word fragments (e.g. "SLOPE" and "2: 12" or "17652" and "mm")
        merged_objects = self._merge_compound_tokens(text_objects, page_number)

        # 2. Detect, group, and flag overlapping/duplicate text (AutoCAD bolding/shadowing)
        deduped_objects = self._detect_and_group_duplicates(merged_objects)

        return deduped_objects

    def get_display_priority(self, role: SemanticTextRole) -> int:
        """Visual display priority ladder per Section 3 specification:
        TAKEOFF LABEL (100) > DIMENSION (90) > ROOM LABEL (80) > TRADE/WALL/MATERIAL NOTE (70)
        > SECTION/DETAIL LABEL (60) > GENERAL NOTE (50) > TITLE BLOCK (40) > ANNOTATION (30) > UNKNOWN (10)
        """
        priority_map: dict[SemanticTextRole, int] = {
            SemanticTextRole.DIMENSION_TEXT: 90,
            SemanticTextRole.ROOM_LABEL: 80,
            SemanticTextRole.ROOF_LABEL: 80,
            SemanticTextRole.WALL_NOTE: 70,
            SemanticTextRole.MATERIAL_NOTE: 70,
            SemanticTextRole.TRADE_NOTE: 70,
            SemanticTextRole.MATERIAL_LABEL: 70,
            SemanticTextRole.SECTION_LABEL: 60,
            SemanticTextRole.DETAIL_LABEL: 60,
            SemanticTextRole.DETAIL_CALLOUT: 60,
            SemanticTextRole.ELEVATION_LABEL: 60,
            SemanticTextRole.GENERAL_NOTE: 50,
            SemanticTextRole.NOTE: 50,
            SemanticTextRole.PLUMBING_NOTE: 50,
            SemanticTextRole.DRAWING_TITLE: 40,
            SemanticTextRole.SHEET_NUMBER: 40,
            SemanticTextRole.SCALE_TEXT: 40,
            SemanticTextRole.SCALE_LABEL: 40,
            SemanticTextRole.TITLE_BLOCK_TEXT: 40,
            SemanticTextRole.TITLE_BLOCK: 40,
            SemanticTextRole.GRID_LABEL: 30,
            SemanticTextRole.LEVEL_LABEL: 30,
            SemanticTextRole.ANNOTATION: 30,
            SemanticTextRole.GENERAL_ANNOTATION: 30,
            SemanticTextRole.GENERAL_TEXT: 30,
            SemanticTextRole.LEGEND_TEXT: 25,
            SemanticTextRole.UNKNOWN: 10,
            SemanticTextRole.UNKNOWN_TEXT: 10,
        }
        return priority_map.get(role, 30)

    def map_text_layer(self, role: SemanticTextRole) -> str:
        """Assigns appropriate display layer for filtering and visual rendering."""
        if role in (SemanticTextRole.TITLE_BLOCK, SemanticTextRole.TITLE_BLOCK_TEXT, SemanticTextRole.DRAWING_TITLE, SemanticTextRole.SHEET_NUMBER, SemanticTextRole.SCALE_TEXT, SemanticTextRole.SCALE_LABEL):
            return "Title Block"
        elif role == SemanticTextRole.DIMENSION_TEXT:
            return "Dimensions"
        elif role == SemanticTextRole.GRID_LABEL:
            return "Grid"
        elif role == SemanticTextRole.LEGEND_TEXT:
            return "Legend"
        elif role in (SemanticTextRole.DETAIL_LABEL, SemanticTextRole.DETAIL_CALLOUT):
            return "Details"
        elif role in (SemanticTextRole.GENERAL_NOTE, SemanticTextRole.NOTE, SemanticTextRole.PLUMBING_NOTE, SemanticTextRole.ANNOTATION, SemanticTextRole.GENERAL_ANNOTATION, SemanticTextRole.WALL_NOTE, SemanticTextRole.TRADE_NOTE):
            return "Annotations"
        elif role in (SemanticTextRole.ROOM_LABEL, SemanticTextRole.ROOF_LABEL, SemanticTextRole.MATERIAL_LABEL, SemanticTextRole.MATERIAL_NOTE):
            return "Rooms"
        return "Text"

    def classify_text_role(self, text: str, semantic_type: SemanticContentType) -> SemanticTextRole:
        """Determines the detailed architectural role for text, strictly mapping all 16 user roles."""
        clean = text.strip()
        clean_upper = clean.upper()

        # 1. Sheet number (e.g. SHEET # 22, SHEET # 04, A2.1, S1.0, ARCH-101, A-101)
        if "SHEET" in clean_upper or re.match(r"^[A-Z]{1,4}\s*[-.]?\s*\d+(?:\.\d+)?$", clean):
            return SemanticTextRole.SHEET_NUMBER

        # 2. Scale Text / Label (e.g. SCALE: 1/8" = 1'-0", 1:50)
        if "SCALE" in clean_upper or re.match(r"^\d+/\d+\"\s*[:=]\s*\d+", clean) or re.match(r"^1\s*:\s*\d+$", clean):
            return SemanticTextRole.SCALE_TEXT

        # 3. Title Block Metadata
        title_block_kws = ["CLIENT:", "PROJECT:", "DRAWN BY:", "PROPOSED DESIGN", "PLOT NO.", "M . P . C. H", "TITLE:", "DATE:", "CHECKED BY:"]
        if any(kw in clean_upper for kw in title_block_kws):
            return SemanticTextRole.TITLE_BLOCK_TEXT

        # 4. Drawing Title
        if any(kw in clean_upper for kw in [
            "WORKING PLAN", "FURNITURE) PLAN", "FOUNDATION) PLAN", "ROOF (WORKING) PLAN",
            "FRONT ELEVATION", "REAR ELEVATION", "SECTION AT", "PLUMBING DRAWINGS",
            "PLUMBING & SANITARY", "LAYOUT PLAN", "FLOOR PLAN", "ROOF PLAN"
        ]):
            return SemanticTextRole.DRAWING_TITLE

        # 5. Section Label
        if clean_upper.startswith("SECTION") or "SEC." in clean_upper or clean_upper.startswith("CROSS SECTION") or clean_upper.startswith("LONGITUDINAL SECTION"):
            return SemanticTextRole.SECTION_LABEL

        # 6. Detail Label / Callout
        if clean_upper.startswith("DETAIL") or "ENLARGED" in clean_upper or "SEC. OF VANITY" in clean_upper or "JOINERY DETAIL" in clean_upper or "TYPICAL DETAIL" in clean_upper:
            return SemanticTextRole.DETAIL_LABEL

        # 7. Elevation Label
        if "ELEVATION" in clean_upper and not any(k in clean_upper for k in ["LEVEL", "DATUM"]):
            return SemanticTextRole.ELEVATION_LABEL

        # 8. Level label (e.g. +2'-6", +13'-0", +23'-6", +34'-0", ±0'-0")
        if re.match(r"^[+±\-]\d+['\-]", clean):
            return SemanticTextRole.LEVEL_LABEL

        # 9. Legend entries & headers
        legend_terms = [
            "LEGEND", "WATER CLOSET", "WASH HAND BASIN", "COLD WATER SUPPLY", "HOT WATER SUPPLY",
            "GULLY TRAP", "WATER TAP", "SHOWER", "GEYSER", "UNDER GROUND WATER TANK",
            "OVER HEAD TANK", "FLOOR TRAP", "INTERNAL SEWER LINE", "MAIN HOLE",
            "S.NO", "DESCRIPTION", "SYMBOL", "F.T", "W.H.B", "G.T", "M.H", "C.W.S", "H. W. S"
        ]
        if any(lt == clean_upper or f"[{lt}]" in clean_upper for lt in legend_terms):
            return SemanticTextRole.LEGEND_TEXT

        # 10. Wall Notes
        if any(kw in clean_upper for kw in [
            "BRICK WALL", "PARTITION WALL", "CAVITY WALL", "MASONRY WALL", "WALL CAVITY",
            "GYPSUM BOARD", "DRYWALL", "WALL FINISH", "DPC", "D.P.C"
        ]):
            return SemanticTextRole.WALL_NOTE

        # 11. Material Notes
        if any(kw in clean_upper for kw in [
            "THICK RCC", "R.C.C SLAB", "BRICK IN C.M", "CEMENT PLASTER", "MARBLE FLOOR",
            "PORCELAIN TILE", "CERAMIC TILE", "WOODEN FLOOR", "VIN BOARD", "TERRAZZO", "MEMBRANE"
        ]):
            return SemanticTextRole.MATERIAL_NOTE

        # 12. Trade Notes (Plumbing / Mechanical / Electrical specifications)
        if any(kw in clean_upper for kw in [
            "TEES & BENDS", "PIPE SHOULD", "SLOPE OF SOIL", "CAST IRON PIPE", "SEWER LINE",
            "DRAIN PIPE", "COPPER PIPE", "P-TRAP", "VENT PIPE", "G.I. PIPE", "PVC PIPE"
        ]):
            return SemanticTextRole.TRADE_NOTE

        # 13. General Notes (numbered specifications, disclaimers)
        note_triggers = [
            "GENERAL NOTE", "ALL DIMENSIONS", "CONTRACTOR SHALL", "VERIFY ALL", "DO NOT SCALE",
            "GROUND INFORMATION", "ACCORDING TO PROFILE", "LOCAL CONDITIONS", "MINOR ADJUSTMENT"
        ]
        if any(nt in clean_upper for nt in note_triggers) or re.match(r"^\d+\.\s*", clean):
            return SemanticTextRole.GENERAL_NOTE

        # 14. Room Labels
        room_keywords = [
            "BED ROOM", "BEDROOM", "MASTER BED", "BATH", "DRESS", "KITCHEN", "STAIR HALL",
            "T.V LOUNGE", "TV LOUNGE", "LOUNGE", "DRAWING", "DRAWING ROOM", "LIVING ROOM",
            "DINING", "COV.TERRACE", "COV. TERRACE", "TERRACE", "FRONT LAWN", "REAR LAWN", "LAWN",
            "CAR PORCH", "MAIN GATE", "GATE", "STORE", "MUMTY", "O.H.W TANK", "POWDER ROOM",
            "FOYER", "CORRIDOR", "BALCONY", "UTILITY", "LOBBY", "STUDY"
        ]
        if any(kw == clean_upper or f" {kw} " in f" {clean_upper} " for kw in room_keywords):
            return SemanticTextRole.ROOM_LABEL

        # 15. Pure Dimension text (isolated measurement notation)
        is_isolated_dim = bool(
            re.match(r"^\d+['\"]\s*x\s*\d+['\"]$", clean) or
            re.match(r"^\d+'\s*-\s*\d+(?:\s+\d/\d)?\"?$", clean) or
            re.match(r"^\d+'\s*\d+(?:\s+\d/\d)?\"?$", clean) or
            re.match(r"^\d+'$", clean) or
            re.match(r"^\d+(?:\s+\d/\d)?\"$", clean) or
            re.match(r"^\d/\d\"$", clean) or
            re.match(r"^\d+(?:\.\d+)?\s*mm$", clean, re.IGNORECASE)
        )
        if is_isolated_dim:
            return SemanticTextRole.DIMENSION_TEXT

        # 16. Grid bubble labels
        if re.match(r"^[A-Z]$|^[1-9]\d?$", clean):
            return SemanticTextRole.GRID_LABEL

        # Fallbacks based on semantic_type
        if semantic_type == SemanticContentType.DRAWING_TITLE:
            return SemanticTextRole.DRAWING_TITLE
        elif semantic_type == SemanticContentType.SCALE_LABEL:
            return SemanticTextRole.SCALE_TEXT
        elif semantic_type == SemanticContentType.DIMENSION_TEXT:
            return SemanticTextRole.DIMENSION_TEXT
        elif semantic_type == SemanticContentType.ROOF_LABEL:
            return SemanticTextRole.ROOF_LABEL
        elif semantic_type == SemanticContentType.ROOM_LABEL:
            return SemanticTextRole.ROOM_LABEL
        elif semantic_type == SemanticContentType.MATERIAL_ANNOTATION:
            return SemanticTextRole.MATERIAL_NOTE
        elif semantic_type == SemanticContentType.NOTES:
            return SemanticTextRole.GENERAL_NOTE

        return SemanticTextRole.ANNOTATION

    def classify_text_semantic(self, text: str) -> SemanticContentType:
        """Determines the semantic category of extracted text using strict regexes."""
        clean = text.strip()

        # 1. Slope / Pitch
        for pat in _SLOPE_PATTERNS:
            if pat.search(clean):
                return SemanticContentType.SLOPE_ANNOTATION

        # 2. Scale
        for pat in _SCALE_PATTERNS:
            if pat.search(clean):
                return SemanticContentType.SCALE_LABEL

        # 3. Dimension
        for pat in _DIMENSION_PATTERNS:
            if pat.search(clean):
                return SemanticContentType.DIMENSION_TEXT

        # 4. Drawing Title
        for pat in _DRAWING_TITLE_PATTERNS:
            if pat.search(clean):
                return SemanticContentType.DRAWING_TITLE

        # 5. Roof Specific Label
        for pat in _ROOF_LABEL_PATTERNS:
            if pat.search(clean):
                return SemanticContentType.ROOF_LABEL

        # 6. Material
        for pat in _MATERIAL_PATTERNS:
            if pat.search(clean):
                return SemanticContentType.MATERIAL_ANNOTATION

        return SemanticContentType.GENERAL_TEXT

    def _merge_compound_tokens(
        self, tokens: list[DrawingTextObject], page_number: int
    ) -> list[DrawingTextObject]:
        """Merges adjacent split tokens such as ['17652', 'mm'] or ['SLOPE', '2: 12'] or ['BED', 'ROOM']."""
        if not tokens:
            return []

        merged: list[DrawingTextObject] = []
        skip_indices = set()

        for i in range(len(tokens)):
            if i in skip_indices:
                continue

            curr = tokens[i]

            if i + 1 < len(tokens):
                nxt = tokens[i + 1]
                same_y = abs(curr.origin_pdf[1] - nxt.origin_pdf[1]) < 3.0
                proximity = 0 <= (nxt.bbox_pdf[0] - curr.bbox_pdf[2]) < 30.0

                # 1. Dimension number + "mm"
                if curr.text.replace(".", "").isdigit() and nxt.text.lower() == "mm" and same_y and proximity:
                    combined_text = f"{curr.text} mm"
                    combined_bbox = [
                        min(curr.bbox_pdf[0], nxt.bbox_pdf[0]),
                        min(curr.bbox_pdf[1], nxt.bbox_pdf[1]),
                        max(curr.bbox_pdf[2], nxt.bbox_pdf[2]),
                        max(curr.bbox_pdf[3], nxt.bbox_pdf[3]),
                    ]
                    merged.append(
                        curr.model_copy(
                            update={
                                "text": combined_text,
                                "content": combined_text,
                                "semantic_type": SemanticContentType.DIMENSION_TEXT,
                                "semantic_role": SemanticTextRole.DIMENSION_TEXT,
                                "bbox_pdf": combined_bbox,
                                "bbox": combined_bbox,
                                "width": round(abs(combined_bbox[2] - combined_bbox[0]), 2),
                                "height": round(abs(combined_bbox[3] - combined_bbox[1]), 2),
                                "display_priority": 90,
                            }
                        )
                    )
                    skip_indices.add(i + 1)
                    continue

                # 2. "SLOPE" + ratio (e.g. "2: 12" or "2:12")
                if curr.text.upper() == "SLOPE" and same_y and proximity:
                    combined_text = f"SLOPE {nxt.text}"
                    combined_bbox = [
                        min(curr.bbox_pdf[0], nxt.bbox_pdf[0]),
                        min(curr.bbox_pdf[1], nxt.bbox_pdf[1]),
                        max(curr.bbox_pdf[2], nxt.bbox_pdf[2]),
                        max(curr.bbox_pdf[3], nxt.bbox_pdf[3]),
                    ]
                    merged.append(
                        curr.model_copy(
                            update={
                                "text": combined_text,
                                "content": combined_text,
                                "semantic_type": SemanticContentType.SLOPE_ANNOTATION,
                                "bbox_pdf": combined_bbox,
                                "bbox": combined_bbox,
                                "width": round(abs(combined_bbox[2] - combined_bbox[0]), 2),
                                "height": round(abs(combined_bbox[3] - combined_bbox[1]), 2),
                            }
                        )
                    )
                    skip_indices.add(i + 1)
                    continue

                # 3. "BED" + "ROOM" or "T.V" + "LOUNGE"
                if (curr.text.upper() in ("BED", "T.V", "TV", "DRAWING") and nxt.text.upper() in ("ROOM", "LOUNGE")) and same_y and proximity:
                    combined_text = f"{curr.text} {nxt.text}"
                    combined_bbox = [
                        min(curr.bbox_pdf[0], nxt.bbox_pdf[0]),
                        min(curr.bbox_pdf[1], nxt.bbox_pdf[1]),
                        max(curr.bbox_pdf[2], nxt.bbox_pdf[2]),
                        max(curr.bbox_pdf[3], nxt.bbox_pdf[3]),
                    ]
                    merged.append(
                        curr.model_copy(
                            update={
                                "text": combined_text,
                                "content": combined_text,
                                "semantic_type": SemanticContentType.ROOM_LABEL,
                                "semantic_role": SemanticTextRole.ROOM_LABEL,
                                "bbox_pdf": combined_bbox,
                                "bbox": combined_bbox,
                                "width": round(abs(combined_bbox[2] - combined_bbox[0]), 2),
                                "height": round(abs(combined_bbox[3] - combined_bbox[1]), 2),
                                "display_priority": 80,
                            }
                        )
                    )
                    skip_indices.add(i + 1)
                    continue

            merged.append(curr)

        return merged

    def _detect_and_group_duplicates(
        self, text_objects: list[DrawingTextObject]
    ) -> list[DrawingTextObject]:
        """Detects overlapping/duplicate text objects (e.g. AutoCAD faux-bold offset <= 1.0 pt),
        groups them, and marks redundant instances for suppression in clean display mode.
        Preserves original PDF data completely.
        """
        if not text_objects:
            return []

        group_counter = 1
        processed_objects: list[DrawingTextObject] = []
        seen_clusters: list[tuple[str, list[float], str]] = []  # (text, bbox, group_id)

        for obj in text_objects:
            b = obj.bbox_pdf
            t_clean = obj.text.strip()
            if not b or len(b) < 4 or not t_clean:
                processed_objects.append(obj)
                continue

            matched_group: Optional[str] = None
            is_dup = False

            for prev_text, prev_bbox, prev_group in seen_clusters:
                # Same text string and coordinates within 1.2 pt
                if (
                    prev_text == t_clean
                    and abs(b[0] - prev_bbox[0]) <= 1.2
                    and abs(b[1] - prev_bbox[1]) <= 1.2
                    and abs(b[2] - prev_bbox[2]) <= 1.2
                    and abs(b[3] - prev_bbox[3]) <= 1.2
                ):
                    matched_group = prev_group
                    is_dup = True
                    break

            if is_dup and matched_group:
                # Mark as duplicate and suppress in clean mode
                updated_obj = obj.model_copy(
                    update={
                        "is_duplicate": True,
                        "overlap_group_id": matched_group,
                        "is_suppressed_in_clean_mode": True,
                    }
                )
                processed_objects.append(updated_obj)
            else:
                new_group_id = f"GRP-P{obj.page_number:02d}-{group_counter:04d}"
                group_counter += 1
                seen_clusters.append((t_clean, b, new_group_id))
                updated_obj = obj.model_copy(
                    update={
                        "is_duplicate": False,
                        "overlap_group_id": new_group_id,
                        "is_suppressed_in_clean_mode": False,
                    }
                )
                processed_objects.append(updated_obj)

        return processed_objects
