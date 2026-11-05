"""
qto/section_heights.py: Section Callout Tag Discovery & Height Verification Engine (Requirement R4).

Part of Milestone M3:
- Discovers circular section/detail callouts on floor plan sheets (e.g. A-706 / 09, A-702 / 01, A-801, A-802 / 4, A-907 / 2).
- Spatially associates wall runs with their nearest section callout (radius <= 120.0 pt).
- Navigates to referenced detail sheets and extracts explicit ceiling/wall height dimensions (+- 8'-0" CH, +- 7'-8" CH, +- 7'-3" CH).
- Falls back to 10.0 ft standard default height with estimator review flagging when unverified.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

import pymupdf as fitz

from qto.geometry import Point, Segment, point_to_segment_distance
from qto.dedup import WallRun
from qto.sheet_index import normalize_sheet_label


# ==============================================================================
# DATA STRUCTURES
# ==============================================================================

class CenterPoint(Point):
    """Point subclass providing both attribute (.x, .y) and sequence ([0], [1]) access."""

    def __getitem__(self, idx: int) -> float:
        return (self.x, self.y)[idx]


@dataclass
class SectionCallout:
    """Represents a discovered architectural section, elevation, or detail callout bubble."""
    raw_text: str
    sheet_ref: str              # Canonical sheet code (e.g. "A-706", "A-801")
    detail_num: Optional[str]   # Detail number (e.g. "09", "01", or None if sheet-wide)
    tag: str                    # Canonical callout tag (e.g. "A-706 / 09", "A-801")
    cx: float                   # Center X coordinate in page points
    cy: float                   # Center Y coordinate in page points
    bbox: Tuple[float, float, float, float]
    callout_type: str = "OTHER" # "ELEVATION", "SECTION", "PARTITION_DETAIL", "OTHER"
    page_num: int = 1

    @property
    def canonical_tag(self) -> str:
        return self.tag

    @property
    def callout_tag(self) -> str:
        return self.tag

    @property
    def center(self) -> CenterPoint:
        return CenterPoint(self.cx, self.cy)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "sheet_ref": self.sheet_ref,
            "detail_num": self.detail_num,
            "canonical_tag": self.tag,
            "tag": self.tag,
            "callout_type": self.callout_type,
            "bbox": list(self.bbox),
            "center": {"x": round(self.cx, 4), "y": round(self.cy, 4)},
            "page_num": self.page_num,
        }


# ==============================================================================
# REGEX PATTERNS & UTILITIES
# ==============================================================================

# Matches slash- or dash-separated detail and sheet references: e.g. "08/A-706", "A-706/08", "A-800/1"
SLASH_CALLOUT_PAT = re.compile(
    r"\b(?:(\d{1,2})\s*[\/\-]\s*(A-[2-9]\d{2})|(A-[2-9]\d{2})\s*[\/\-]\s*(\d{1,2}))\b",
    re.IGNORECASE,
)

# Matches standalone architectural sheet codes: e.g. "A-706", "A-801", "A-901"
SHEET_REF_PAT = re.compile(r"\b(A-[2-9]\d{2}(?:\.\d{1,2})?)\b", re.IGNORECASE)

# Matches isolated 1-2 digit detail numbers in multi-line callout bubbles
DETAIL_NUM_PAT = re.compile(r"^\s*(\d{1,2})\s*$")

# Negative keywords for general notes or title block sentences to prevent false positive callouts
GENERAL_NOTE_KEYWORDS = (
    "DRAWINGS", "SPECIFICATIONS", "GENERAL NOTES", "CONTRACTOR",
    "SHALL BE", "THIS SET OF", "TYPE ON SHEET", "SCALE:", "PROJECT:",
    "DATE:", "REVISION", "ARCHITECT", "ENGINEER"
)

# Explicit ceiling height pattern: e.g. "+- 8'-0" CH", "+- 7'-8" CH", "+- 7'-3" CH", "8'-0" CH"
CEILING_HEIGHT_PAT = re.compile(
    r"(?:[+\-±\s/]+)?(\d+)[\'′]\s*(?:[-–\s]\s*(\d+(?:\s*[\/½¼¾\d]+)?)\s*[\"″])?\s*CH\b",
    re.IGNORECASE,
)


def normalize_sheet_code(raw: str) -> str:
    """Normalizes sheet code string into canonical form (e.g. 'a 706' -> 'A-706')."""
    s = raw.strip().upper()
    m = re.match(r"^([A-Z]{1,2})[\s\-_]?(\d{3,4})$", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return s


def classify_callout_sheet(sheet_ref: str) -> str:
    """Distinguishes functional role of target detail sheet."""
    ref = sheet_ref.upper().strip()
    if ref.startswith("A-7"):
        return "ELEVATION"
    elif ref.startswith("A-8"):
        return "SECTION"
    elif ref.startswith("A-9"):
        return "PARTITION_DETAIL"
    return "OTHER"


def parse_ceiling_height(text: str) -> Optional[float]:
    """
    Parses architectural ceiling height dimension strings into decimal feet.
    Examples:
    - '+- 8\'-0" CH' -> 8.00
    - '+- 7\'-8" CH' -> 7.67
    - '+- 7\'-3" CH' -> 7.25
    - '8\'-0" CH' -> 8.00
    """
    if not text:
        return None
    m = CEILING_HEIGHT_PAT.search(text)
    if not m:
        return None

    ft = float(m.group(1))
    inch_str = m.group(2)
    inch = 0.0

    if inch_str:
        inch_str = inch_str.strip()
        if "1/2" in inch_str or "½" in inch_str:
            inch = float(inch_str.split()[0]) + 0.5 if " " in inch_str else 0.5
        elif "1/4" in inch_str or "¼" in inch_str:
            inch = float(inch_str.split()[0]) + 0.25 if " " in inch_str else 0.25
        elif "3/4" in inch_str or "¾" in inch_str:
            inch = float(inch_str.split()[0]) + 0.75 if " " in inch_str else 0.75
        else:
            try:
                inch = float(inch_str)
            except ValueError:
                inch = 0.0

    h = ft + (inch / 12.0)
    return round(h, 2)


# ==============================================================================
# DISCOVERY & HEIGHT EXTRACTION ENGINES
# ==============================================================================

def discover_section_callouts_on_page(
    page: fitz.Page,
    page_num: int = 1,
    current_sheet_label: str = "",
) -> List[SectionCallout]:
    """
    Parses vector and text blocks on a drawing page to discover section and
    detail callout bubbles (e.g. A-706 / 08, A-706 / 09, A-702 / 01, A-801, A-802 / 4, A-907 / 2).
    Uses dict/spans extraction with line lookahead/lookback to detect stacked callouts
    while filtering general note blocks and current sheet references.
    """
    d = page.get_text("dict")
    callouts: List[SectionCallout] = []
    curr_norm = normalize_sheet_code(current_sheet_label) if current_sheet_label else ""
    seen_keys = set()

    for b in d.get("blocks", []):
        if "lines" not in b:
            continue
        lines = b["lines"]

        block_text = " ".join(s.get("text", "") for l in lines for s in l.get("spans", [])).strip()
        block_upper = block_text.upper()
        if any(kw in block_upper for kw in GENERAL_NOTE_KEYWORDS):
            continue
        if len(block_text) > 120:
            continue

        l_idx = 0
        while l_idx < len(lines):
            line = lines[l_idx]
            line_text = " ".join(s.get("text", "") for s in line.get("spans", [])).strip()
            if not line_text:
                l_idx += 1
                continue

            # 1. Check inline slash pattern: e.g. "08 / A-706", "A-706 / 08"
            slash_match = SLASH_CALLOUT_PAT.search(line_text)
            if slash_match:
                if slash_match.group(1) and slash_match.group(2):
                    det = slash_match.group(1)
                    sheet = normalize_sheet_code(slash_match.group(2))
                else:
                    sheet = normalize_sheet_code(slash_match.group(3))
                    det = slash_match.group(4)

                if sheet != curr_norm and not sheet.startswith("A-10"):
                    bbox = tuple(line["bbox"])
                    cx = (bbox[0] + bbox[2]) / 2.0
                    cy = (bbox[1] + bbox[3]) / 2.0
                    c_tag = f"{sheet} / {det}" if det else sheet
                    key = (c_tag, round(cx, 1), round(cy, 1))
                    if key not in seen_keys:
                        seen_keys.add(key)
                        callouts.append(SectionCallout(
                            raw_text=line_text,
                            sheet_ref=sheet,
                            detail_num=det,
                            tag=c_tag,
                            cx=cx,
                            cy=cy,
                            bbox=bbox,
                            callout_type=classify_callout_sheet(sheet),
                            page_num=page_num,
                        ))
                l_idx += 1
                continue

            # 2. Check standalone sheet reference pattern: e.g. "A-706", "A-801", "A-802"
            sheet_match = SHEET_REF_PAT.search(line_text)
            if sheet_match:
                sheet = normalize_sheet_code(sheet_match.group(1))
                if sheet == curr_norm or sheet.startswith("A-10"):
                    l_idx += 1
                    continue

                det = ""
                det_line = None

                # Lookahead to adjacent next line in block
                if l_idx + 1 < len(lines):
                    next_text = " ".join(s.get("text", "") for s in lines[l_idx + 1].get("spans", [])).strip()
                    m_det = DETAIL_NUM_PAT.match(next_text)
                    if m_det:
                        det = m_det.group(1)
                        det_line = lines[l_idx + 1]
                        l_idx += 1

                # Lookback to adjacent previous line in block
                if not det and l_idx > 0:
                    prev_text = " ".join(s.get("text", "") for s in lines[l_idx - 1].get("spans", [])).strip()
                    m_det = DETAIL_NUM_PAT.match(prev_text)
                    if m_det:
                        det = m_det.group(1)
                        det_line = lines[l_idx - 1]

                if det_line is not None:
                    b_sheet = line["bbox"]
                    b_det = det_line["bbox"]
                    bbox = (
                        min(b_sheet[0], b_det[0]),
                        min(b_sheet[1], b_det[1]),
                        max(b_sheet[2], b_det[2]),
                        max(b_sheet[3], b_det[3]),
                    )
                    raw = f"{line_text}\n{det}"
                else:
                    bbox = tuple(line["bbox"])
                    raw = line_text

                cx = (bbox[0] + bbox[2]) / 2.0
                cy = (bbox[1] + bbox[3]) / 2.0
                c_tag = f"{sheet} / {det}" if det else sheet
                key = (c_tag, round(cx, 1), round(cy, 1))
                if key not in seen_keys:
                    seen_keys.add(key)
                    callouts.append(SectionCallout(
                        raw_text=raw,
                        sheet_ref=sheet,
                        detail_num=det if det else None,
                        tag=c_tag,
                        cx=cx,
                        cy=cy,
                        bbox=bbox,
                        callout_type=classify_callout_sheet(sheet),
                        page_num=page_num,
                    ))

            l_idx += 1

    return callouts


def extract_explicit_height_from_page(
    doc: fitz.Document,
    page_num: int,
    detail_num: Optional[str] = None,
) -> Optional[float]:
    """
    Navigates to referenced detail/elevation sheet and extracts explicit
    ceiling/wall height dimension (e.g. '+- 8'-0" CH' -> 8.00 ft, '+- 7'-8" CH' -> 7.67 ft,
    '+- 7'-3" CH' -> 7.25 ft). Returns None if no explicit ceiling height dimension is found.
    Correlates with detail numbers via detail title / marker anchors if detail_num is provided.
    """
    if page_num < 1 or page_num > len(doc):
        return None
    page = doc[page_num - 1]
    blocks = page.get_text("blocks")

    # Extract all candidate ceiling heights with their locations
    ch_candidates: List[Tuple[float, float, float, str]] = []  # (height_ft, cx, cy, text)

    for b in blocks:
        txt = b[4].strip()
        h_val = parse_ceiling_height(txt)
        if h_val is not None and 5.0 <= h_val <= 30.0:
            cx = (b[0] + b[2]) / 2.0
            cy = (b[1] + b[3]) / 2.0
            ch_candidates.append((h_val, cx, cy, txt))

    if not ch_candidates:
        return None

    # If detail_num is specified, correlate with detail elevation marker location
    if detail_num:
        norm_det = detail_num.lstrip("0") or detail_num
        best_detail_loc = None
        min_det_rank = float("inf")

        for b in blocks:
            txt = b[4].strip()
            lines = [l.strip() for l in txt.splitlines() if l.strip()]
            for l in lines:
                is_exact = l == detail_num or l == norm_det
                is_pattern = bool(re.search(rf"\b(?:DETAIL|ELEVATION|PLAN).*?\b0?{norm_det}\b", l, re.IGNORECASE))
                if is_exact or is_pattern:
                    cx = (b[0] + b[2]) / 2.0
                    cy = (b[1] + b[3]) / 2.0
                    rank = 1 if is_exact else 2
                    if rank < min_det_rank:
                        min_det_rank = rank
                        best_detail_loc = (cx, cy)
                    break

        if best_detail_loc:
            # Find closest CH candidate to this detail marker
            best_h = None
            min_dist = float("inf")
            for h_ft, hx, hy, _ in ch_candidates:
                d = math.hypot(hx - best_detail_loc[0], hy - best_detail_loc[1])
                if d < min_dist:
                    min_dist = d
                    best_h = h_ft
            if best_h is not None:
                return best_h

    # Return first positive candidate on sheet if no detail correlation found
    return ch_candidates[0][0]


# ==============================================================================
# WALL RUN HEIGHT VERIFICATION ENGINE
# ==============================================================================

def verify_wall_run_heights(
    doc: fitz.Document,
    wall_runs: List[WallRun],
    sheet_catalog: List[Dict[str, Any]],
    max_radius_pt: float = 120.0,
    default_height_ft: float = 10.0,
) -> Tuple[List[WallRun], List[Dict[str, Any]]]:
    """
    Contract Function:
    Spatially matches wall runs on floor plans to nearest section callout tags
    (within max_radius_pt radius, default 120.0 pt), navigates to referenced section
    detail sheet, extracts explicit ceiling/wall height, or falls back to 10.0 ft
    default with is_height_verified=False and review flagging.

    Args:
        doc: PyMuPDF Document.
        wall_runs: Traced and deduplicated wall runs.
        sheet_catalog: Indexed blueprint sheets list.
        max_radius_pt: Spatial search radius in points (default 120.0 pt).
        default_height_ft: Standard default height fallback in feet (default 10.0 ft).

    Returns:
        Tuple of (updated_wall_runs, review_items).
    """
    sheet_map: Dict[str, int] = {}
    for s in sheet_catalog:
        label = s.get("sheet_label")
        pnum = s.get("page_num")
        if label and pnum:
            sheet_map[label] = pnum
            sheet_map[normalize_sheet_label(label)] = pnum

    # Group wall runs by page to discover callouts once per page
    runs_by_page: Dict[int, List[WallRun]] = {}
    for wr in wall_runs:
        runs_by_page.setdefault(wr.page_num, []).append(wr)

    page_callouts: Dict[int, List[SectionCallout]] = {}
    for p_num, runs in runs_by_page.items():
        if 1 <= p_num <= len(doc):
            sheet_lbl = runs[0].sheet_label if runs else ""
            page_callouts[p_num] = discover_section_callouts_on_page(
                page=doc[p_num - 1],
                page_num=p_num,
                current_sheet_label=sheet_lbl,
            )
        else:
            page_callouts[p_num] = []

    review_items: List[Dict[str, Any]] = []

    for wr in wall_runs:
        # If manual markup already has estimator override, preserve it
        if wr.is_manual and wr.height_ft is not None:
            wr.is_height_verified = True
            wr.status = "OK"
            continue

        callouts = page_callouts.get(wr.page_num, [])

        # Find nearest callout within max_radius_pt using Euclidean point-to-segment distance
        best_c: Optional[SectionCallout] = None
        min_dist = max_radius_pt

        for c in callouts:
            d, _, _, _ = point_to_segment_distance(
                c.cx, c.cy, wr.spine.x1, wr.spine.y1, wr.spine.x2, wr.spine.y2
            )
            if d < min_dist:
                min_dist = d
                best_c = c

        verified_height: Optional[float] = None
        if best_c:
            wr.section_callout_tag = best_c.tag
            target_page = sheet_map.get(best_c.sheet_ref) or sheet_map.get(normalize_sheet_label(best_c.sheet_ref))
            if target_page:
                verified_height = extract_explicit_height_from_page(
                    doc=doc,
                    page_num=target_page,
                    detail_num=best_c.detail_num,
                )

        if verified_height is not None and verified_height > 0:
            # Case A: Callout tag found AND referenced sheet provides explicit height
            wr.height_ft = verified_height
            wr.is_height_verified = True
            if best_c and best_c.detail_num:
                wr.height_source = f"{best_c.sheet_ref} Detail {best_c.detail_num}"
            elif best_c:
                wr.height_source = f"{best_c.sheet_ref} Detail"
            else:
                wr.height_source = "SECTION_DETAIL_VERIFIED"
            wr.status = "OK"
        else:
            # Case B: Callout missing OR referenced detail lacks explicit height dimension
            wr.height_ft = default_height_ft
            wr.is_height_verified = False
            wr.height_source = "UNVERIFIED_HEIGHT_DEFAULT"
            wr.status = "REVIEW"

            if wr.section_callout_tag:
                issue = (
                    f"Unverified wall height for Tag {wr.tag}: "
                    f"Referenced detail {wr.section_callout_tag} lacks explicit height dimension. "
                    f"Using standard {default_height_ft:.1f} ft fallback."
                )
                note = (
                    f"Unverified wall height: Detail {wr.section_callout_tag} lacks explicit height dimension. "
                    f"Using standard {default_height_ft:.1f} ft fallback."
                )
            else:
                issue = (
                    f"Unverified wall height for Tag {wr.tag}: "
                    f"No section callout found on floor plan. "
                    f"Using standard {default_height_ft:.1f} ft fallback."
                )
                note = f"Isolated wall run: No section callout within {max_radius_pt:.0f} pt radius."

            if note not in wr.notes:
                wr.notes.append(note)

            review_item = {
                "run_id": wr.run_id,
                "target_id": wr.run_id,
                "review_id": f"REV-HGT-{wr.run_id}",
                "tag": wr.tag,
                "page": wr.page_num,
                "sheet": wr.sheet_label,
                "category": "Unverified Wall Height",
                "issue": issue,
                "description": issue,
                "action_required": "Estimator review required to confirm wall height against architectural elevations.",
                "required_action": "Estimator review required to confirm wall height against architectural elevations.",
                "measured_values": f"Default Height: {default_height_ft:.2f} ft | Gross: {wr.gross_length_ft:.2f} LF",
            }
            review_items.append(review_item)

    return wall_runs, review_items
