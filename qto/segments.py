"""
CAD linework and vector segment extraction from PDF pages using PyMuPDF.
Filters out title blocks, notes columns, and noise ticks.
Extracts both straight wall segments and door swing Bézier arcs.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Any, List, Tuple
import pymupdf as fitz

from qto.geometry import Point, Segment, BoundingBox


@dataclass
class DoorArc:
    start: Point
    end: Point
    c1: Point
    c2: Point
    chord_length: float
    approx_radius: float
    bbox: BoundingBox
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
            "chord_length": round(self.chord_length, 4),
            "approx_radius": round(self.approx_radius, 4),
            "bbox": self.bbox.to_dict(),
        }


@dataclass
class PageLinework:
    page_num: int
    width: float
    height: float
    segments: List[Segment]
    door_arcs: List[DoorArc]

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_num": self.page_num,
            "width": round(self.width, 2),
            "height": round(self.height, 2),
            "segment_count": len(self.segments),
            "door_arc_count": len(self.door_arcs),
            "segments": [s.to_dict() for s in self.segments],
            "door_arcs": [a.to_dict() for a in self.door_arcs],
        }


def extract_page_linework(
    page: fitz.Page,
    margin_cutoff_x_pct: float = 0.78,
    min_length: float = 4.0,
    max_length_pct: float = 0.45,
    margin_border_pt: float = 12.0,
) -> PageLinework:
    """
    Extracts straight vector line segments and door swing arcs from a CAD drawing PDF page.
    Filters out notes columns (x > cutoff), margin borders, and noise ticks (<4pt).
    """
    pw = page.rect.width
    ph = page.rect.height
    drawing_cutoff_x = pw * margin_cutoff_x_pct
    max_wall_len = pw * max_length_pct

    raw_drawings = page.get_drawings()
    raw_lines: List[Tuple[float, float, float, float]] = []
    raw_curves: List[Tuple[fitz.Point, fitz.Point, fitz.Point, fitz.Point]] = []

    for path in raw_drawings:
        rect = path.get("rect")
        if rect:
            # Skip paths completely in the right-side notes/titleblock area
            if rect.x0 > drawing_cutoff_x:
                continue
            # Skip paths outside printable margins
            if rect.x1 < margin_border_pt or rect.y1 < margin_border_pt:
                continue

        for item in path.get("items", []):
            kind = item[0]
            if kind == "l":
                p1, p2 = item[1], item[2]
                raw_lines.append((p1.x, p1.y, p2.x, p2.y))
            elif kind == "re":
                r = item[1]
                raw_lines.extend([
                    (r.x0, r.y0, r.x1, r.y0),
                    (r.x1, r.y0, r.x1, r.y1),
                    (r.x1, r.y1, r.x0, r.y1),
                    (r.x0, r.y1, r.x0, r.y0),
                ])
            elif kind == "qu":
                q = item[1]
                raw_lines.extend([
                    (q.ul.x, q.ul.y, q.ur.x, q.ur.y),
                    (q.ur.x, q.ur.y, q.lr.x, q.lr.y),
                    (q.lr.x, q.lr.y, q.ll.x, q.ll.y),
                    (q.ll.x, q.ll.y, q.ul.x, q.ul.y),
                ])
            elif kind == "c":
                # Cubic Bezier curve: ("c", p1, p2, p3, p4)
                p1, p2, p3, p4 = item[1], item[2], item[3], item[4]
                raw_curves.append((p1, p2, p3, p4))

    # Process and filter straight line segments
    segments: List[Segment] = []
    for x1, y1, x2, y2 in raw_lines:
        # Ignore lines sitting inside notes column
        if min(x1, x2) > drawing_cutoff_x:
            continue
        # Ignore border margin lines
        if max(x1, x2) < margin_border_pt or max(y1, y2) < margin_border_pt:
            continue
        if min(x1, x2) > pw - margin_border_pt or min(y1, y2) > ph - margin_border_pt:
            continue

        length = math.hypot(x2 - x1, y2 - y1)
        # Filter out ticks / stipples and full-sheet border / gridlines
        if length < min_length or length > max_wall_len:
            continue

        seg = Segment(x1=x1, y1=y1, x2=x2, y2=y2, length=length)
        segments.append(seg)

    # Process door swing arcs (curves)
    door_arcs: List[DoorArc] = []
    for p1, p2, p3, p4 in raw_curves:
        # Check coordinates inside drawing area
        if min(p1.x, p4.x) > drawing_cutoff_x:
            continue

        chord_len = math.hypot(p4.x - p1.x, p4.y - p1.y)
        # Door openings in CAD are typically 1.5' to 8.0' (at 1/8" scale, 13.5 pt to 72 pt)
        if chord_len < 6.0 or chord_len > 180.0:
            continue

        # In a 90-degree circular door swing arc, chord = radius * sqrt(2)
        approx_r = chord_len / math.sqrt(2.0)

        min_x = min(p1.x, p2.x, p3.x, p4.x)
        max_x = max(p1.x, p2.x, p3.x, p4.x)
        min_y = min(p1.y, p2.y, p3.y, p4.y)
        max_y = max(p1.y, p2.y, p3.y, p4.y)

        arc = DoorArc(
            start=Point(p1.x, p1.y),
            end=Point(p4.x, p4.y),
            c1=Point(p2.x, p2.y),
            c2=Point(p3.x, p3.y),
            chord_length=chord_len,
            approx_radius=approx_r,
            bbox=BoundingBox(min_x, min_y, max_x, max_y),
        )
        door_arcs.append(arc)

    return PageLinework(
        page_num=page.number + 1,
        width=pw,
        height=ph,
        segments=segments,
        door_arcs=door_arcs,
    )


def extract_page_segments(
    page: fitz.Page,
    margin_cutoff_x_pct: float = 0.78,
    min_length: float = 4.0,
    max_length_pct: float = 0.45,
) -> List[dict[str, Any]]:
    """
    Backward-compatible dictionary-based segment extractor.
    Returns list of segment dicts matching test.py output format.
    """
    linework = extract_page_linework(
        page,
        margin_cutoff_x_pct=margin_cutoff_x_pct,
        min_length=min_length,
        max_length_pct=max_length_pct,
    )
    result = []
    for s in linework.segments:
        result.append({
            "x1": s.x1,
            "y1": s.y1,
            "x2": s.x2,
            "y2": s.y2,
            "length": s.length,
            "angle": s.angle,
            "min_x": s.min_x,
            "max_x": s.max_x,
            "min_y": s.min_y,
            "max_y": s.max_y,
            "ux": s.ux,
            "uy": s.uy,
        })
    return result
