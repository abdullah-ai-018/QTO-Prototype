"""Native PDF Vector Geometry Extractor.
Extracts drawing paths, polylines, lines, beziers, rectangles, and fills
directly from PDF vector streams using PyMuPDF (fitz) without rasterization.
Preserves original PDF coordinates, normalized coordinates, and transformation metadata.
"""
from __future__ import annotations

from typing import Any, Optional
import fitz  # PyMuPDF

from app.bim.models import DataProvenanceStatus
from app.pdf.models import (
    DrawingGeometryObject,
    GeometryPrimitiveType,
    TransformMetadata,
)


class PDFVectorExtractor:
    """Extracts raw vector linework from PDF pages with exact coordinate preservation."""

    def extract_page_vectors(self, page: fitz.Page, page_number: int) -> list[DrawingGeometryObject]:
        """Extracts all vector geometry objects from a PDF page."""
        raw_drawings = page.get_drawings()
        width_pt = float(page.rect.width)
        height_pt = float(page.rect.height)

        geometry_objects: list[DrawingGeometryObject] = []

        for idx, d in enumerate(raw_drawings, start=1):
            items = d.get("items", [])
            if not items:
                continue

            rect = d.get("rect", fitz.Rect())
            bbox_pdf = [float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)]

            stroke_color = d.get("color")
            if stroke_color is not None and isinstance(stroke_color, (tuple, list)):
                stroke_color = tuple(float(c) for c in stroke_color[:3])
            else:
                stroke_color = None

            fill_color = d.get("fill")
            if fill_color is not None and isinstance(fill_color, (tuple, list)):
                fill_color = tuple(float(c) for c in fill_color[:3])
            else:
                fill_color = None

            stroke_width = float(d.get("width") or 1.0)
            is_closed = bool(d.get("closePath", False))
            layer_name = d.get("layer")

            # Extract path vertices from drawing operations
            source_points: list[list[float]] = []
            prim_type = GeometryPrimitiveType.POLYLINE

            for item in items:
                op = item[0]
                if op == "l":  # Line: ("l", p1, p2)
                    p1, p2 = item[1], item[2]
                    if not source_points:
                        source_points.append([float(p1.x), float(p1.y)])
                    source_points.append([float(p2.x), float(p2.y)])
                    if len(items) == 1:
                        prim_type = GeometryPrimitiveType.LINE
                elif op == "re":  # Rectangle: ("re", Rect)
                    r = item[1]
                    source_points = [
                        [float(r.x0), float(r.y0)],
                        [float(r.x1), float(r.y0)],
                        [float(r.x1), float(r.y1)],
                        [float(r.x0), float(r.y1)],
                    ]
                    prim_type = GeometryPrimitiveType.RECTANGLE
                    is_closed = True
                elif op == "c":  # Cubic Bezier: ("c", p1, p2, p3, p4)
                    p1, p2, p3, p4 = item[1], item[2], item[3], item[4]
                    if not source_points:
                        source_points.append([float(p1.x), float(p1.y)])
                    # Sample curve adaptively
                    curve_pts = self._linearize_cubic_bezier(p1, p2, p3, p4, steps=8)
                    source_points.extend(curve_pts)
                    prim_type = GeometryPrimitiveType.BEZIER
                elif op == "qu":  # Quad: ("qu", quad)
                    q = item[1]
                    source_points = [
                        [float(q.ul.x), float(q.ul.y)],
                        [float(q.ur.x), float(q.ur.y)],
                        [float(q.lr.x), float(q.lr.y)],
                        [float(q.ll.x), float(q.ll.y)],
                    ]
                    prim_type = GeometryPrimitiveType.QUAD
                    is_closed = True

            if not source_points:
                continue

            # Check if start and end match within 0.01 pt tolerance
            if len(source_points) >= 3:
                dx = abs(source_points[0][0] - source_points[-1][0])
                dy = abs(source_points[0][1] - source_points[-1][1])
                if dx < 0.01 and dy < 0.01:
                    is_closed = True

            # Normalized points (clamped to page dimensions)
            normalized_points = [
                [max(0.0, min(width_pt, pt[0])), max(0.0, min(height_pt, pt[1]))]
                for pt in source_points
            ]

            obj_id = f"GEO-P{page_number:02d}-{idx:05d}"
            path_type_str = prim_type.value.lower()

            stroke_dict = {"color": stroke_color, "width": stroke_width} if stroke_color else None
            fill_dict = {"color": fill_color} if fill_color else None

            geometry_objects.append(
                DrawingGeometryObject(
                    id=obj_id,
                    source_vector_id=obj_id,
                    page_number=page_number,
                    primitive_type=prim_type,
                    path_type=path_type_str,
                    source_points_pdf=source_points,
                    coordinates=source_points,
                    normalized_points=normalized_points,
                    transformed_points_ft=[],  # Empty until scale is verified
                    is_closed=is_closed,
                    stroke_color=stroke_color,
                    fill_color=fill_color,
                    stroke=stroke_dict,
                    fill=fill_dict,
                    stroke_width=stroke_width,
                    layer_name=layer_name,
                    bbox_pdf=bbox_pdf,
                    transform_metadata=TransformMetadata(
                        applied_snapping_tolerance_pt=0.0,
                        snap_count=0,
                        reconstruction_method="NATIVE_EXPLICIT",
                        notes=["Extracted directly from native PDF drawing commands."],
                    ),
                    source_object_id=idx,
                    source="PDF_VECTOR",
                    provenance=DataProvenanceStatus.VERIFIED_EXPLICIT,
                )
            )

        return geometry_objects

    @staticmethod
    def _linearize_cubic_bezier(p1, p2, p3, p4, steps: int = 8) -> list[list[float]]:
        """Samples a cubic Bezier curve into straight line segments."""
        pts: list[list[float]] = []
        for i in range(1, steps + 1):
            t = i / steps
            u = 1.0 - t
            # B(t) = (1-t)^3*P1 + 3(1-t)^2*t*P2 + 3(1-t)*t^2*P3 + t^3*P4
            x = (u**3 * p1.x) + (3 * u**2 * t * p2.x) + (3 * u * t**2 * p3.x) + (t**3 * p4.x)
            y = (u**3 * p1.y) + (3 * u**2 * t * p2.y) + (3 * u * t**2 * p3.y) + (t**3 * p4.y)
            pts.append([float(x), float(y)])
        return pts
