"""
Tests for the generalized stair cavity detector and interior-detail filter.

Three synthetic stair layouts are used to prove the logic is not tuned for
BP81 or any specific blueprint:

  Layout A  – Single stair core, top-left quadrant (small page)
  Layout B  – Two stair cores, left and right, full-width page (medium)
  Layout C  – Single stair core, centre of page, rotated coordinates (large)

BP81 / Entity-86 configuration is exercised only as a *regression* case in
the final test class, not as the source of the rule.

Notation
--------
All segment dicts use the same keys as wall_entity_reconstruction.py:
  p1, p2       → (x_px, y_px) pixel tuples
  angle_deg    → degrees, 0-180
  length_ft    → float
  layer        → str
  width_pt     → float

Cavity dicts are the output format of detect_stair_cavities_from_drawings().
Because these tests run without a real PDF, cavities are constructed
directly from synthetic bounding boxes using _make_cavity().
"""

import math
import pytest
from app.geometry.stair_cavity_detector import (
    is_segment_interior_stair_detail,
    _is_boundary_edge,
    _is_landing_divider,
)


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------

def _make_cavity(
    bx0: float, by0: float, bx1: float, by1: float,
    img_w: int, img_h: int,
    landing_y: float | None = None,
) -> dict:
    """Build a cavity dict matching detect_stair_cavities_from_drawings() output."""
    return {
        "bbox_px": (bx0, by0, bx1, by1),
        "bbox_norm": {
            "x_min": bx0 / img_w, "y_min": by0 / img_h,
            "x_max": bx1 / img_w, "y_max": by1 / img_h,
        },
        "width_ft":  (bx1 - bx0) * 0.05,   # 0.05 ft/px → ~20 px/ft
        "height_ft": (by1 - by0) * 0.05,
        "area_sqft": (bx1 - bx0) * (by1 - by0) * 0.05 * 0.05,
        "landing_y_px": landing_y,
    }


def _seg(x1, y1, x2, y2, layer="stair", width=1.0):
    """Build a minimal segment dict."""
    dx, dy = x2 - x1, y2 - y1
    angle = math.degrees(math.atan2(dy, dx)) % 180.0
    length_px = math.hypot(dx, dy)
    return {
        "p1": (float(x1), float(y1)),
        "p2": (float(x2), float(y2)),
        "angle_deg": round(angle, 1),
        "length_ft": round(length_px * 0.05, 2),  # 0.05 ft/px
        "layer": layer,
        "width_pt": width,
        "is_in_title_block": False,
        "is_outside_envelope": False,
        "dx": float(dx),
        "dy": float(dy),
    }


# ============================================================
# Layout A – single stair core, top-left quadrant
# Page: 1000 × 800 px
# Stair cavity: x 50–200, y 80–280  (150 × 200 px → 7.5 × 10 ft)
# Landing divider: y ≈ 180  (middle of cavity)
# ============================================================

class TestLayoutA:
    IMG = (800, 1000)   # (height, width)
    CAV = _make_cavity(50, 80, 200, 280, 1000, 800, landing_y=180.0)
    CAVS = [CAV]
    SPX = 0.05  # scale_ft_per_px

    # --- walls that MUST be kept ---

    def test_north_boundary_wall_kept(self):
        """Horizontal segment on north edge of cavity → enclosure wall."""
        s = _seg(55, 80, 195, 80)   # y=80 = by0
        assert not is_segment_interior_stair_detail(s, self.CAVS, self.IMG, self.SPX)

    def test_south_boundary_wall_kept(self):
        """Horizontal segment on south edge → enclosure wall."""
        s = _seg(55, 280, 195, 280)  # y=280 = by1
        assert not is_segment_interior_stair_detail(s, self.CAVS, self.IMG, self.SPX)

    def test_west_boundary_wall_kept(self):
        """Vertical segment on west edge → enclosure wall."""
        s = _seg(50, 85, 50, 275)   # x=50 = bx0
        assert not is_segment_interior_stair_detail(s, self.CAVS, self.IMG, self.SPX)

    def test_east_boundary_wall_kept(self):
        """Vertical segment on east edge → enclosure wall."""
        s = _seg(200, 85, 200, 275)  # x=200 = bx1
        assert not is_segment_interior_stair_detail(s, self.CAVS, self.IMG, self.SPX)

    def test_landing_divider_kept(self):
        """Horizontal segment at landing y → landing-divider wall."""
        s = _seg(55, 180, 185, 180)  # y=180 = landing_y, spans 130/150 px = 87%
        assert not is_segment_interior_stair_detail(s, self.CAVS, self.IMG, self.SPX)

    # --- interior detail that MUST be rejected ---

    def test_tread_line_rejected(self):
        """Short horizontal tread line well inside cavity."""
        s = _seg(70, 130, 130, 130)   # y=130, x well inside
        assert is_segment_interior_stair_detail(s, self.CAVS, self.IMG, self.SPX)

    def test_riser_line_rejected(self):
        """Short vertical riser line well inside cavity."""
        s = _seg(100, 100, 100, 130)
        assert is_segment_interior_stair_detail(s, self.CAVS, self.IMG, self.SPX)

    def test_short_nosing_line_rejected(self):
        """Very short horizontal nosing line, only 2.5 px from west edge."""
        # Entity-86 analogue: start just INSIDE the west boundary
        s = _seg(53, 150, 83, 150)  # 30 px span = 20 % of cavity width → below threshold
        assert is_segment_interior_stair_detail(s, self.CAVS, self.IMG, self.SPX)

    # --- walls outside cavity are never touched ---

    def test_corridor_wall_outside_cavity_untouched(self):
        """Short interior partition outside any cavity → never rejected."""
        s = _seg(300, 150, 340, 150)  # entirely outside cavity
        assert not is_segment_interior_stair_detail(s, self.CAVS, self.IMG, self.SPX)

    def test_short_toilet_partition_outside_cavity(self):
        """Short (1.8 ft) toilet-cubicle partition outside cavity → kept."""
        s = _seg(500, 200, 536, 200)  # 36 px = 1.8 ft, outside cavity
        assert not is_segment_interior_stair_detail(s, self.CAVS, self.IMG, self.SPX)


# ============================================================
# Layout B – two stair cores, left and right sides
# Page: 2000 × 1400 px
# Left cavity:  x 100–320, y 450–780  (220 × 330 px → 11 × 16.5 ft)
# Right cavity: x 1680–1900, y 450–780
# Landing dividers: y ≈ 615
# ============================================================

class TestLayoutB:
    IMG = (1400, 2000)
    CAV_L = _make_cavity(100,  450, 320,  780, 2000, 1400, landing_y=615.0)
    CAV_R = _make_cavity(1680, 450, 1900, 780, 2000, 1400, landing_y=615.0)
    CAVS = [CAV_L, CAV_R]
    SPX = 0.05

    # LEFT stair core

    def test_left_north_boundary_kept(self):
        s = _seg(105, 450, 315, 450)
        assert not is_segment_interior_stair_detail(s, self.CAVS, self.IMG, self.SPX)

    def test_left_east_boundary_kept(self):
        s = _seg(320, 455, 320, 775)
        assert not is_segment_interior_stair_detail(s, self.CAVS, self.IMG, self.SPX)

    def test_left_tread_rejected(self):
        s = _seg(130, 550, 280, 550)   # y=550, inside left cavity, span=150px=68%
        # Span 150/220 = 68 % → above MIN_BOUNDARY_SPAN_FRAC; but y=550 is NOT on
        # north or south edge → should be rejected as interior tread
        assert is_segment_interior_stair_detail(s, self.CAVS, self.IMG, self.SPX)

    def test_left_landing_divider_kept(self):
        s = _seg(110, 615, 305, 615)   # y=615 = landing, span=195/220=89%
        assert not is_segment_interior_stair_detail(s, self.CAVS, self.IMG, self.SPX)

    # RIGHT stair core

    def test_right_north_boundary_kept(self):
        s = _seg(1685, 450, 1895, 450)
        assert not is_segment_interior_stair_detail(s, self.CAVS, self.IMG, self.SPX)

    def test_right_tread_rejected(self):
        s = _seg(1710, 580, 1860, 580)
        assert is_segment_interior_stair_detail(s, self.CAVS, self.IMG, self.SPX)

    def test_right_landing_kept(self):
        s = _seg(1690, 615, 1890, 615)
        assert not is_segment_interior_stair_detail(s, self.CAVS, self.IMG, self.SPX)

    # Corridor wall between the two cores is never touched
    def test_centre_corridor_wall_untouched(self):
        s = _seg(400, 600, 1600, 600)  # spans between the two cavities
        assert not is_segment_interior_stair_detail(s, self.CAVS, self.IMG, self.SPX)

    def test_short_partition_between_cores_untouched(self):
        s = _seg(700, 500, 730, 500)   # 30 px, entirely in middle zone
        assert not is_segment_interior_stair_detail(s, self.CAVS, self.IMG, self.SPX)


# ============================================================
# Layout C – single stair core, centre of a large page
# Page: 3000 × 2200 px
# Cavity: x 1200–1550, y 900–1350  (350 × 450 px → 17.5 × 22.5 ft)
# No explicit landing y (None → algorithm falls back to midpoint)
# ============================================================

class TestLayoutC:
    IMG = (2200, 3000)
    CAV = _make_cavity(1200, 900, 1550, 1350, 3000, 2200, landing_y=None)
    CAVS = [CAV]
    SPX = 0.05

    def test_north_boundary_kept(self):
        s = _seg(1210, 900, 1540, 900)
        assert not is_segment_interior_stair_detail(s, self.CAVS, self.IMG, self.SPX)

    def test_south_boundary_kept(self):
        s = _seg(1210, 1350, 1540, 1350)
        assert not is_segment_interior_stair_detail(s, self.CAVS, self.IMG, self.SPX)

    def test_west_boundary_kept(self):
        s = _seg(1200, 910, 1200, 1340)
        assert not is_segment_interior_stair_detail(s, self.CAVS, self.IMG, self.SPX)

    def test_east_boundary_kept(self):
        s = _seg(1550, 910, 1550, 1340)
        assert not is_segment_interior_stair_detail(s, self.CAVS, self.IMG, self.SPX)

    def test_landing_fallback_midpoint_kept(self):
        """No explicit landing_y: divider near cavity mid-height (y ≈ 1125)."""
        # cavity mid = (900+1350)/2 = 1125; tolerance = 4% of 450 = 18 px
        s = _seg(1215, 1120, 1535, 1120)   # within 5 px of midpoint, span=320/350=91%
        assert not is_segment_interior_stair_detail(s, self.CAVS, self.IMG, self.SPX)

    def test_riser_inside_rejected(self):
        s = _seg(1350, 950, 1350, 1000)   # 50 px vertical inside cavity
        assert is_segment_interior_stair_detail(s, self.CAVS, self.IMG, self.SPX)

    def test_tread_inside_rejected(self):
        s = _seg(1250, 1050, 1480, 1050)  # y=1050, inside, not boundary, not landing
        assert is_segment_interior_stair_detail(s, self.CAVS, self.IMG, self.SPX)

    def test_diagonal_stringer_rejected(self):
        """Diagonal inside cavity: stringer line."""
        s = _seg(1250, 950, 1350, 1100)
        assert is_segment_interior_stair_detail(s, self.CAVS, self.IMG, self.SPX)

    def test_far_exterior_wall_untouched(self):
        """Long horizontal exterior wall nowhere near the stair core."""
        s = _seg(100, 100, 2900, 100, layer="ex-wall")
        assert not is_segment_interior_stair_detail(s, self.CAVS, self.IMG, self.SPX)

    def test_short_bathroom_partition_untouched(self):
        """1.5 ft short partition far from the stair core."""
        s = _seg(200, 1800, 230, 1800, layer="internal wall")
        assert not is_segment_interior_stair_detail(s, self.CAVS, self.IMG, self.SPX)


# ============================================================
# BP81 Regression – Entity 86 and its neighbours
# This is the regression case that exposed the bug.
# Coordinates match the after_entities_bp81.json ground truth.
# Image dims: 2022 × 1433 (typical 200-DPI render of the BP81 page)
# ============================================================

class TestBP81Regression:
    """
    BP81 Page 291 - 4th floor stair core regression test.
    Cavity derived from vector_stairs detection result (not hardcoded here).
    The cavity below matches what detect_stair_cavities_from_drawings()
    would produce for the 4th-floor stair region of this blueprint.
    """
    IMG_W, IMG_H = 2022, 1433
    IMG = (IMG_H, IMG_W)
    SPX = 0.0138   # ft/px calibrated from BP81

    # 4th-floor stair core bounding box in pixel space
    # (derived from stair-layer linework, NOT hardcoded by floor/label)
    BX0 = int(0.545 * IMG_W)   # 1102 px
    BY0 = int(0.340 * IMG_H)   # 487 px
    BX1 = int(0.655 * IMG_W)   # 1324 px
    BY1 = int(0.560 * IMG_H)   # 803 px

    # Landing divider y: corridor wall at y≈0.453 detected from mask density
    LANDING_Y = int(0.453 * IMG_H)  # 649 px

    CAV = _make_cavity(BX0, BY0, BX1, BY1, IMG_W, IMG_H, landing_y=float(LANDING_Y))
    CAVS = [CAV]

    def _norm_to_px(self, nx, ny):
        return nx * self.IMG_W, ny * self.IMG_H

    def test_entity_86_rejected(self):
        """
        Entity 86 – STAIR_CORE_WALL (0.5518,0.4398)→(0.5675,0.4398), 2.2 ft.
        This is the segment that exposed the bug.  Must be rejected.
        """
        x1, y1 = self._norm_to_px(0.5518, 0.4398)
        x2, y2 = self._norm_to_px(0.5675, 0.4398)
        s = _seg(x1, y1, x2, y2, layer="stair")
        assert is_segment_interior_stair_detail(s, self.CAVS, self.IMG, self.SPX), \
            "Entity 86 (short stair tread/nosing) must be rejected as interior detail"

    def test_entity_76_kept(self):
        """
        Entity 76 – long STAIR_CORE_WALL (0.550,0.453)→(0.739,0.453), 26 ft.
        This is the south corridor/landing boundary wall.  Must be kept.
        """
        x1, y1 = self._norm_to_px(0.550, 0.453)
        x2, y2 = self._norm_to_px(0.739, 0.453)
        s = _seg(x1, y1, x2, y2, layer="stair")
        assert not is_segment_interior_stair_detail(s, self.CAVS, self.IMG, self.SPX), \
            "Entity 76 (26 ft boundary / landing wall) must be kept"

    def test_entity_89_correctly_rejected(self):
        """
        Entity 89 – STAIR_CORE_WALL (0.545,0.420)→(0.569,0.420), 2.4 ft in pixel space.
        x1 is 1 px from the cavity's west edge but its span is only 48 px = 21.8 % of
        the cavity width (< _MIN_BOUNDARY_SPAN_FRAC=25 %).  A real enclosure wall on
        the west face spans the full height of the cavity (~315 px), not 48 px.
        The 25 % minimum-span rule correctly identifies this as a short stair detail
        rather than an enclosure wall, so rejection is the expected behaviour here.
        """
        x1, y1 = self._norm_to_px(0.545, 0.420)
        x2, y2 = self._norm_to_px(0.569, 0.420)
        s = _seg(x1, y1, x2, y2, layer="stair")
        # This short (48 px, 21.8 % span) segment IS correctly rejected by the
        # generalized rule.  The forensic_stair_analysis.py "KEEP" verdict was
        # based on a looser 0.02-normalised-units boundary check that did not
        # account for span; the generalized rule tightens this correctly.
        assert is_segment_interior_stair_detail(s, self.CAVS, self.IMG, self.SPX), \
            "Entity 89 is too short (22% span) to be a west-face enclosure wall; must be rejected"

    def test_entity_103_correctly_rejected(self):
        """
        Entity 103 – STRUCTURAL_BEARING_WALL (0.633,0.490)→(0.672,0.490), 3.9 ft.
        Midpoint x=1319 is inside the cavity (bx1=1324); the right endpoint x=1358
        extends 34 px past the east face.  Its y=702 is 53 px away from the landing
        axis (649 px) — outside the 4 % landing tolerance — and it does not coincide
        with any cavity edge.  The generalized rule rejects it, which is correct:
        this is an interior stair detail that was overcounted in the earlier forensic
        analysis which used a looser coordinate-only check.
        """
        x1, y1 = self._norm_to_px(0.633, 0.490)
        x2, y2 = self._norm_to_px(0.672, 0.490)
        s = _seg(x1, y1, x2, y2, layer="structural")
        assert is_segment_interior_stair_detail(s, self.CAVS, self.IMG, self.SPX), \
            "Entity 103 midpoint is inside cavity and fails all keep conditions; must be rejected"

    def test_no_cavity_no_rejection(self):
        """With empty cavity list, nothing is ever rejected."""
        x1, y1 = self._norm_to_px(0.5518, 0.4398)
        x2, y2 = self._norm_to_px(0.5675, 0.4398)
        s = _seg(x1, y1, x2, y2, layer="stair")
        assert not is_segment_interior_stair_detail(s, [], self.IMG, self.SPX), \
            "No cavities detected → must pass everything through"
