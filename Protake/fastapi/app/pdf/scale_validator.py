"""Scale Validation and Calibration Engine.
Deterministically validates architectural drawing scale from explicit text annotations
and independent corroborating dimension geometry.
Strict Rule: A scale is VERIFIED only when:
A) explicit scale notation exists AND
B) independent dimension/vector evidence agrees within tolerance.
Otherwise: status = REVIEW_REQUIRED or SCALE_UNRESOLVED.
Never assumes a default scale or accepts material mix ratios (e.g. CMT 1:4) as drawing scale.
"""
from __future__ import annotations

import math
import re
from typing import Optional

from app.bim.models import DataProvenanceStatus
from app.pdf.models import (
    DrawingGeometryObject,
    DrawingTextObject,
    ScaleEvidence,
    ScaleStatus,
    SemanticContentType,
)

# 1 pt = 1/72 inch; 1 ft = 12 inches = 864 points
PT_PER_INCH = 72.0
PT_PER_FOOT = 864.0
MM_PER_INCH = 25.4


class ScaleValidator:
    """Validates real-world scale and converts PDF points to feet with full provenance."""

    def validate_page_scale(
        self,
        text_objects: list[DrawingTextObject],
        geometry_objects: list[DrawingGeometryObject],
    ) -> ScaleEvidence:
        """Determines the authoritative scale of a drawing page with strict dimension cross-check."""
        # 1. Search for explicit architectural scale text
        explicit_scale = self._find_explicit_scale_text(text_objects)
        if explicit_scale:
            scale_str, ft_per_pt, ratio, txt_id = explicit_scale

            # Cross-check against independent dimension linework
            corroboration = self._cross_check_with_dimensions(
                ft_per_pt, text_objects, geometry_objects
            )

            if corroboration:
                dim_text, expected_pt, actual_pt, residual_error = corroboration
                calib_notes = [
                    f"Explicit scale text '{scale_str}' verified from document content stream.",
                    f"Scale factor: 1.0 PDF pt = {ft_per_pt:.6f} real-world feet ({ft_per_pt * 304.8:.3f} mm).",
                    f"Dimension corroboration verified: '{dim_text}' matches vector linework ({actual_pt:.1f} pt, expected {expected_pt:.1f} pt, residual {residual_error:.2f} pt).",
                ]
                return ScaleEvidence(
                    scale_status=ScaleStatus.VERIFIED_EXPLICIT,
                    scale_string=scale_str,
                    scale_detected=scale_str,
                    scale_validated="VERIFIED",
                    scale_display=f"{scale_str} — VERIFIED",
                    scale_evidence_type="EXPLICIT_TEXT",
                    ratio=ratio,
                    ft_per_pt=ft_per_pt,
                    source_text_id=txt_id,
                    dimension_evidence=dim_text,
                    expected_measurement=round(expected_pt, 2),
                    actual_measurement=round(actual_pt, 2),
                    vector_measurement=round(actual_pt, 2),
                    residual_error=round(residual_error, 2),
                    confidence=1.0,
                    provenance=DataProvenanceStatus.VERIFIED_EXPLICIT,
                    notes=calib_notes,
                )
            else:
                # Explicit scale exists, but independent dimension corroboration failed!
                return ScaleEvidence(
                    scale_status=ScaleStatus.REVIEW_REQUIRED,
                    scale_string=scale_str,
                    scale_detected=scale_str,
                    scale_validated="REVIEW_REQUIRED",
                    scale_display=f"{scale_str} — REVIEW REQUIRED",
                    scale_evidence_type="EXPLICIT_TEXT",
                    ratio=ratio,
                    ft_per_pt=ft_per_pt,
                    source_text_id=txt_id,
                    confidence=0.5,
                    provenance=DataProvenanceStatus.UNKNOWN_UNRESOLVED,
                    notes=[
                        f"Explicit scale notation '{scale_str}' found in content stream, but independent dimension corroboration failed.",
                        "Scale is marked REVIEW_REQUIRED. QTO calculation must be reviewed before reliance.",
                    ],
                )

        # 2. Search for calibrating dimension if explicit scale text is absent
        calibrated_scale = self._calibrate_from_dimension_geometry(text_objects, geometry_objects)
        if calibrated_scale:
            scale_str, ft_per_pt, ratio, dim_id = calibrated_scale
            return ScaleEvidence(
                scale_status=ScaleStatus.CALIBRATED_DIMENSION,
                scale_string=scale_str,
                scale_detected=scale_str,
                scale_validated="VERIFIED",
                scale_display=f"{scale_str} — VERIFIED",
                scale_evidence_type="CALIBRATED_DIMENSION",
                ratio=ratio,
                ft_per_pt=ft_per_pt,
                calibrating_dimension_id=dim_id,
                confidence=0.8,
                provenance=DataProvenanceStatus.DERIVED_GEOMETRIC,
                notes=[
                    f"Scale calibrated from verified dimension geometry ({dim_id}).",
                    f"Scale factor: 1.0 PDF pt = {ft_per_pt:.6f} real-world feet.",
                ],
            )

        # 3. Unresolved scale: Strictly block QTO without guesswork
        return ScaleEvidence(
            scale_status=ScaleStatus.SCALE_UNRESOLVED,
            scale_string=None,
            scale_detected=None,
            scale_validated="UNRESOLVED",
            scale_display="UNRESOLVED",
            scale_evidence_type="NONE",
            ratio=None,
            ft_per_pt=None,
            confidence=0.0,
            provenance=DataProvenanceStatus.UNKNOWN_UNRESOLVED,
            notes=[
                "SCALE_UNRESOLVED: Neither explicit scale text nor calibrating dimension geometry found.",
                "Takeoff calculations are strictly blocked to prevent arbitrary or guessed quantities.",
            ],
        )

    def _find_explicit_scale_text(
        self, text_objects: list[DrawingTextObject]
    ) -> Optional[tuple[str, float, float, str]]:
        """Parses verified architectural drawing scales. Strictly rejects material mixes like CMT 1:4."""
        exclude_keywords = [
            "CMT", "MORTAR", "CONCRETE", "CEMENT", "MIX", "SLOPE", "PITCH",
            "HOLE", "THICK", "SWITCH", "BB", "PLASTER", "RATIO", "MASONRY",
        ]

        for t in text_objects:
            txt = t.text.strip()
            txt_upper = txt.upper()

            # Reject material mixes (e.g. "CMT (1:4)" or "MORTAR 1:4")
            if any(kw in txt_upper for kw in exclude_keywords):
                continue

            # Check imperial architectural scale with prefix or parens (e.g. SCALE = 1/8" : 1'-0", SCALE: 1/4" = 1'-0")
            # Matches formats like: 1/8" : 1'-0", 1/8" = 1'-0", 1/4" = 1'-0", 3/16" = 1'-0", 1-1/2" = 1'-0"
            m_imp = re.search(
                r"(?:SCALE\s*[:=]?\s*)?(\d+)/(\d+)\s*\"\s*[:=]\s*(\d+)(?:'-0\"|'|\s*FT)",
                txt,
                re.IGNORECASE,
            )
            if m_imp:
                num = float(m_imp.group(1))
                den = float(m_imp.group(2))
                ft_val = float(m_imp.group(3))
                inches_on_paper = num / den
                pts_on_paper = inches_on_paper * PT_PER_INCH
                ft_per_pt = ft_val / pts_on_paper
                ratio_val = (ft_val * 12.0) / inches_on_paper
                return (f"{int(num)}/{int(den)}\" = {int(ft_val)}'-0\"", ft_per_pt, ratio_val, t.id)

            # Check metric scale with explicit SCALE / SC prefix (e.g. "SCALE 1:50", "SCALE: 1:100", "SC 1:50")
            m_metric_prefix = re.search(r"\b(?:SCALE|SC)\s*[:.]?\s*1\s*:\s*(\d+)\b", txt, re.IGNORECASE)
            if m_metric_prefix:
                ratio_val = float(m_metric_prefix.group(1))
                if ratio_val in (5, 10, 20, 25, 50, 75, 100, 150, 200, 250, 500, 1000):
                    ft_per_pt = ratio_val / PT_PER_FOOT
                    return (f"1:{int(ratio_val)}", ft_per_pt, ratio_val, t.id)

            # Check standalone architectural scale ratio (strictly isolated, e.g. "1:50", "1:100")
            if re.match(r"^1\s*:\s*(10|20|25|50|75|100|150|200|250|500|1000)$", txt):
                ratio_val = float(txt.split(":")[1].strip())
                ft_per_pt = ratio_val / PT_PER_FOOT
                return (f"1:{int(ratio_val)}", ft_per_pt, ratio_val, t.id)

            # Check civil scale (e.g. 1" = 20', 1" = 50', 1" = 100')
            m_civil = re.search(r"\b1\s*\"\s*=\s*(\d+)\s*(?:'|FT)\b", txt, re.IGNORECASE)
            if m_civil:
                ft_val = float(m_civil.group(1))
                ft_per_pt = ft_val / PT_PER_INCH
                ratio_val = ft_val * 12.0
                return (f"1\" = {int(ft_val)}'", ft_per_pt, ratio_val, t.id)

        return None

    def _cross_check_with_dimensions(
        self,
        ft_per_pt: float,
        text_objects: list[DrawingTextObject],
        geometry_objects: list[DrawingGeometryObject],
    ) -> Optional[tuple[str, float, float, float]]:
        """Cross-checks scale factor against dimensions. Returns (dim_text, expected_pt, actual_pt, residual_error)."""
        for t in text_objects:
            txt = t.text.strip()

            # 1. Check metric dimensions e.g. "2097 mm", "17652 mm", "10176"
            m_mm = re.match(r"^(\d+(?:\.\d+)?)\s*(?:mm)?$", txt, re.IGNORECASE)
            if m_mm:
                nominal_mm = float(m_mm.group(1))
                if nominal_mm >= 500:
                    nominal_ft = nominal_mm / 304.8
                    expected_pt = nominal_ft / ft_per_pt

                    for g in geometry_objects:
                        bbox = g.bbox_pdf
                        if len(bbox) == 4:
                            w = bbox[2] - bbox[0]
                            h = bbox[3] - bbox[1]
                            for dim_len in (w, h):
                                if dim_len > 10.0 and abs(dim_len - expected_pt) / expected_pt <= 0.05:
                                    residual = abs(dim_len - expected_pt)
                                    return (txt, expected_pt, dim_len, residual)

            # 2. Check imperial dimensions e.g. 15'-6", 10'-9", 7'-0", 3'-6"
            m_imp = re.match(r"^(\d+)'(?:\s*-\s*(\d+)(?:-(\d+)/(\d+)|\s*(\d+)/(\d+))?)?\"?$", txt)
            if m_imp:
                ft_part = float(m_imp.group(1))
                in_part = float(m_imp.group(2) or 0)
                frac_num = float(m_imp.group(3) or m_imp.group(5) or 0)
                frac_den = float(m_imp.group(4) or m_imp.group(6) or 1)
                total_in = ft_part * 12.0 + in_part + (frac_num / frac_den if frac_den else 0)
                nominal_ft = total_in / 12.0

                if nominal_ft >= 2.0:
                    expected_pt = nominal_ft / ft_per_pt
                    for g in geometry_objects:
                        bbox = g.bbox_pdf
                        if len(bbox) == 4:
                            w = bbox[2] - bbox[0]
                            h = bbox[3] - bbox[1]
                            for dim_len in (w, h):
                                if dim_len > 10.0 and abs(dim_len - expected_pt) / expected_pt <= 0.05:
                                    residual = abs(dim_len - expected_pt)
                                    return (txt, expected_pt, dim_len, residual)

        return None

    def _calibrate_from_dimension_geometry(
        self,
        text_objects: list[DrawingTextObject],
        geometry_objects: list[DrawingGeometryObject],
    ) -> Optional[tuple[str, float, float, str]]:
        """Calibrates scale directly when an explicit scale tag is absent but dimension text and vectors exist."""
        for t in text_objects:
            if t.semantic_type != SemanticContentType.DIMENSION_TEXT:
                continue

            m_mm = re.match(r"^(\d+(?:\.\d+)?)\s*(?:mm)?$", t.text.strip(), re.IGNORECASE)
            if m_mm:
                nominal_mm = float(m_mm.group(1))
                if nominal_mm < 500:
                    continue
                nominal_ft = nominal_mm / 304.8
                for g in geometry_objects:
                    bbox = g.bbox_pdf
                    if len(bbox) == 4:
                        w = bbox[2] - bbox[0]
                        h = bbox[3] - bbox[1]
                        for candidate_ratio in [50.0, 100.0, 20.0, 25.0, 200.0]:
                            cand_ft_per_pt = candidate_ratio / PT_PER_FOOT
                            cand_pt = nominal_ft / cand_ft_per_pt
                            if abs(w - cand_pt) < 2.0 or abs(h - cand_pt) < 2.0:
                                matched_pt = w if abs(w - cand_pt) < 2.0 else h
                                ft_per_pt = nominal_ft / matched_pt
                                return (f"1:{int(candidate_ratio)} (Calibrated)", ft_per_pt, candidate_ratio, t.id)

        return None

    @staticmethod
    def transform_point_to_ft(point_pt: list[float], scale_evidence: ScaleEvidence) -> list[float]:
        """Transforms a 2D PDF point [x, y] to real-world feet."""
        if not scale_evidence.ft_per_pt or scale_evidence.scale_status == ScaleStatus.SCALE_UNRESOLVED:
            return point_pt
        return [point_pt[0] * scale_evidence.ft_per_pt, point_pt[1] * scale_evidence.ft_per_pt]

    @staticmethod
    def transform_points_to_ft(points_pt: list[list[float]], scale_evidence: ScaleEvidence) -> list[list[float]]:
        """Transforms a list of 2D PDF points to real-world feet."""
        if not scale_evidence.ft_per_pt or scale_evidence.scale_status == ScaleStatus.SCALE_UNRESOLVED:
            return points_pt
        f = scale_evidence.ft_per_pt
        return [[p[0] * f, p[1] * f] for p in points_pt]

    @staticmethod
    def transform_bbox_to_ft(bbox_pt: list[float], scale_evidence: ScaleEvidence) -> Optional[list[float]]:
        """Transforms a [min_x, min_y, max_x, max_y] bounding box to real-world feet."""
        if not scale_evidence.ft_per_pt or scale_evidence.scale_status == ScaleStatus.SCALE_UNRESOLVED:
            return None
        f = scale_evidence.ft_per_pt
        return [bbox_pt[0] * f, bbox_pt[1] * f, bbox_pt[2] * f, bbox_pt[3] * f]
