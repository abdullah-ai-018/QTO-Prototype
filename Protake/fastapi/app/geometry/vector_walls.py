"""Wall extraction from a PDF's own vector drawing layers, when it has
them — a categorically better signal than reverse-engineering wall
thickness from a rasterized image.

`wall_band.py`'s stroke-thickness heuristic assumes walls are drawn
noticeably thicker than everything else. That holds for the illustrated
test floor plans this pipeline was tuned against, but measured false on a
real professional CAD export (ArchiCAD/GSPublisher): its wall strokes
survive only a ~7px opening before vanishing entirely (vs an assumed
~21px), and even after finding that thinner width, the linework fragments
into pieces averaging well under the minimum wall-run length — none of it
reconnects into a usable building outline no matter how it's tuned.

That same file, though, carries genuine named PDF layers: "Wall",
"EX-WALL", "Internal wall" — populated with exactly the wall geometry and
nothing else (verified: 320 objects, forming a plausible building
footprint, vs. 41,791 total drawing objects on the page). When a PDF
preserves this, filtering by layer name sidesteps the thickness-guessing
problem entirely instead of trying to guess it better.

Not every PDF has usable layers (a flattened export, a scanned drawing, an
image-only upload has none) — `extract_wall_mask_from_layers` returns None
in that case, and callers should fall back to `wall_band.py`.
"""

import cv2
import fitz
import numpy as np

import re

_WALL_LAYER_SUBSTRING = "wall"
_MIXED_STRUCTURAL_LAYER_TOKENS = ("bearing", "partition", "column", "stair")
_NON_WALL_LAYER_SUBSTRINGS = (
    "furniture", "50_furniture", "hatch", "axis", "grid", "dim", "text", "annotation", "object",
    "case", "casework", "mill", "millwork", "cabinet", "fixture", "fixt", "equip", "counter",
    "vanity", "plumb", "sanitary", "appl", "joinery", "casewk",
)

# Lineweight equality tolerance.
_STROKE_WIDTH_TOLERANCE = 0.04


def is_structural_layer(layer_name: str) -> bool:
    """Check if a layer name represents structural / partition evidence using exact tokens."""
    l = layer_name.lower().strip()
    if any(blk in l for blk in _NON_WALL_LAYER_SUBSTRINGS):
        return False
    if any(tok in l for tok in _MIXED_STRUCTURAL_LAYER_TOKENS):
        return True
    if re.search(r"\bcon\b", l):
        return True
    return False

# A vector wall line has no real-world "thickness" once rasterized — a
# mathematical line is drawn 1px wide regardless of the source stroke's
# declared width, which is far too thin for the room-detection distance
# transform to treat as a barrier. This gives it the same physical
# thickness convention already used for the illustrated-file wall mask, so
# both code paths hand `detect_room_polygons` a barrier of comparable scale.
_WALL_THICKNESS_PAGE_RATIO = 1 / 1200
_MIN_WALL_THICKNESS_PX = 3

# Small gap-closing so adjacent short segments at a corner (measured: many
# wall-layer segments are just 2-3pt long) join into one continuous run,
# without being large enough to bridge an actual door/window opening.
_CLOSE_PX = 5


def _document_wall_stroke_width(wall_objects: list[dict]) -> float | None:
    """The lineweight THIS document draws walls at, learned from the layers
    it explicitly named for walls.

    Nothing is hardcoded: the wall-named layers are a labelled sample of
    "what a wall stroke looks like here", and their most common stroke
    width is what a mixed structural layer's walls will also be drawn at,
    since it is the same drawing. Measured on the AUC sheet — `Wall` 97 of
    103 objects at 0.57, `Internal wall` 4 of 4 at 0.57, `EX-WALL` split
    56 at 0.57 / 73 at 0.37 — giving 157 votes for 0.57 against 73, so the
    mode is the wall pen even though one wall layer is itself mixed.

    Returns None when the sample is too small/absent to trust, in which
    case the caller must not widen its selection at all.
    """
    counts: dict[float, int] = {}
    for obj in wall_objects:
        width = obj.get("width")
        if width is None or width <= 0:
            continue
        key = round(float(width), 2)
        counts[key] = counts.get(key, 0) + 1
    if not counts:
        return None
    return max(counts.items(), key=lambda kv: kv[1])[0]


def _wall_thickness_px(image_shape: tuple[int, int]) -> int:
    long_edge = max(image_shape)
    size = max(_MIN_WALL_THICKNESS_PX, int(round(long_edge * _WALL_THICKNESS_PAGE_RATIO)))
    return size if size % 2 else size + 1


def extract_wall_mask_from_layers(
    pdf_path: str, page_number: int, image_shape: tuple[int, int]
) -> np.ndarray | None:
    """A wall-only binary mask built from the PDF's own wall-named vector
    layers, or None if this PDF has no such layer (or can't be opened).

    `page_number` is 1-indexed, matching the rest of this codebase
    (PyMuPDF's own page indexing is 0-indexed).
    """
    try:
        doc = fitz.open(pdf_path)
        page = doc[page_number - 1]
        drawings = page.get_drawings()
    except Exception:
        return None

    wall_objects = [
        d for d in drawings 
        if _WALL_LAYER_SUBSTRING in (d.get("layer") or "").lower()
        and not any(blk in (d.get("layer") or "").lower() for blk in _NON_WALL_LAYER_SUBSTRINGS)
    ]
    if not wall_objects:
        return None

    # Recover walls the drafter put on a mixed load-bearing/poché layer
    # instead of a wall-named one, keeping only the strokes drawn at this
    # document's own wall lineweight (see the two constants above for the
    # measured justification, and why width alone is NOT sufficient — on
    # the measured sheet `50_FURNITURE` has 11,861 objects at that very
    # same width, so the layer-name gate is what makes the width gate safe).
    wall_stroke_width = _document_wall_stroke_width(wall_objects)
    if wall_stroke_width is not None:
        for d in drawings:
            layer_name = (d.get("layer") or "").lower()
            if any(blk in layer_name for blk in _NON_WALL_LAYER_SUBSTRINGS):
                continue
            if _WALL_LAYER_SUBSTRING in layer_name:
                continue  # already taken above, at any width
            if not is_structural_layer(layer_name):
                continue
            width = d.get("width")
            if width is None:
                continue
            if abs(float(width) - wall_stroke_width) <= _STROKE_WIDTH_TOLERANCE:
                wall_objects.append(d)

    h, w = image_shape
    page_w, page_h = page.rect.width, page.rect.height
    if page_w <= 0 or page_h <= 0:
        return None
    scale_x, scale_y = w / page_w, h / page_h

    thickness = _wall_thickness_px(image_shape)
    mask = np.zeros(image_shape, dtype=np.uint8)
    for obj in wall_objects:
        for item in obj["items"]:
            kind = item[0]
            if kind == "l":
                p1, p2 = item[1], item[2]
                cv2.line(
                    mask,
                    (int(round(p1.x * scale_x)), int(round(p1.y * scale_y))),
                    (int(round(p2.x * scale_x)), int(round(p2.y * scale_y))),
                    255,
                    thickness,
                )
            elif kind == "re":
                rect = item[1]
                cv2.rectangle(
                    mask,
                    (int(round(rect.x0 * scale_x)), int(round(rect.y0 * scale_y))),
                    (int(round(rect.x1 * scale_x)), int(round(rect.y1 * scale_y))),
                    255,
                    thickness,
                )
            elif kind == "c":
                # Bezier curve — a small fillet/corner detail on a wall
                # layer, not a door swing (those live on the DOOR layer).
                # The straight chord from start to end point is a fine
                # approximation at wall scale.
                p1, p4 = item[1], item[4]
                cv2.line(
                    mask,
                    (int(round(p1.x * scale_x)), int(round(p1.y * scale_y))),
                    (int(round(p4.x * scale_x)), int(round(p4.y * scale_y))),
                    255,
                    thickness,
                )

    mask = _strip_non_wall_symbols(mask)

    close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (_CLOSE_PX, _CLOSE_PX))
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_kernel)


# A wall-named layer being "authoritative" (see room_detector's
# walls_are_authoritative) is an assumption about what the drafter put on
# it — an assumption a real file can violate. Verified on a real CAD
# export: its "EX-WALL" layer also held a floor-grate/grille symbol near
# an emergency exit, which this module drew as if it were a wall, and it
# then reached the room-detection envelope and the persisted wall list as
# a fabricated "Interior Wall" (measured 8in thick, 40% confidence) — a
# grille is compact, not a wall run.
#
# A real wall stroke is always a thin skeleton: even a masonry wall shown
# hatched to indicate its material is elongated (measured on that same
# file: hatched wall segments at aspect ratios 15-20 despite 30-42% fill),
# and a wall shown as a bare double-line outline is compact but sparse
# (measured: aspect ratios 1.2-2.5 at only 2-10% fill). The offending
# grille symbol was compact AND dense at once (aspect 1.0-2.0, fill
# 34-35%) — a combination no real wall on that sheet ever produced. Only
# that combination is excluded, so a hatched wall's density and a bare
# outline's compactness are each individually safe.
_SYMBOL_MAX_ASPECT_RATIO = 5.0
_SYMBOL_MIN_FILL_RATIO = 0.15

# A symbol is small. The aspect+fill test above describes a compact, dense
# blob — but so does a COMPLETE floor-plan wall skeleton, which is roughly
# square and moderately dense once every partition is present. Measured on
# the AUC sheet after the mixed-structural-layer recovery above started
# supplying real interior walls: the two floor plans' wall skeletons became
# the two largest components at 658x621px and 659x621px, aspect 1.06, fill
# 0.200 and 0.186 — tripping the symbol test exactly, which deleted 95% of
# the mask (184,902 -> 9,606 ink px) and silently reproduced the original
# "no interior walls" bug from the other direction.
#
# The genuine symbols this filter exists to remove (the floor-grate/grille
# in its docstring) measured 36-38px on that same page — 0.019 of the long
# edge against the building's 0.329, a ~17x separation. Anything at or
# above this share of the page is structure, not a symbol, and is never
# tested.
_SYMBOL_MAX_SIZE_PAGE_RATIO = 0.05


def _strip_non_wall_symbols(mask: np.ndarray) -> np.ndarray:
    num, labels, stats, _ = cv2.connectedComponentsWithStats((mask > 0).astype(np.uint8), connectivity=8)
    if num <= 1:
        return mask

    cleaned = mask.copy()
    max_symbol_size = max(mask.shape) * _SYMBOL_MAX_SIZE_PAGE_RATIO
    for i in range(1, num):
        box_w = stats[i, cv2.CC_STAT_WIDTH]
        box_h = stats[i, cv2.CC_STAT_HEIGHT]
        area = stats[i, cv2.CC_STAT_AREA]
        if box_w <= 0 or box_h <= 0:
            continue
        # Too big to be a symbol at all — see _SYMBOL_MAX_SIZE_PAGE_RATIO.
        if box_w > max_symbol_size or box_h > max_symbol_size:
            continue
        aspect_ratio = max(box_w, box_h) / max(1, min(box_w, box_h))
        fill_ratio = area / (box_w * box_h)
        if aspect_ratio < _SYMBOL_MAX_ASPECT_RATIO and fill_ratio > _SYMBOL_MIN_FILL_RATIO:
            cleaned[labels == i] = 0

    return cleaned
