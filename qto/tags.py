"""
Wall tag discovery and spatial instance extraction.
Enforces lumber negative lookahead: \\b(?!\\d+X\\d+\\b)([0-9][A-Z]|[1-9][A-Z][0-9]|GL[1-9]|PW)\\b
ensuring framing notes (e.g., 2X4, 2X6) are never mistaken for wall partition types.
"""

from __future__ import annotations
import re
from dataclasses import dataclass
from typing import List, Set, Tuple
import pymupdf as fitz

from qto.geometry import Point, BoundingBox

# Canonical tag regex with lumber negative lookahead
TAG_REGEX = re.compile(
    r"\b(?!\d+X\d+\b)([0-9][A-Z]|[1-9][A-Z][0-9]|GL[1-9]|PW)\b"
)

# Common non-wall tokens / false positives to discard
EXCLUSION_TOKENS = {
    "GA", "DC", "HR", "SF", "LF", "OC", "MAX", "MIN", "TYP", "SIM", "NTS", "REF", "DET"
}


@dataclass
class TagInstance:
    tag: str
    page_num: int
    bbox: BoundingBox
    center: Point
    tag_radius: float

    def to_dict(self) -> dict:
        return {
            "tag": self.tag,
            "page_num": self.page_num,
            "bbox": self.bbox.to_dict(),
            "center": self.center.to_dict(),
            "tag_radius": round(self.tag_radius, 2),
        }


def is_valid_wall_tag(token: str) -> bool:
    """Checks whether a token strictly matches the wall tag pattern and is not lumber or noise."""
    token = token.strip().upper()
    if token in EXCLUSION_TOKENS:
        return False
    # Explicit check against lumber framing dimensions: 2X4, 2X6, 2X8, etc.
    if re.match(r"^\d+X\d+$", token):
        return False
    return bool(TAG_REGEX.fullmatch(token))


def discover_tags_from_schedules(
    doc: fitz.Document,
    schedule_page_indices: List[int] | None = None,
) -> List[str]:
    """
    Discovers candidate wall partition tags across blueprint schedules, legends, and general notes.
    - Searches partition schedule pages (defaulting to pages 22 & 23 if present).
    - Scans legend on Page 1.
    - If document has <= 5 pages, scans all pages to support test fixtures.
    """
    discovered: Set[str] = set()

    # Determine pages to search
    target_pages = set()
    if schedule_page_indices:
        target_pages.update(p for p in schedule_page_indices if 0 <= p < len(doc))
    else:
        # Check standard schedule pages (21, 22 in 0-indexed terms for pages 22, 23)
        for p in [21, 22]:
            if p < len(doc):
                target_pages.add(p)
        # Always check page 0 (Legend A-100 / Title Sheet)
        if len(doc) > 0:
            target_pages.add(0)

        # In short drawing sets (e.g. test fixtures), check all pages
        if len(doc) <= 5:
            target_pages.update(range(len(doc)))
        else:
            # Look for pages with "PARTITION" or "SCHEDULE" in their text
            for idx, p in enumerate(doc):
                try:
                    txt = p.get_text("text")
                    if "PARTITION" in txt.upper() or "WALL TYPE" in txt.upper():
                        target_pages.add(idx)
                except Exception:
                    continue

    for p_idx in sorted(target_pages):
        page = doc[p_idx]
        text = page.get_text("text")
        for match in TAG_REGEX.finditer(text):
            tag = match.group(1).upper()
            if is_valid_wall_tag(tag):
                discovered.add(tag)

    return sorted(discovered)


def find_tag_instances_on_page(
    page: fitz.Page,
    qualified_tags: Set[str],
    drawing_cutoff_x_pct: float = 0.78,
) -> List[TagInstance]:
    """
    Finds spatial occurrences of qualified tags on a floor plan page.
    Filters out words situated inside the notes column (x > cutoff).
    """
    pw = page.rect.width
    drawing_cutoff_x = pw * drawing_cutoff_x_pct
    words = page.get_text("words")
    instances: List[TagInstance] = []

    for w in words:
        x0, y0, x1, y1, raw_word = w[0], w[1], w[2], w[3], w[4]
        # Ignore words in right-side title block / notes
        if x0 > drawing_cutoff_x:
            continue

        # Clean punctuation from word: "(7A)" -> "7A", "7A." -> "7A"
        cleaned_token = re.sub(r"[^A-Z0-9]", "", raw_word.upper())
        if cleaned_token in qualified_tags and is_valid_wall_tag(cleaned_token):
            bbox = BoundingBox(x0, y0, x1, y1)
            tc_x = (x0 + x1) / 2.0
            tc_y = (y0 + y1) / 2.0
            tag_radius = max(bbox.width, bbox.height) * 1.25

            instances.append(
                TagInstance(
                    tag=cleaned_token,
                    page_num=page.number + 1,
                    bbox=bbox,
                    center=Point(tc_x, tc_y),
                    tag_radius=tag_radius,
                )
            )

    return instances
