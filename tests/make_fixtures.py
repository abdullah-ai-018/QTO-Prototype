"""make_fixtures.py: Programmatic Vector Blueprint PDF Generator.

Constructs realistic synthetic architectural blueprint PDFs using PyMuPDF (fitz)
for deterministic offline testing of the Drywall QTO prototype.

Fixtures generated:
1. fixture_wall20.pdf: A 20ft straight partition wall (180 pt vector at 1/8" = 1'-0" scale),
   10ft height specification, tagged "1A".
2. fixture_door.pdf: A 20ft partition wall with a 3ft door opening (27 pt gap),
   swing arc, tagged "1A".
3. fixture_lumber.pdf: Plan containing framing lumber callouts "2X4" and "2X6"
   alongside legitimate wall tags "1A" and "2B" to verify negative lookahead.
4. fixture_scale.pdf: Plan with explicit architectural title block scale "Scale: 1/8\" = 1'-0\""
   and various standard scale notations.
5. fixture_multiwall.pdf: Multi-wall floor plan with intersecting T-junctions and corner joints.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
import pymupdf


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _draw_tag_callout(
    page: pymupdf.Page,
    center_x: float,
    center_y: float,
    tag: str,
    radius: float = 12.0,
    leader_target: tuple[float, float] | None = None,
) -> None:
    """Draws a vector hexagonal callout box enclosing a tag string and optional leader line."""
    # Draw hexagonal callout polygon
    num_points = 6
    vertices = []
    for i in range(num_points):
        angle = math.radians(60 * i + 30)
        vx = center_x + radius * math.cos(angle)
        vy = center_y + radius * math.sin(angle)
        vertices.append(pymupdf.Point(vx, vy))

    shape = page.new_shape()
    shape.draw_polyline(vertices + [vertices[0]])
    shape.finish(color=(0.1, 0.1, 0.1), fill=(0.95, 0.95, 0.95), width=0.8)

    # Leader line if target provided
    if leader_target is not None:
        tx, ty = leader_target
        # start leader slightly outside callout boundary towards target
        dx = tx - center_x
        dy = ty - center_y
        dist = math.hypot(dx, dy)
        if dist > 0:
            sx = center_x + (dx / dist) * radius
            sy = center_y + (dy / dist) * radius
            shape.draw_line(pymupdf.Point(sx, sy), pymupdf.Point(tx, ty))
            shape.finish(color=(0.1, 0.1, 0.1), width=0.75)

    shape.commit()

    # Draw tag text centered in callout
    fontsize = 8.5
    # approximate centering
    text_x = center_x - (len(tag) * fontsize * 0.3)
    text_y = center_y + (fontsize * 0.35)
    page.insert_text(
        pymupdf.Point(text_x, text_y),
        tag,
        fontsize=fontsize,
        color=(0, 0, 0),
        fontname="helv",
    )


def _draw_quarter_circle_arc(
    shape: pymupdf.Shape,
    center_x: float,
    center_y: float,
    radius: float,
    start_angle_deg: float,
) -> None:
    """Draws a 90-degree circular arc using a cubic Bezier curve."""
    # Bezier approximation factor for 90 degrees: k = 4*(sqrt(2)-1)/3
    k = 0.5522847498307935 * radius
    rad = math.radians(start_angle_deg)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)

    # 4 control points in local frame (from (R, 0) to (0, R))
    p0 = pymupdf.Point(center_x + radius * cos_a, center_y + radius * sin_a)
    p1 = pymupdf.Point(center_x + radius * cos_a - k * sin_a, center_y + radius * sin_a + k * cos_a)
    p2 = pymupdf.Point(center_x - k * cos_a - radius * sin_a, center_y - k * sin_a + radius * cos_a)
    p3 = pymupdf.Point(center_x - radius * sin_a, center_y + radius * cos_a)

    shape.draw_bezier(p0, p1, p2, p3)


def make_wall20_fixture(output_path: Path) -> Path:
    """Generates fixture_wall20.pdf:

    - 20ft straight partition wall drawn at 1/8" = 1'-0" scale (180 pt vector).
    - Double face lines separated by 4 pt wall thickness.
    - 10ft height specification.
    - Tagged "1A" with callout and leader.
    """
    doc = pymupdf.open()
    page = doc.new_page(width=1000, height=800)

    # Title block & notes
    page.insert_text(pymupdf.Point(50, 50), "PROJECT: QTO SYNTHETIC BLUEPRINT TEST SUITE", fontsize=14, fontname="helv")
    page.insert_text(pymupdf.Point(50, 70), 'SHEET A-101: FLOOR PLAN - 20FT PARTITION', fontsize=11, fontname="helv")
    page.insert_text(pymupdf.Point(50, 90), 'SCALE: 1/8" = 1\'-0"', fontsize=10, fontname="helv")

    # Schedule / Assembly specification text block
    schedule_text = (
        "PARTITION SCHEDULE\n"
        "TAG: 1A\n"
        "DESCRIPTION: 3-5/8\" METAL STUDS @ 16\" O.C. WITH 1 LAYER 5/8\" TYPE X GWB EACH SIDE.\n"
        "HEIGHT: 10'-0\" AFF TO UNDERSIDE OF DECK.\n"
        "FINISH: LEVEL 4 FINISH BOTH SIDES.\n"
    )
    page.insert_text(pymupdf.Point(50, 140), schedule_text, fontsize=9, fontname="helv")

    # 20ft wall drawn at 1/8" = 1'-0" scale (9.0 pt/ft -> 20ft = 180 pt)
    # Start: x=200, y=350. End: x=380, y=350. Thickness=4 pt.
    x_start = 200.0
    x_end = 380.0
    y_top = 350.0
    y_bot = 354.0

    shape = page.new_shape()
    # Top face line
    shape.draw_line(pymupdf.Point(x_start, y_top), pymupdf.Point(x_end, y_top))
    # Bottom face line
    shape.draw_line(pymupdf.Point(x_start, y_bot), pymupdf.Point(x_end, y_bot))
    # End caps
    shape.draw_line(pymupdf.Point(x_start, y_top), pymupdf.Point(x_start, y_bot))
    shape.draw_line(pymupdf.Point(x_end, y_top), pymupdf.Point(x_end, y_bot))
    shape.finish(color=(0, 0, 0), width=1.0)
    shape.commit()

    # Tag callout at (290, 300) with leader pointing to (290, 350)
    _draw_tag_callout(page, center_x=290.0, center_y=300.0, tag="1A", radius=12.0, leader_target=(290.0, 350.0))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path, garbage=4, deflate=True)
    doc.close()
    return output_path


def make_door_fixture(output_path: Path) -> Path:
    """Generates fixture_door.pdf:

    - 20ft partition wall with 3ft door opening (27 pt gap) at 1/8" = 1'-0" scale.
    - Two 8.5ft segments (76.5 pt each) on either side of 3ft door (27 pt gap).
    - Door leaf line and quarter-circle door swing arc.
    - Tagged "1A" with 10ft height specification.
    """
    doc = pymupdf.open()
    page = doc.new_page(width=1000, height=800)

    # Title block & notes
    page.insert_text(pymupdf.Point(50, 50), "PROJECT: QTO SYNTHETIC BLUEPRINT TEST SUITE", fontsize=14, fontname="helv")
    page.insert_text(pymupdf.Point(50, 70), 'SHEET A-102: FLOOR PLAN - 20FT PARTITION WITH 3FT DOOR', fontsize=11, fontname="helv")
    page.insert_text(pymupdf.Point(50, 90), 'SCALE: 1/8" = 1\'-0"', fontsize=10, fontname="helv")

    schedule_text = (
        "PARTITION SCHEDULE\n"
        "TAG: 1A\n"
        "DESCRIPTION: 3-5/8\" METAL STUDS @ 16\" O.C. WITH 1 LAYER 5/8\" TYPE X GWB EACH SIDE.\n"
        "HEIGHT: 10'-0\" AFF.\n"
        "DOOR OPENING: 3'-0\" X 7'-0\" HOLLOW METAL DOOR.\n"
    )
    page.insert_text(pymupdf.Point(50, 140), schedule_text, fontsize=9, fontname="helv")

    # Geometry:
    # Segment 1: x in [200.0, 276.5] (length 76.5 pt = 8.5 ft)
    # Opening:   x in [276.5, 303.5] (length 27.0 pt = 3.0 ft)
    # Segment 2: x in [303.5, 380.0] (length 76.5 pt = 8.5 ft)
    # Total gross span: 180.0 pt = 20.0 ft.
    y_top = 350.0
    y_bot = 354.0

    shape = page.new_shape()
    # Segment 1
    shape.draw_line(pymupdf.Point(200.0, y_top), pymupdf.Point(276.5, y_top))
    shape.draw_line(pymupdf.Point(200.0, y_bot), pymupdf.Point(276.5, y_bot))
    shape.draw_line(pymupdf.Point(200.0, y_top), pymupdf.Point(200.0, y_bot))
    shape.draw_line(pymupdf.Point(276.5, y_top), pymupdf.Point(276.5, y_bot))

    # Segment 2
    shape.draw_line(pymupdf.Point(303.5, y_top), pymupdf.Point(380.0, y_top))
    shape.draw_line(pymupdf.Point(303.5, y_bot), pymupdf.Point(380.0, y_bot))
    shape.draw_line(pymupdf.Point(303.5, y_top), pymupdf.Point(303.5, y_bot))
    shape.draw_line(pymupdf.Point(380.0, y_top), pymupdf.Point(380.0, y_bot))

    # Door leaf at hinge x=276.5 swinging open 90 degrees downward (+y)
    door_hinge = pymupdf.Point(276.5, y_bot)
    door_leaf_end = pymupdf.Point(276.5, y_bot + 27.0)
    shape.draw_line(door_hinge, door_leaf_end)

    # Door swing quarter-circle arc from leaf end (276.5, 381.0) to strike jamb (303.5, 354.0)
    # Arc center is at hinge (276.5, 354.0), radius = 27.0
    # From angle 90 deg (down) to angle 0 deg (right)
    k = 0.55228475 * 27.0
    p0 = door_leaf_end  # (276.5, 381.0)
    p1 = pymupdf.Point(276.5 + k, y_bot + 27.0)
    p2 = pymupdf.Point(276.5 + 27.0, y_bot + k)
    p3 = pymupdf.Point(276.5 + 27.0, y_bot)  # (303.5, 354.0)
    shape.draw_bezier(p0, p1, p2, p3)

    shape.finish(closePath=False, color=(0, 0, 0), width=1.0)
    shape.commit()

    # Tag callout pointing to Segment 1
    _draw_tag_callout(page, center_x=238.25, center_y=300.0, tag="1A", radius=12.0, leader_target=(238.25, y_top))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path, garbage=4, deflate=True)
    doc.close()
    return output_path


def make_lumber_fixture(output_path: Path) -> Path:
    """Generates fixture_lumber.pdf:

    - Blueprint containing framing lumber callouts "2X4" and "2X6"
      alongside legitimate partition wall tags "1A" and "2B".
    - Used to verify negative lookahead in tag extraction regex.
    """
    doc = pymupdf.open()
    page = doc.new_page(width=1000, height=800)

    # Title block
    page.insert_text(pymupdf.Point(50, 50), "PROJECT: QTO SYNTHETIC BLUEPRINT TEST SUITE", fontsize=14, fontname="helv")
    page.insert_text(pymupdf.Point(50, 70), 'SHEET A-103: FRAMING PLAN WITH LUMBER CALLOUTS', fontsize=11, fontname="helv")
    page.insert_text(pymupdf.Point(50, 90), 'SCALE: 1/8" = 1\'-0"', fontsize=10, fontname="helv")

    # Schedule notes with both wall tags and lumber notes
    schedule_text = (
        "GENERAL FRAMING NOTES & SCHEDULE\n"
        "1. WALL TAG 1A: 3-5/8\" METAL STUDS @ 16\" O.C. WITH 5/8\" TYPE X GWB.\n"
        "2. WALL TAG 2B: 6\" METAL STUDS @ 16\" O.C. WITH 5/8\" TYPE X GWB.\n"
        "3. PROVIDE 2X4 WOOD BLOCKING FOR ALL WALL-MOUNTED CASEWORK.\n"
        "4. PROVIDE 2X6 WOOD BLOCKING FOR GRAB BARS AND TOILET ACCESSORIES.\n"
        "5. 2X4 STUDS @ 24\" O.C. AT CHASE WALL INFILL.\n"
        "6. 2X6 HEADER OVER EQUIPMENT OPENING.\n"
    )
    page.insert_text(pymupdf.Point(50, 140), schedule_text, fontsize=9, fontname="helv")

    # Wall 1: tagged "1A" (x: 200 -> 380, y: 320 -> 324)
    shape = page.new_shape()
    shape.draw_line(pymupdf.Point(200, 320), pymupdf.Point(380, 320))
    shape.draw_line(pymupdf.Point(200, 324), pymupdf.Point(380, 324))
    shape.draw_line(pymupdf.Point(200, 320), pymupdf.Point(200, 324))
    shape.draw_line(pymupdf.Point(380, 320), pymupdf.Point(380, 324))

    # Wall 2: tagged "2B" (x: 200 -> 380, y: 460 -> 466, 6 pt thickness)
    shape.draw_line(pymupdf.Point(200, 460), pymupdf.Point(380, 460))
    shape.draw_line(pymupdf.Point(200, 466), pymupdf.Point(380, 466))
    shape.draw_line(pymupdf.Point(200, 460), pymupdf.Point(200, 466))
    shape.draw_line(pymupdf.Point(380, 460), pymupdf.Point(380, 466))
    shape.finish(color=(0, 0, 0), width=1.0)
    shape.commit()

    # Valid wall tags with callouts and leaders
    _draw_tag_callout(page, center_x=290, center_y=280, tag="1A", radius=12.0, leader_target=(290, 320))
    _draw_tag_callout(page, center_x=290, center_y=420, tag="2B", radius=12.0, leader_target=(290, 460))

    # Bare lumber callout text notes near drawing (NOT wall tags)
    page.insert_text(pymupdf.Point(220, 360), '2X4 BLOCKING IN WALL', fontsize=8, fontname="helv")
    page.insert_text(pymupdf.Point(220, 500), '2X6 SILL PLATE BELOW', fontsize=8, fontname="helv")
    page.insert_text(pymupdf.Point(400, 320), '2X4 @ 16" O.C.', fontsize=8, fontname="helv")
    page.insert_text(pymupdf.Point(400, 460), '2X6 @ 24" O.C.', fontsize=8, fontname="helv")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path, garbage=4, deflate=True)
    doc.close()
    return output_path


def make_scale_fixture(output_path: Path) -> Path:
    """Generates fixture_scale.pdf:

    - Architectural title block with explicit scale string 'Scale: 1/8" = 1'-0"'.
    - Contains additional detail scale callouts (1/4" = 1'-0", 3/16" = 1'-0", 1" = 20').
    - Graphical scale bar with calibrated 1-inch increments.
    """
    doc = pymupdf.open()
    page = doc.new_page(width=1000, height=800)

    # Title block in lower right / top headers
    page.insert_text(pymupdf.Point(50, 50), "PROJECT: QTO SYNTHETIC BLUEPRINT TEST SUITE", fontsize=14, fontname="helv")
    page.insert_text(pymupdf.Point(50, 75), 'TITLE BLOCK DETAILS & SCALE SPECIFICATION', fontsize=11, fontname="helv")

    # Primary architectural scale string
    page.insert_text(pymupdf.Point(50, 120), 'PRIMARY PLAN SCALE: 1/8" = 1\'-0"', fontsize=12, fontname="helv")

    # Additional standard scale strings for parsing tests
    scales_text = (
        "ARCHITECTURAL SCALES CATALOG:\n"
        "1. FLOOR PLAN: Scale: 1/8\" = 1'-0\"\n"
        "2. ENLARGED RESTROOM: Scale: 1/4\" = 1'-0\"\n"
        "3. WALL SECTION DETAIL: Scale: 3/16\" = 1'-0\"\n"
        "4. CIVIL SITE PLAN: Scale: 1\" = 20'\n"
        "5. METRIC PLAN: Scale: 1:100\n"
    )
    page.insert_text(pymupdf.Point(50, 160), scales_text, fontsize=10, fontname="helv")

    # Graphical scale bar (72 pt = 1 inch = 8 feet at 1/8" = 1'-0")
    # Draw scale bar line from x=50 to x=338 (4 inches = 288 pt = 32 ft)
    shape = page.new_shape()
    y_bar = 320.0
    shape.draw_line(pymupdf.Point(50, y_bar), pymupdf.Point(338, y_bar))
    # Major ticks every 72 pt (8 ft)
    for i in range(5):
        tx = 50.0 + i * 72.0
        shape.draw_line(pymupdf.Point(tx, y_bar - 6.0), pymupdf.Point(tx, y_bar + 6.0))
    # Minor ticks every 36 pt (4 ft)
    for i in range(4):
        tx = 50.0 + i * 72.0 + 36.0
        shape.draw_line(pymupdf.Point(tx, y_bar - 3.0), pymupdf.Point(tx, y_bar + 3.0))

    shape.finish(color=(0, 0, 0), width=1.0)
    shape.commit()

    # Scale bar labels
    page.insert_text(pymupdf.Point(46, y_bar + 16), "0'", fontsize=8, fontname="helv")
    page.insert_text(pymupdf.Point(118, y_bar + 16), "8'", fontsize=8, fontname="helv")
    page.insert_text(pymupdf.Point(190, y_bar + 16), "16'", fontsize=8, fontname="helv")
    page.insert_text(pymupdf.Point(262, y_bar + 16), "24'", fontsize=8, fontname="helv")
    page.insert_text(pymupdf.Point(334, y_bar + 16), "32'", fontsize=8, fontname="helv")
    page.insert_text(pymupdf.Point(50, y_bar + 32), 'GRAPHIC SCALE: 1/8" = 1\'-0"', fontsize=9, fontname="helv")

    # Title block box in bottom-right
    shape2 = page.new_shape()
    tb_rect = pymupdf.Rect(650, 680, 950, 760)
    shape2.draw_rect(tb_rect)
    shape2.finish(color=(0, 0, 0), width=1.5)
    shape2.commit()

    page.insert_text(pymupdf.Point(660, 700), "DWG NO: A-001", fontsize=10, fontname="helv")
    page.insert_text(pymupdf.Point(660, 720), 'SCALE: 1/8" = 1\'-0"', fontsize=10, fontname="helv")
    page.insert_text(pymupdf.Point(660, 740), "DATE: 2026-11-03", fontsize=9, fontname="helv")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path, garbage=4, deflate=True)
    doc.close()
    return output_path


def make_multiwall_fixture(output_path: Path) -> Path:
    """Generates fixture_multiwall.pdf:

    - Multi-wall floor plan with intersecting T-junctions and corner joints.
    - Wall A: Horizontal 300 pt wall (33.33 ft) tagged "1A".
    - Wall B: Vertical 296 pt wall (32.89 ft) forming corner joint with Wall A, tagged "1A".
    - Wall C: Interior partition (176 pt = 19.56 ft) forming T-junction at Wall A, tagged "2B".
    - Wall D: Horizontal wall (196 pt = 21.78 ft) meeting Wall B at bottom corner, tagged "1A".
    """
    doc = pymupdf.open()
    page = doc.new_page(width=1000, height=800)

    # Title block
    page.insert_text(pymupdf.Point(50, 50), "PROJECT: QTO SYNTHETIC BLUEPRINT TEST SUITE", fontsize=14, fontname="helv")
    page.insert_text(pymupdf.Point(50, 70), 'SHEET A-104: MULTI-WALL FLOOR PLAN (T-JUNCTIONS & CORNERS)', fontsize=11, fontname="helv")
    page.insert_text(pymupdf.Point(50, 90), 'SCALE: 1/8" = 1\'-0"', fontsize=10, fontname="helv")

    schedule_text = (
        "SCHEDULE OF WALL TYPES\n"
        "TAG 1A: 3-5/8\" METAL STUDS @ 16\" O.C., 1 LAYER 5/8\" TYPE X GWB EACH SIDE. HEIGHT: 10'-0\".\n"
        "TAG 2B: 6\" CHASE WALL @ 16\" O.C., 2 LAYERS 5/8\" TYPE X GWB EACH SIDE. HEIGHT: 10'-0\".\n"
    )
    page.insert_text(pymupdf.Point(50, 130), schedule_text, fontsize=9, fontname="helv")

    shape = page.new_shape()

    # Wall A: North horizontal wall from x=200 to x=500 at y=200..204 (thickness 4 pt)
    shape.draw_line(pymupdf.Point(200, 200), pymupdf.Point(500, 200))
    shape.draw_line(pymupdf.Point(200, 204), pymupdf.Point(496, 204))  # meets Wall B inner face
    shape.draw_line(pymupdf.Point(200, 200), pymupdf.Point(200, 204))  # West end cap

    # Wall B: East vertical wall from y=200 to y=500 at x=496..500 (thickness 4 pt)
    # Outer corner at (500, 200), inner corner at (496, 204)
    shape.draw_line(pymupdf.Point(500, 200), pymupdf.Point(500, 500))  # East outer face
    shape.draw_line(pymupdf.Point(496, 204), pymupdf.Point(496, 496))  # West inner face

    # Wall C: Interior partition forming T-junction with Wall A at x=348..352, y=204 to y=380
    # Meets Wall A bottom face (continuous opposite face = GAP_INTERSECTION)
    shape.draw_line(pymupdf.Point(348, 204), pymupdf.Point(348, 380))
    shape.draw_line(pymupdf.Point(352, 204), pymupdf.Point(352, 380))
    shape.draw_line(pymupdf.Point(348, 380), pymupdf.Point(352, 380))  # Bottom end cap

    # Wall D: South horizontal wall from x=300 to x=496 at y=496..500 (thickness 4 pt)
    # Forms corner joint with Wall B
    shape.draw_line(pymupdf.Point(300, 496), pymupdf.Point(496, 496))  # North inner face
    shape.draw_line(pymupdf.Point(300, 500), pymupdf.Point(500, 500))  # South outer face
    shape.draw_line(pymupdf.Point(300, 496), pymupdf.Point(300, 500))  # West end cap

    shape.finish(color=(0, 0, 0), width=1.0)
    shape.commit()

    # Tag callouts
    # Wall A tagged "1A"
    _draw_tag_callout(page, center_x=270, center_y=160, tag="1A", radius=12.0, leader_target=(270, 200))
    # Wall B tagged "1A"
    _draw_tag_callout(page, center_x=540, center_y=350, tag="1A", radius=12.0, leader_target=(500, 350))
    # Wall C tagged "2B"
    _draw_tag_callout(page, center_x=310, center_y=300, tag="2B", radius=12.0, leader_target=(348, 300))
    # Wall D tagged "1A"
    _draw_tag_callout(page, center_x=380, center_y=540, tag="1A", radius=12.0, leader_target=(380, 500))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path, garbage=4, deflate=True)
    doc.close()
    return output_path


def build_all_fixtures(fixtures_dir: Path | None = None) -> dict[str, Path]:
    """Generates all 5 synthetic blueprint fixtures into target directory."""
    target_dir = fixtures_dir or FIXTURES_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    fixtures = {
        "wall20": make_wall20_fixture(target_dir / "fixture_wall20.pdf"),
        "door": make_door_fixture(target_dir / "fixture_door.pdf"),
        "lumber": make_lumber_fixture(target_dir / "fixture_lumber.pdf"),
        "scale": make_scale_fixture(target_dir / "fixture_scale.pdf"),
        "multiwall": make_multiwall_fixture(target_dir / "fixture_multiwall.pdf"),
    }
    return fixtures


if __name__ == "__main__":
    print(f"Building synthetic blueprint fixtures in: {FIXTURES_DIR}")
    created = build_all_fixtures()
    for name, path in created.items():
        print(f"  [OK] {name}: {path.name} ({path.stat().st_size} bytes)")
    print("All synthetic blueprint fixtures built successfully.")
