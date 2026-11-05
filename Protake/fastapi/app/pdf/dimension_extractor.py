"""Architectural Dimension Extractor.
Extracts structured architectural dimensions from native PDF text and vector linework.
Associates dimension text with witness lines, dimension lines, and measured geometry edges.
Follows strict auditable constraints: if association cannot be proven, association_status = REVIEW_REQUIRED.
"""
from __future__ import annotations

import math
import re
from typing import Optional

from app.bim.models import DataProvenanceStatus
from app.pdf.models import (
    DrawingDimensionObject,
    DrawingGeometryObject,
    DrawingTextObject,
    ScaleEvidence,
    ScaleStatus,
    SemanticContentType,
)
from app.pdf.scale_validator import ScaleValidator


class PDFDimensionExtractor:
    """Structures native PDF dimensions with geometry association and real-world calibration."""

    def extract_dimensions(
        self,
        text_objects: list[DrawingTextObject],
        geometry_objects: list[DrawingGeometryObject],
        scale_evidence: ScaleEvidence,
        page_number: int,
    ) -> list[DrawingDimensionObject]:
        """Extracts all structured dimension objects from the sheet."""
        dimensions: list[DrawingDimensionObject] = []
        dim_counter = 1

        # Pre-filter geometry lines (straight 2-point segments or rectangular vectors)
        line_objects = [
            g for g in geometry_objects
            if len(g.source_points_pdf) >= 2 and not g.is_closed
        ]

        for text_obj in text_objects:
            parsed_dim = self._parse_dimension_text(text_obj.text)
            if not parsed_dim:
                # Also check if text was classified as DIMENSION_TEXT
                if text_obj.semantic_type == SemanticContentType.DIMENSION_TEXT:
                    num_match = re.search(r"(\d+(?:\.\d+)?)", text_obj.text)
                    if num_match:
                        parsed_dim = (float(num_match.group(1)), "mm" if "mm" in text_obj.text.lower() else "unknown")
                if not parsed_dim:
                    continue

            measured_val, unit = parsed_dim
            # Skip tiny numbers like grid bubble numbers 1, 2, 3
            if measured_val < 50.0 and unit == "unknown":
                continue

            # Find matching dimension line nearby
            dim_line, witness_lines, start_pt, end_pt = self._find_dimension_linework(
                text_obj, line_objects
            )

            # Compute points distance
            pt_dist = math.hypot(end_pt[0] - start_pt[0], end_pt[1] - start_pt[1]) if (start_pt and end_pt) else 0.0

            # Real world lengths
            length_ft: Optional[float] = None
            length_mm: Optional[float] = None
            start_ft: Optional[list[float]] = None
            end_ft: Optional[list[float]] = None

            if unit == "mm":
                length_mm = measured_val
                length_ft = measured_val / 304.8
            elif unit in ("ft", "in"):
                length_ft = measured_val
                length_mm = measured_val * 304.8
            elif scale_evidence.scale_status != ScaleStatus.SCALE_UNRESOLVED and scale_evidence.ft_per_pt:
                # Infer from point distance if unit not stated in text
                length_ft = pt_dist * scale_evidence.ft_per_pt
                length_mm = length_ft * 304.8

            if scale_evidence.scale_status != ScaleStatus.SCALE_UNRESOLVED and scale_evidence.ft_per_pt:
                start_ft = ScaleValidator.transform_point_to_ft(start_pt, scale_evidence)
                end_ft = ScaleValidator.transform_point_to_ft(end_pt, scale_evidence)

            # Find associated drawing geometry edges (e.g. boundary lines parallel to dimension)
            associated_geoms, association_status = self._associate_measured_geometry(
                start_pt, end_pt, geometry_objects, witness_lines
            )

            is_calibrated = False
            calib_ratio = None
            if pt_dist > 0.0 and length_ft is not None:
                calib_ratio = length_ft / pt_dist
                is_calibrated = True

            dim_id = f"DIM-P{page_number:02d}-{dim_counter:04d}"
            dim_counter += 1

            dimensions.append(
                DrawingDimensionObject(
                    id=dim_id,
                    page_number=page_number,
                    dimension_text=text_obj.text,
                    text_object_id=text_obj.id,
                    nominal_length_ft=length_ft,
                    measured_value=measured_val,
                    unit=unit,
                    start_pt=start_pt,
                    end_pt=end_pt,
                    start_pt_ft=start_ft,
                    end_pt_ft=end_ft,
                    measured_points_distance=pt_dist,
                    measured_length_ft=length_ft,
                    measured_length_mm=length_mm,
                    dimension_line_id=dim_line.id if dim_line else None,
                    witness_line_ids=[w.id for w in witness_lines],
                    associated_geometry_ids=associated_geoms,
                    association_status=association_status,
                    calibration_ratio=calib_ratio,
                    is_calibrated=is_calibrated,
                    provenance=DataProvenanceStatus.VERIFIED_EXPLICIT if association_status == "VERIFIED_EXPLICIT" else DataProvenanceStatus.DERIVED_GEOMETRIC,
                )
            )

        return dimensions

    def _parse_dimension_text(self, text: str) -> Optional[tuple[float, str]]:
        """Parses metric millimeter or imperial foot/inch dimension strings."""
        clean = text.strip()
        # 1. Millimeter format: "17652 mm", "13388mm"
        m_mm = re.match(r"^(\d+(?:\.\d+)?)\s*mm$", clean, re.IGNORECASE)
        if m_mm:
            return (float(m_mm.group(1)), "mm")

        # 2. Imperial foot-inch format: 24'-6", 12'-0", 8' - 4", 14'-1 1/2"
        m_imp_fi = re.match(r"^(\d+)'\s*-\s*(\d+)(?:\s+(\d)/(\d))?\"?$", clean)
        if m_imp_fi:
            ft = float(m_imp_fi.group(1))
            inches = float(m_imp_fi.group(2))
            frac = float(m_imp_fi.group(3)) / float(m_imp_fi.group(4)) if m_imp_fi.group(3) else 0.0
            return (ft + (inches + frac) / 12.0, "ft")

        # 3. Imperial standalone feet: 3', 35', 80'
        m_ft = re.match(r"^(\d+)'$", clean)
        if m_ft:
            return (float(m_ft.group(1)), "ft")

        # 4. Detail fraction inches: 2 1/4", 1 3/4", 5/8", 1/4", 1/2", 7/8"
        m_frac_in = re.match(r"^(?:(\d+)\s+)?(\d)/(\d)\"?$", clean)
        if m_frac_in:
            whole = float(m_frac_in.group(1)) if m_frac_in.group(1) else 0.0
            num = float(m_frac_in.group(2))
            den = float(m_frac_in.group(3))
            inches = whole + (num / den)
            return (inches / 12.0, "in")

        # 5. Detail whole inches: 1", 2", 4", 6"
        m_in = re.match(r"^(\d+(?:\.\d+)?)\"$", clean)
        if m_in:
            return (float(m_in.group(1)) / 12.0, "in")

        # 6. Dimensions like 6"x6"
        m_grid_dim = re.match(r"^(\d+)\"\s*x\s*(\d+)\"$", clean, re.IGNORECASE)
        if m_grid_dim:
            w = float(m_grid_dim.group(1))
            return (w / 12.0, "in")

        return None

    def _find_dimension_linework(
        self,
        text_obj: DrawingTextObject,
        line_objects: list[DrawingGeometryObject],
    ) -> tuple[Optional[DrawingGeometryObject], list[DrawingGeometryObject], list[float], list[float]]:
        """Searches for the dimension line adjacent to the text label, plus witness lines."""
        tb = text_obj.bbox_pdf
        tx_mid = (tb[0] + tb[2]) / 2.0
        ty_mid = (tb[1] + tb[3]) / 2.0

        best_line: Optional[DrawingGeometryObject] = None
        min_dist = 60.0  # max 60 pt search radius around text
        start_pt = [tb[0], tb[1]]
        end_pt = [tb[2], tb[3]]

        for line in line_objects:
            pts = line.source_points_pdf
            if len(pts) < 2:
                continue
            p0, p1 = pts[0], pts[-1]
            lx_mid = (p0[0] + p1[0]) / 2.0
            ly_mid = (p0[1] + p1[1]) / 2.0

            dist = math.hypot(tx_mid - lx_mid, ty_mid - ly_mid)
            if dist < min_dist:
                min_dist = dist
                best_line = line
                start_pt = p0
                end_pt = p1

        # Search for witness lines near start_pt and end_pt
        witness_lines: list[DrawingGeometryObject] = []
        if best_line:
            for line in line_objects:
                if line.id == best_line.id:
                    continue
                pts = line.source_points_pdf
                if len(pts) < 2:
                    continue
                p0, p1 = pts[0], pts[-1]
                # Witness lines are typically short perpendicular segments (< 40 pt)
                length = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
                if length > 50.0:
                    continue
                dist_start = min(math.hypot(p0[0] - start_pt[0], p0[1] - start_pt[1]), math.hypot(p1[0] - start_pt[0], p1[1] - start_pt[1]))
                dist_end = min(math.hypot(p0[0] - end_pt[0], p0[1] - end_pt[1]), math.hypot(p1[0] - end_pt[0], p1[1] - end_pt[1]))
                if dist_start < 15.0 or dist_end < 15.0:
                    witness_lines.append(line)

        return best_line, witness_lines, start_pt, end_pt

    def _associate_measured_geometry(
        self,
        start_pt: list[float],
        end_pt: list[float],
        geometry_objects: list[DrawingGeometryObject],
        witness_lines: list[DrawingGeometryObject],
    ) -> tuple[list[str], str]:
        """Corroborates dimension endpoints with nearby building geometry edges."""
        dim_length = math.hypot(end_pt[0] - start_pt[0], end_pt[1] - start_pt[1])
        if dim_length < 1.0:
            return [], "REVIEW_REQUIRED"

        associated_ids: list[str] = []

        # Check for geometry objects that match this length within 2.0 pt and run parallel
        for g in geometry_objects:
            if g.is_closed:
                continue
            pts = g.source_points_pdf
            if len(pts) < 2:
                continue
            p0, p1 = pts[0], pts[-1]
            geom_len = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
            if abs(geom_len - dim_length) < 2.5:
                # Check parallelism
                dx_dim = end_pt[0] - start_pt[0]
                dy_dim = end_pt[1] - start_pt[1]
                dx_geo = p1[0] - p0[0]
                dy_geo = p1[1] - p0[1]
                # Dot product normalized
                cos_theta = abs(dx_dim * dx_geo + dy_dim * dy_geo) / (dim_length * geom_len + 1e-6)
                if cos_theta > 0.98:  # parallel within ~11 degrees
                    associated_ids.append(g.id)

        if associated_ids:
            return associated_ids, "VERIFIED_EXPLICIT"
        return [], "REVIEW_REQUIRED"
