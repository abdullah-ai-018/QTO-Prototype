"""qto/sheet_index.py: Blueprint sheet indexing and classification module.

Provides robust title-block extraction, callout rejection, and architectural
sheet classification (floor plans vs partition schedules vs ceiling plans).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import pymupdf

SHEET_PAT = re.compile(r"\b([A-Z]{1,3}[-\s]?\d{3,4}(?:\.\d{1,2})?)\b")
CALLOUT_PREFIX_PAT = re.compile(r"(\d+\s*/\s*|SEE\s+|DETAIL\s+|REF(?:ER)?\s+TO\s+)", re.IGNORECASE)


def normalize_sheet_label(raw: str) -> str:
    """Normalizes architectural sheet numbers to canonical form (e.g. A 101, A101 -> A-101)."""
    if not raw:
        return ""
    s = raw.strip().upper()
    m1 = re.match(r"^([A-Z]{1,3})[\s\-_]+(\d{1,4}(?:\.\d{1,2})?)$", s)
    if m1:
        return f"{m1.group(1)}-{m1.group(2)}"
    m2 = re.match(r"^([A-Z]{1,3})(\d{3,4}(?:\.\d{1,2})?)$", s)
    if m2:
        return f"{m2.group(1)}-{m2.group(2)}"
    return s


def extract_sheet_label(
    page: pymupdf.Page,
    page_num: int,
    page_dict: Optional[Dict[str, Any]] = None,
    page_text: Optional[str] = None,
) -> str:
    """Extracts authoritative sheet label from title block, rejecting incidental detail callouts."""
    d = page_dict if page_dict is not None else page.get_text("dict")
    text = page_text if page_text is not None else page.get_text("text")

    candidates: List[Tuple[float, str]] = []

    for b in d.get("blocks", []):
        if "lines" not in b:
            continue
        for l in b["lines"]:
            line_text = " ".join(s.get("text", "") for s in l.get("spans", []))
            for s in l["spans"]:
                stext = s.get("text", "").strip()
                sz = float(s.get("size", 10.0))

                m = SHEET_PAT.search(stext)
                if not m:
                    continue
                raw_token = m.group(1)

                # Reject detail callout references like '4/A-701', 'SEE DETAIL A-701'
                start_idx = m.start()
                prefix = line_text[:start_idx]
                if CALLOUT_PREFIX_PAT.search(prefix):
                    continue

                is_standalone = (stext == raw_token or stext == m.group(0))
                has_sheet_prefix = bool(
                    re.search(
                        r"(?:SHEET|DWG|DRAWING|NO\.?)\s*[:\s-]*" + re.escape(raw_token),
                        line_text,
                        re.IGNORECASE,
                    )
                )

                score = sz * 2.0
                if is_standalone:
                    score += 15.0
                if has_sheet_prefix:
                    score += 40.0
                elif "SHEET" in line_text.upper():
                    score += 10.0
                if CALLOUT_PREFIX_PAT.search(line_text):
                    score -= 30.0

                norm_token = normalize_sheet_label(raw_token)
                candidates.append((score, norm_token))

    if candidates:
        candidates.sort(key=lambda c: c[0], reverse=True)
        return candidates[0][1]

    # Fallback to simple regex on page text
    fallback_m = SHEET_PAT.search(text)
    if fallback_m:
        return normalize_sheet_label(fallback_m.group(1))

    return f"Sheet_{page_num}"


def extract_sheet_title(
    page: pymupdf.Page,
    page_dict: Optional[Dict[str, Any]] = None,
    page_text: Optional[str] = None,
) -> str:
    """Extracts architectural drawing title from title block area."""
    d = page_dict if page_dict is not None else page.get_text("dict")
    text = page_text if page_text is not None else page.get_text("text")
    txt_upper = text.upper()

    title_candidates: List[Tuple[float, str]] = []
    for b in d.get("blocks", []):
        if "lines" not in b:
            continue
        for l in b["lines"]:
            line_str = " ".join(s.get("text", "") for s in l.get("spans", [])).strip()
            line_up = line_str.upper()

            # Reject detail callout references e.g. "(REFER TO CONSTRUCTION PLANS)", "SEE DETAIL A-701"
            if CALLOUT_PREFIX_PAT.search(line_str) or "(" in line_str or ")" in line_str or "REFER TO" in line_up:
                continue

            if any(k in line_up for k in ["PLAN", "SCHEDULE", "ELEVATION", "SECTION", "PARTITION TYPES", "INDEX", "DETAILS"]):
                if 4 <= len(line_str) <= 60 and not re.match(r"^\d+$", line_str):
                    weight = 1.0
                    if any(k in line_up for k in ["CONSTRUCTION PLAN", "FLOOR PLAN", "PARTITION TYPES", "PARTITION SCHEDULE", "REFLECTED CEILING"]):
                        weight += 10.0
                    max_sz = max((float(s.get("size", 10.0)) for s in l.get("spans", [])), default=10.0)
                    title_candidates.append((weight * max_sz, line_str))

    if title_candidates:
        title_candidates.sort(key=lambda t: t[0], reverse=True)
        return title_candidates[0][1]

    if "FLOOR PLAN" in txt_upper:
        return "FLOOR PLAN"
    if "PARTITION" in txt_upper:
        return "PARTITION SCHEDULE"
    return "ARCHITECTURAL SHEET"


def classify_page_type(
    sheet_label: str,
    sheet_title: str,
    text: str,
    page_num: int,
    total_pages: int,
) -> str:
    """Classifies blueprint page into standard SOP page types with strict precedence."""
    title_up = sheet_title.upper()
    txt_upper = text.upper()

    # 1. Standalone Schedules & Tables (A-900 series or title indicates schedule)
    if any(k in title_up for k in ["PARTITION TYPES", "PARTITION SCHEDULE", "SCHEDULE OF PARTITIONS", "WALL TYPE SCHEDULE", "WALL TYPES"]):
        return "PARTITION_SCHEDULE"
    if sheet_label.startswith("A-90") and not any(k in title_up for k in ["FLOOR PLAN", "CONSTRUCTION PLAN", "REFLECTED"]):
        return "PARTITION_SCHEDULE"

    # 2. General Notes / Legends / Cover (G-00, T-00 series or page 1)
    if sheet_label.startswith(("G-00", "T-00")) or page_num == 1:
        return "LEGEND"
    if any(k in title_up for k in ["LEGEND", "GLOSSARY", "COVER", "INDEX", "DRAWING LIST", "SHEET LIST"]):
        return "LEGEND"

    # 3. Floor / Construction Plans (A-100 series or title has FLOOR PLAN / CONSTRUCTION PLAN)
    if sheet_label.startswith(("A-100", "A-101", "A-102", "A-103", "A-104", "A-105")):
        return "FLOOR_PLAN"
    if any(k in title_up for k in ["FLOOR PLAN", "CONSTRUCTION PLAN", "PLAN - "]) and not sheet_label.startswith(("A-8", "A-9")):
        return "FLOOR_PLAN"
    if ("CONSTRUCTION PLAN" in txt_upper or "FLOOR PLAN" in txt_upper) and not sheet_label.startswith(("A-8", "A-9")):
        if not any(k in title_up for k in ["REFLECTED", "CEILING", "ELEVATION", "SECTION", "DETAIL"]):
            return "FLOOR_PLAN"

    # 4. Reflected Ceiling Plans
    if any(k in title_up for k in ["REFLECTED CEILING", "CEILING PLAN", "RCP"]):
        return "CEILING_PLAN"
    if sheet_label.startswith("A-20") and not any(k in title_up for k in ["FLOOR PLAN", "CONSTRUCTION PLAN"]):
        return "CEILING_PLAN"

    # 5. Backward compatibility for short single-sheet fixtures:
    if total_pages <= 3 and ("FLOOR PLAN" in txt_upper or "PARTITION" in txt_upper or "FRAMING PLAN" in txt_upper):
        return "FLOOR_PLAN"

    return "OTHER"


def index_blueprint_sheets(doc: pymupdf.Document) -> List[Dict[str, Any]]:
    """Indexes all pages in a blueprint document."""
    total_pages = len(doc)
    sheets: List[Dict[str, Any]] = []
    for p_idx, page in enumerate(doc):
        page_num = p_idx + 1
        d = page.get_text("dict")
        text = page.get_text("text")
        sheet_label = extract_sheet_label(page, page_num, page_dict=d, page_text=text)
        sheet_title = extract_sheet_title(page, page_dict=d, page_text=text)
        page_type = classify_page_type(sheet_label, sheet_title, text, page_num, total_pages)

        sheets.append({
            "page_num": page_num,
            "sheet_label": sheet_label,
            "sheet_title": sheet_title,
            "page_type": page_type,
            "width": round(page.rect.width, 2),
            "height": round(page.rect.height, 2),
        })
    return sheets


def extract_blueprint_sheet_catalog(doc_or_path: Union[pymupdf.Document, str, Path]) -> List[Dict[str, Any]]:
    """Extracts sheet catalog with scale information conforming to PROJECT.md:80-94."""
    from qto.scale import detect_scale_from_page

    def process_doc(doc: pymupdf.Document) -> List[Dict[str, Any]]:
        total_pages = len(doc)
        catalog: List[Dict[str, Any]] = []
        for p_idx, page in enumerate(doc):
            p_num = p_idx + 1
            d = page.get_text("dict")
            text = page.get_text("text")
            sheet_label = extract_sheet_label(page, p_num, page_dict=d, page_text=text)
            sheet_title = extract_sheet_title(page, page_dict=d, page_text=text)
            page_type = classify_page_type(sheet_label, sheet_title, text, p_num, total_pages)

            ft_per_pt, matched_scale, _ = detect_scale_from_page(page)

            catalog.append({
                "page_num": p_num,
                "sheet_label": sheet_label,
                "sheet_title": sheet_title,
                "page_type": page_type,
                "scale": matched_scale,
                "ft_per_pt": round(ft_per_pt, 6),
            })
        return catalog

    if isinstance(doc_or_path, (str, Path)):
        with pymupdf.open(str(doc_or_path)) as doc:
            return process_doc(doc)
    else:
        return process_doc(doc_or_path)
