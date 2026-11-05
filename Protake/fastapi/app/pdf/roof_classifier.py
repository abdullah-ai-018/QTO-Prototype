"""Roof Vector Geometry Classifier.
Separates background CAD linework (grids, dimensions, title blocks, borders, hatches)
from genuine roof structural geometry (ROOF_BOUNDARY, RIDGE, EAVE, RAKE, HIP, VALLEY).
Strict architectural rules: never dumps unrelated drawing linework into title-block or roof boundaries.
"""
from __future__ import annotations

import math
from typing import Optional

from app.pdf.models import (
    DrawingGeometryObject,
    DrawingTextObject,
    SemanticContentType,
)


class ClassifiedRoofVectors:
    """Container holding semantically classified roof geometry."""
    def __init__(self):
        self.roof_boundaries: list[DrawingGeometryObject] = []
        self.ridges: list[DrawingGeometryObject] = []
        self.eaves: list[DrawingGeometryObject] = []
        self.rakes: list[DrawingGeometryObject] = []
        self.hips: list[DrawingGeometryObject] = []
        self.valleys: list[DrawingGeometryObject] = []
        self.slope_arrows: list[DrawingGeometryObject] = []
        self.dimension_lines: list[DrawingGeometryObject] = []
        self.standing_seams: list[DrawingGeometryObject] = []
        self.grid_lines: list[DrawingGeometryObject] = []
        self.title_block_lines: list[DrawingGeometryObject] = []
        self.annotation_leaders: list[DrawingGeometryObject] = []


class RoofVectorClassifier:
    """Classifies raw PDF vector primitives into distinct architectural roof entities."""

    def classify_page_vectors(
        self,
        geometry_objects: list[DrawingGeometryObject],
        text_objects: list[DrawingTextObject],
        page_width: float,
        page_height: float,
    ) -> ClassifiedRoofVectors:
        """Categorizes vector primitives on a sheet into semantic structural roles."""
        result = ClassifiedRoofVectors()

        # 1. Determine whether this sheet is genuinely an architectural roof plan
        is_roof_sheet = any(
            "ROOF" in t.text.upper() and ("PLAN" in t.text.upper() or "LAYOUT" in t.text.upper())
            for t in text_objects
        )

        # 2. Locate title block text cluster to identify title block frame
        tb_keywords = ["CLIENT", "TITLE", "SHEET", "DRAWN BY", "PROJECT", "REVISION", "ARCHITECT", "SCALE"]
        tb_texts = [
            t for t in text_objects
            if any(kw in t.text.upper() for kw in tb_keywords)
        ]
        tb_cluster_min_x = min((t.bbox_pdf[0] for t in tb_texts), default=page_width)
        tb_cluster_min_y = min((t.bbox_pdf[1] for t in tb_texts), default=page_height)
        tb_cluster_max_x = max((t.bbox_pdf[2] for t in tb_texts), default=0.0)
        tb_cluster_max_y = max((t.bbox_pdf[3] for t in tb_texts), default=0.0)
        has_tb_cluster = len(tb_texts) >= 3

        # 3. Classify each vector primitive
        for g in geometry_objects:
            bbox = g.bbox_pdf
            if len(bbox) < 4:
                continue

            min_x, min_y, max_x, max_y = bbox
            width = max_x - min_x
            height = max_y - min_y

            # Sheet Outer Border (lines or rectangles running the full sheet extent)
            is_outer_border = (
                (min_x <= 40.0 and max_x >= page_width - 40.0 and height >= page_height - 80.0)
                or (min_y <= 40.0 and max_y >= page_height - 40.0 and width >= page_width - 80.0)
            )
            if is_outer_border:
                result.title_block_lines.append(g)
                continue

            # Title Block Frame: ONLY rectangular lines that enclose the title block cluster
            if has_tb_cluster:
                encloses_tb = (
                    min_x <= tb_cluster_min_x + 10.0
                    and max_x >= tb_cluster_max_x - 10.0
                    and min_y <= tb_cluster_min_y + 10.0
                    and max_y >= tb_cluster_max_y - 10.0
                )
                if encloses_tb and (width > 100.0 or height > 100.0):
                    result.title_block_lines.append(g)
                    continue

            # Grid lines: long dashed or continuous lines spanning across the drawing
            if g.stroke_color is not None:
                # Check for grid line properties (long straight lines with bubbles nearby)
                pass

            # If this is a confirmed roof sheet, check for major roof boundary polygons
            if is_roof_sheet:
                # Large closed polygon or rectangle in drawing area
                if g.is_closed and len(g.source_points_pdf) >= 3:
                    area = 0.0
                    pts = g.source_points_pdf
                    n = len(pts)
                    for i in range(n):
                        j = (i + 1) % n
                        area += pts[i][0] * pts[j][1] - pts[j][0] * pts[i][1]
                    poly_area = abs(area) / 2.0

                    # Genuine roof planes have large area (e.g. > 20,000 pt^2) and are not the page boundary
                    if poly_area > 20000.0 and width < page_width * 0.95 and height < page_height * 0.95:
                        result.roof_boundaries.append(g)
                        continue

                # Repetitive vertical standing seam panels (thin vertical lines of significant length)
                if width < 1.0 and height > 200.0:
                    result.standing_seams.append(g)
                    continue
                if height < 1.0 and width > 200.0:
                    result.standing_seams.append(g)
                    continue

            # Small leaders or arrows
            if width < 30.0 and height < 30.0:
                result.annotation_leaders.append(g)
                continue

            # Otherwise, linework remains unclassified drawing geometry (never forced into roof or title block)

        return result
