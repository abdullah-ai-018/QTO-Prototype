"""
Scale detection and points-to-feet calibration engine.
Translates architectural scale notations (e.g., 1/8" = 1'-0") to real-world ft/pt factors.
"""

from __future__ import annotations
import re
from typing import Tuple
import pymupdf as fitz


DEFAULT_SCALE_STR = '1/8" = 1\'-0"'
DEFAULT_FT_PER_PT = 1.0 / (72.0 * 0.125)  # 0.1111111111111111 ft/pt


def parse_fraction(s: str) -> float | None:
    """Parses fraction strings like '1/8', '3/16', '1 1/2', '1-1/2', '0.125'."""
    s = s.strip()
    if not s:
        return None
    # Mixed fraction like 1-1/2 or 1 1/2
    m_mixed = re.match(r"^(\d+)\s*[- ]\s*(\d+)/(\d+)$", s)
    if m_mixed:
        whole, num, den = float(m_mixed.group(1)), float(m_mixed.group(2)), float(m_mixed.group(3))
        return whole + (num / den if den != 0 else 0.0)
    # Simple fraction like 1/8
    m_frac = re.match(r"^(\d+)/(\d+)$", s)
    if m_frac:
        num, den = float(m_frac.group(1)), float(m_frac.group(2))
        return num / den if den != 0 else None
    # Float or int
    try:
        return float(s)
    except ValueError:
        return None


def parse_scale_string(scale_str: str) -> float | None:
    """
    Parses architectural and engineering scale strings into ft_per_pt factor.
    Returns ft_per_pt (feet per PDF point) or None if unparseable.

    Examples:
    - 1/8" = 1'-0"  -> 0.11111 ft/pt (9 pt = 1 ft)
    - 1/4" = 1'-0"  -> 0.05555 ft/pt (18 pt = 1 ft)
    - 3/16" = 1'-0" -> 0.07407 ft/pt (13.5 pt = 1 ft)
    - 1" = 20'      -> 0.27778 ft/pt (72 pt = 20 ft)
    - 1:50          -> 0.16404 ft/pt
    """
    if not scale_str or not isinstance(scale_str, str):
        return None

    cleaned = scale_str.replace("“", '"').replace("”", '"').replace("’", "'").strip()

    # Pattern 1: Architectural scale: [inches]" = [feet]'-[inches]"
    # e.g., 1/8" = 1'-0", 1/4" = 1'-0", 3/16"=1'-0", 1-1/2" = 1'-0", 1/8" : 1'-0"
    m_arch = re.search(
        r'([\d\s\/\.\-]+)\s*["״]?\s*[:=]\s*(\d+)\s*[\'′]\s*(?:-\s*([\d\s\/\.\-]+)\s*["״]?)?',
        cleaned,
        re.IGNORECASE,
    )
    if m_arch:
        drawing_in_str = m_arch.group(1)
        feet_str = m_arch.group(2)
        extra_in_str = m_arch.group(3)

        drawing_in = parse_fraction(drawing_in_str)
        if drawing_in is not None and drawing_in > 0:
            feet = float(feet_str)
            if extra_in_str:
                extra_in = parse_fraction(extra_in_str) or 0.0
                feet += extra_in / 12.0
            if feet > 0:
                # drawing_in inches on paper = feet in reality
                # 1 inch on paper = 72 pt
                # 72 * drawing_in pt = feet in reality
                # ft_per_pt = feet / (72 * drawing_in)
                return feet / (72.0 * drawing_in)

    # Pattern 2: Engineering scale: 1" = [feet]'
    # e.g., 1" = 20', 1" = 10', 1" = 50'
    m_eng = re.search(r'1\s*["״]?\s*[:=]\s*(\d+(?:\.\d+)?)\s*[\'′]', cleaned, re.IGNORECASE)
    if m_eng:
        feet = float(m_eng.group(1))
        if feet > 0:
            return feet / 72.0

    # Pattern 3: Metric ratio: 1 : [ratio] (e.g., 1:50, 1:100)
    m_metric = re.search(r'\b1\s*[:/]\s*(\d+)\b', cleaned)
    if m_metric:
        ratio = float(m_metric.group(1))
        # 1 pt = 1/72 in = 25.4 / 72 mm = 0.352778 mm
        # 1 pt corresponds to ratio * 0.352778 mm
        # Convert mm to feet (1 ft = 304.8 mm):
        # feet = (ratio * 0.352778) / 304.8 = ratio / (72 * 12)
        return ratio / (72.0 * 12.0)

    # Pattern 4: Bare fraction before '= 1'-0"' or similar without quotes
    m_bare = re.search(r'(\d+/\d+)\s*=\s*1\b', cleaned)
    if m_bare:
        frac = parse_fraction(m_bare.group(1))
        if frac and frac > 0:
            return 1.0 / (72.0 * frac)

    return None


def detect_scale_from_page(
    page: fitz.Page, default_scale_str: str = DEFAULT_SCALE_STR
) -> Tuple[float, str, str]:
    """
    Scans a PDF page's text for architectural or engineering scale notes.
    Returns (ft_per_pt, matched_scale_string, status).
    Status is either 'DETECTED' or 'DEFAULT_ASSUMED'.
    """
    text = page.get_text("text")

    # Look for scale labels like:
    # SCALE: 1/8" = 1'-0"
    # SCALE: 1/4" = 1'-0"
    # SCALE 3/16" = 1'-0"
    # 1/8" = 1'-0"
    patterns = [
        r'SCALE\s*[:=\-]?\s*([0-9\/\s\-."״\'′:=]+(?:1[\'′]-0["״]?|\d+[\'′]))',
        r'(\b\d+\s*[\/-]\s*\d+\s*["״]?\s*[:=]\s*\d+\s*[\'′](?:-\s*\d+\s*["״]?)?)',
        r'(1\s*["״]?\s*[:=]\s*\d+\s*[\'′])',
        r'SCALE\s*[:=\-]?\s*1\s*[:/]\s*(\d+)',
    ]

    for pat in patterns:
        for match in re.finditer(pat, text, re.IGNORECASE):
            candidate = match.group(0).strip()
            # Clean up prefix like "SCALE:"
            sub_cand = re.sub(r'^SCALE\s*[:=\-]?\s*', '', candidate, flags=re.IGNORECASE).strip()
            factor = parse_scale_string(sub_cand)
            if factor is not None and factor > 0:
                return (factor, sub_cand, "DETECTED")

    # Fallback to default
    default_factor = parse_scale_string(default_scale_str) or DEFAULT_FT_PER_PT
    return (default_factor, default_scale_str, "DEFAULT_ASSUMED")


def pt_to_ft(pt_length: float, ft_per_pt: float) -> float:
    """Converts PDF points to real-world feet."""
    return pt_length * ft_per_pt


def ft_to_pt(ft_length: float, ft_per_pt: float) -> float:
    """Converts real-world feet to PDF points."""
    return ft_length / ft_per_pt if ft_per_pt > 0 else 0.0
