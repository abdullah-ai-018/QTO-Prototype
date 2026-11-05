"""
Generalized Stair Cavity Detector for Wall Entity Filtering.

Detects stair enclosures dynamically from a PDF page's own CAD vector
linework (the stair-named layer that every CAD tool exports) and classifies
wall segments as either:

  • boundary / enclosure walls  → keep as wall entities
  • interior stair detail        → reject (treads, risers, stringers,
                                   handrails, nosing lines, landing steps)

Design constraints
------------------
* No page-specific coordinates, floor counts, orientation labels, or
  blueprint-specific constants anywhere in this file.
* Works for any number of stair cores per page, any position, any scale,
  any PDF dimensions, any architect's layer naming convention as long as
  the word "stair" appears somewhere in the layer name (the de-facto CAD
  standard used by AutoCAD, Revit, ArchiCAD, MicroStation exports).
* Short walls elsewhere on the page are NEVER penalised — the length
  filter only applies inside a detected cavity.

Algorithm
---------
1. Collect every line/rect/curve item on a stair-named layer → rasterise
   onto a binary mask.
2. Dilate + connected-components → one bounding rectangle per stair core.
3. For each raw segment being evaluated:
   a. If its midpoint is NOT inside any cavity → pass through unchanged.
   b. If inside a cavity:
        i.  Runs coincident with a cavity edge (west/east/north/south) AND
            has significant span along that edge → BOUNDARY wall, keep.
        ii. Is near the cavity's intermediate landing-divider axis (derived
            from the density of horizontal strokes inside the cavity, not a
            hardcoded y-fraction) AND spans ≥ 40 % of cavity width → LANDING
            divider wall, keep.
        iii. Otherwise → interior stair detail, reject.
"""

from __future__ import annotations

import math
from statistics import median
from typing import Any

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Layer detection constants
# ---------------------------------------------------------------------------

# Every major CAD tool puts stair linework on a layer whose name contains
# this substring (case-insensitive).  ArchiCAD uses "staircase", Revit uses
# "Stairs", AutoCAD sheets typically "stair" or "STAIR".
_STAIR_LAYER_SUBSTR = "stair"

# Minimum area of a connected stair-layer blob before it is considered a
# real stair core (filters out stray annotation marks on the stair layer).
_MIN_STAIR_AREA_PX = 400

# Bridge kernel used to weld the individual lines of a stair symbol into
# one connected component.  30 px at 200 DPI ≈ 1.9 mm, well below tread
# depth but enough to close gaps between adjacent tread lines.
_BRIDGE_KERNEL_PX = 30
_LINE_THICKNESS_PX = 5

# ---------------------------------------------------------------------------
# Boundary-check tolerances (relative, scale-independent)
# ---------------------------------------------------------------------------

# A segment endpoint is "on" the cavity edge when it sits within this
# fraction of the cavity's shorter dimension.
_EDGE_TOL_FRAC = 0.06       # 6 % of shorter cavity dimension

# A segment must span at least this fraction of the cavity dimension
# along its own axis to count as a boundary wall (not a short tread).
_MIN_BOUNDARY_SPAN_FRAC = 0.25   # 25 % of cavity width / height

# Landing divider: search for the most-populated horizontal axis between
# 30 % and 70 % of cavity height.  A segment qualifies as a landing wall
# if its y-midpoint is within this fraction of that axis.
_LANDING_AXIS_TOL_FRAC = 0.04   # 4 % of cavity height
_MIN_LANDING_SPAN_FRAC = 0.40   # 40 % of cavity width


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_stair_cavities_from_drawings(
    drawings: list[dict],
    image_dims: tuple[int, int],
    scale_ft_per_px: float,
) -> list[dict[str, Any]]:
    """
    Detect stair enclosure bounding boxes from a page's fitz drawing objects.

    Parameters
    ----------
    drawings:
        List of drawing dicts as returned by ``fitz.Page.get_drawings()``.
    image_dims:
        ``(height, width)`` of the rasterised image (pixels).
    scale_ft_per_px:
        Calibration: feet per pixel at the rasterised resolution.

    Returns
    -------
    List of cavity dicts.  Empty list when no stair layer exists or no
    component is large enough.  Each dict has:

        bbox_px   : (x_min, y_min, x_max, y_max) in pixel coordinates
        bbox_norm : {x_min, y_min, x_max, y_max} normalised to [0, 1]
        width_ft, height_ft, area_sqft
        landing_y_px : best-estimate y-coordinate (pixels) of the
                       intermediate landing divider; None if not found.
    """
    h, w = image_dims
    stair_items = [d for d in drawings if _STAIR_LAYER_SUBSTR in (d.get("layer") or "").lower()]
    if not stair_items:
        return []

    # --- build a per-page pixel mask from stair-layer linework ---
    # We need the PDF page dimensions to map PDF points → pixels, but
    # get_drawings() items carry absolute point coordinates already at the
    # *page* coordinate system.  We need to know the PDF page size.
    # The drawings list does not carry page size directly, so we derive a
    # conservative estimate from the maximum observed coordinates.
    max_px = max_py = 1.0
    for d in stair_items:
        r = d.get("rect")
        if r:
            max_px = max(max_px, r.x1)
            max_py = max(max_py, r.y1)
        for it in d.get("items", []):
            if it[0] == "l":
                p1, p2 = it[1], it[2]
                max_px = max(max_px, p1.x, p2.x)
                max_py = max(max_py, p1.y, p2.y)

    # pdf-point → pixel scaling
    sx = w / max_px
    sy = h / max_py

    mask = np.zeros((h, w), dtype=np.uint8)

    for d in stair_items:
        for it in d.get("items", []):
            kind = it[0]
            if kind == "l":
                p1, p2 = it[1], it[2]
                cv2.line(
                    mask,
                    (int(round(p1.x * sx)), int(round(p1.y * sy))),
                    (int(round(p2.x * sx)), int(round(p2.y * sy))),
                    255, _LINE_THICKNESS_PX,
                )
            elif kind == "re":
                rect = it[1]
                cv2.rectangle(
                    mask,
                    (int(round(rect.x0 * sx)), int(round(rect.y0 * sy))),
                    (int(round(rect.x1 * sx)), int(round(rect.y1 * sy))),
                    255, _LINE_THICKNESS_PX,
                )
            elif kind == "c":
                # Bezier curve — use chord start→end
                p1, p4 = it[1], it[4]
                cv2.line(
                    mask,
                    (int(round(p1.x * sx)), int(round(p1.y * sy))),
                    (int(round(p4.x * sx)), int(round(p4.y * sy))),
                    255, _LINE_THICKNESS_PX,
                )

    if not mask.any():
        return []

    # Bridge individual tread lines into one connected blob per stair core
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (_BRIDGE_KERNEL_PX, _BRIDGE_KERNEL_PX))
    bridged = cv2.dilate(mask, kernel)

    num, _labels, stats, _ = cv2.connectedComponentsWithStats(bridged, connectivity=8)

    cavities: list[dict[str, Any]] = []
    for i in range(1, num):
        area_px = stats[i, cv2.CC_STAT_AREA]
        if area_px < _MIN_STAIR_AREA_PX:
            continue

        bx = stats[i, cv2.CC_STAT_LEFT]
        by = stats[i, cv2.CC_STAT_TOP]
        bw = stats[i, cv2.CC_STAT_WIDTH]
        bh = stats[i, cv2.CC_STAT_HEIGHT]

        x_min_px, y_min_px = bx, by
        x_max_px, y_max_px = bx + bw, by + bh

        width_ft  = bw * scale_ft_per_px
        height_ft = bh * scale_ft_per_px
        area_sqft = width_ft * height_ft

        # Minimum real stair core: at least 8 ft × 8 ft
        if area_sqft < 64:
            continue

        landing_y = _detect_landing_divider(
            mask, x_min_px, y_min_px, x_max_px, y_max_px
        )

        cavities.append({
            "bbox_px": (x_min_px, y_min_px, x_max_px, y_max_px),
            "bbox_norm": {
                "x_min": x_min_px / w,
                "y_min": y_min_px / h,
                "x_max": x_max_px / w,
                "y_max": y_max_px / h,
            },
            "width_ft":  width_ft,
            "height_ft": height_ft,
            "area_sqft": area_sqft,
            "landing_y_px": landing_y,
        })

    return cavities


def is_segment_interior_stair_detail(
    segment: dict[str, Any],
    stair_cavities: list[dict[str, Any]],
    image_dims: tuple[int, int],
    scale_ft_per_px: float,
) -> bool:
    """
    Return True when *segment* is interior stair construction detail that
    must NOT become a wall entity.

    A segment is interior detail when ALL of the following hold:
      1. Its midpoint falls strictly inside a detected stair cavity.
      2. It does NOT run coincident with a cavity boundary edge with
         sufficient span (→ enclosure wall).
      3. It is NOT a landing-divider wall spanning the cavity's middle.

    Short walls located entirely outside every detected cavity are never
    affected — no global short-wall penalty is applied.
    """
    h, w = image_dims
    x1, y1 = segment["p1"]
    x2, y2 = segment["p2"]
    x_mid = (x1 + x2) / 2.0
    y_mid = (y1 + y2) / 2.0
    angle = segment["angle_deg"]

    for cav in stair_cavities:
        bx0, by0, bx1, by1 = cav["bbox_px"]

        # 1. midpoint must be inside the cavity (strict)
        if not (bx0 < x_mid < bx1 and by0 < y_mid < by1):
            continue

        cav_w = bx1 - bx0
        cav_h = by1 - by0
        tol = max(2.0, _EDGE_TOL_FRAC * min(cav_w, cav_h))

        # 2. Is this a boundary / enclosure wall?
        if _is_boundary_edge(x1, y1, x2, y2, bx0, by0, bx1, by1, tol, angle):
            return False  # keep — enclosure wall

        # 3. Is this a landing-divider wall?
        landing_y = cav.get("landing_y_px")
        if _is_landing_divider(x1, y1, x2, y2, bx0, bx1, by0, by1, angle, landing_y):
            return False  # keep — landing wall

        # 4. Neither boundary nor landing → interior stair detail
        return True

    return False  # midpoint not in any cavity → not our concern


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_boundary_edge(
    x1: float, y1: float, x2: float, y2: float,
    bx0: float, by0: float, bx1: float, by1: float,
    tol: float,
    angle: float,
) -> bool:
    """
    True when the segment runs coincident with one of the four cavity walls
    AND spans at least _MIN_BOUNDARY_SPAN_FRAC of that wall's length.

    Both endpoints must be near the edge (within *tol* pixels) — this
    excludes short tread lines that happen to start near a corner.
    """
    cav_w = bx1 - bx0
    cav_h = by1 - by0

    is_h = angle <= 15.0 or angle >= 165.0
    is_v = 75.0 <= angle <= 105.0

    if is_h:
        # Horizontal segment → check north / south edges
        near_north = abs(y1 - by0) <= tol and abs(y2 - by0) <= tol
        near_south = abs(y1 - by1) <= tol and abs(y2 - by1) <= tol
        if not (near_north or near_south):
            return False
        span = abs(x2 - x1)
        return span >= _MIN_BOUNDARY_SPAN_FRAC * cav_w

    if is_v:
        # Vertical segment → check west / east edges
        near_west = abs(x1 - bx0) <= tol and abs(x2 - bx0) <= tol
        near_east = abs(x1 - bx1) <= tol and abs(x2 - bx1) <= tol
        if not (near_west or near_east):
            return False
        span = abs(y2 - y1)
        return span >= _MIN_BOUNDARY_SPAN_FRAC * cav_h

    # Diagonal — not a boundary edge in the axis-aligned sense; treat as
    # interior detail unless it is very long (full-height stringer).
    diag_len_px = math.hypot(x2 - x1, y2 - y1)
    return diag_len_px >= 0.75 * max(cav_w, cav_h)


def _is_landing_divider(
    x1: float, y1: float, x2: float, y2: float,
    bx0: float, bx1: float,
    by0: float, by1: float,
    angle: float,
    landing_y: float | None,
) -> bool:
    """
    True when the segment is a horizontal landing-divider wall spanning at
    least _MIN_LANDING_SPAN_FRAC of the cavity width, located near the
    detected (or estimated) landing-divider axis.
    """
    is_h = angle <= 15.0 or angle >= 165.0
    if not is_h:
        return False

    cav_w = bx1 - bx0
    cav_h = by1 - by0
    y_mid = (y1 + y2) / 2.0

    # Use detected landing axis if available; fall back to cavity midpoint.
    if landing_y is not None:
        ref_y = landing_y
    else:
        ref_y = by0 + cav_h * 0.5   # midpoint as conservative fallback

    tol_y = _LANDING_AXIS_TOL_FRAC * cav_h
    if abs(y_mid - ref_y) > tol_y:
        return False

    span = abs(x2 - x1)
    return span >= _MIN_LANDING_SPAN_FRAC * cav_w


def _detect_landing_divider(
    mask: np.ndarray,
    bx0: int, by0: int, bx1: int, by1: int,
) -> float | None:
    """
    Estimate the y-coordinate of the intermediate landing-divider wall
    inside a stair cavity by finding the most-populated horizontal scan
    line in the mask within the middle third of the cavity.

    Returns pixel y-coordinate, or None if no clear landing line is found.
    """
    cav_h = by1 - by0
    if cav_h <= 0:
        return None

    # Restrict to middle third (30 %–70 %) of cavity height to avoid
    # conflating the cavity's own top/bottom boundary with the landing.
    y_lo = by0 + int(cav_h * 0.30)
    y_hi = by0 + int(cav_h * 0.70)

    # Crop mask to cavity x-range
    sub = mask[y_lo:y_hi, bx0:bx1]
    if sub.size == 0:
        return None

    row_sums = sub.sum(axis=1)       # pixels per row
    if row_sums.max() == 0:
        return None

    best_row = int(row_sums.argmax())
    best_y = y_lo + best_row

    # Only accept if the densest row accounts for a meaningful fraction
    # of the cavity width (otherwise it's just scattered tread marks).
    density = row_sums[best_row] / (255 * max(1, bx1 - bx0))
    if density < 0.25:
        return None

    return float(best_y)
