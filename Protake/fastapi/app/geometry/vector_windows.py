"""Window extraction from a PDF's own "WINDOW" vector layer, when it has
one — the same category of fix as vector_walls.py, and for the same
reason: a raster model guessing at a window symbol is strictly worse
evidence than the drafter's own layered vector data, when that data
exists.

Verified on a real commercial CAD sheet: the primary YOLO model's own
"windows" class topped out at 8.3% confidence for every real window on
this sheet — even the lowered 10% class-specific threshold (see
yolo_detector._CLASS_CONFIDENCE_OVERRIDES) couldn't clear it, so every
window on the page was silently dropped. The same PDF's own "WINDOW"
layer holds 52 line objects that cluster into exactly 16 well-separated,
evenly-spaced symbols matching the window row visible on the sheet —
a strong, unambiguous signal the raster pass never had a chance at.

Not every PDF has a usable WINDOW layer (flattened export, scan, image
upload) — `extract_window_polygons_from_layers` returns None in that case,
and callers should fall back to the YOLO pass exactly as before.
"""

import cv2
import fitz
import numpy as np

# Layers get named "WINDOW", "Window", "Windows_Pen_No__3" etc. by
# different CAD tools — matched the same way vector_walls.py matches wall
# layers, by substring rather than exact name.
_WINDOW_LAYER_SUBSTRING = "window"

# How thick to rasterize each window-layer line before clustering — needs
# to bridge the small gaps between a window symbol's own parallel strokes
# (multi-pane sash lines) without being so thick it bridges across the
# gap to a neighboring window. Matches vector_walls.py's convention.
_LINE_THICKNESS_PX = 5

# Structuring element for merging one window symbol's separate strokes
# into a single connected component. Measured on a real sheet: a window
# symbol's own lines sit within ~10px of each other, while neighboring
# window symbols are 200px+ apart — wide margin, not sensitive to exact
# value.
_BRIDGE_KERNEL_PX = 15

# A component this small is stroke-rendering noise (a stray tick mark, a
# jamb detail), not a real window symbol.
MIN_WINDOW_COMPONENT_AREA_PX = 200


def extract_window_polygons_from_layers(
    pdf_path: str, page_number: int, image_shape: tuple[int, int]
) -> list[np.ndarray] | None:
    """Pixel-space bounding-box polygons, one per window symbol found on
    the PDF's own WINDOW-named vector layer(s), or None if this PDF has no
    such layer (or can't be opened).

    Each window symbol is drawn as a cluster of nearby parallel lines (the
    sash/pane divisions); this rasterizes just that layer, bridges each
    cluster into one connected component, and returns its bounding box —
    a rectangle is the correct shape for a window opening regardless of
    how many individual pane lines the symbol happens to be drawn with.

    `page_number` is 1-indexed, matching the rest of this codebase.
    """
    try:
        doc = fitz.open(pdf_path)
        page = doc[page_number - 1]
        drawings = page.get_drawings()
    except Exception:
        return None

    window_objects = [d for d in drawings if _WINDOW_LAYER_SUBSTRING in (d.get("layer") or "").lower()]
    if not window_objects:
        return None

    h, w = image_shape
    page_w, page_h = page.rect.width, page.rect.height
    if page_w <= 0 or page_h <= 0:
        return None
    scale_x, scale_y = w / page_w, h / page_h

    mask = np.zeros(image_shape, dtype=np.uint8)
    for obj in window_objects:
        for item in obj["items"]:
            kind = item[0]
            if kind == "l":
                p1, p2 = item[1], item[2]
                cv2.line(
                    mask,
                    (int(round(p1.x * scale_x)), int(round(p1.y * scale_y))),
                    (int(round(p2.x * scale_x)), int(round(p2.y * scale_y))),
                    255,
                    _LINE_THICKNESS_PX,
                )
            elif kind == "re":
                rect = item[1]
                cv2.rectangle(
                    mask,
                    (int(round(rect.x0 * scale_x)), int(round(rect.y0 * scale_y))),
                    (int(round(rect.x1 * scale_x)), int(round(rect.y1 * scale_y))),
                    255,
                    _LINE_THICKNESS_PX,
                )
            elif kind == "c":
                p1, p4 = item[1], item[4]
                cv2.line(
                    mask,
                    (int(round(p1.x * scale_x)), int(round(p1.y * scale_y))),
                    (int(round(p4.x * scale_x)), int(round(p4.y * scale_y))),
                    255,
                    _LINE_THICKNESS_PX,
                )

    if not mask.any():
        return None

    bridge_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (_BRIDGE_KERNEL_PX, _BRIDGE_KERNEL_PX))
    bridged = cv2.dilate(mask, bridge_kernel)

    num, labels, stats, _ = cv2.connectedComponentsWithStats(bridged, connectivity=8)

    polygons: list[np.ndarray] = []
    for i in range(1, num):
        if stats[i, cv2.CC_STAT_AREA] < MIN_WINDOW_COMPONENT_AREA_PX:
            continue
        x = stats[i, cv2.CC_STAT_LEFT]
        y = stats[i, cv2.CC_STAT_TOP]
        box_w = stats[i, cv2.CC_STAT_WIDTH]
        box_h = stats[i, cv2.CC_STAT_HEIGHT]
        polygons.append(
            np.array([[x, y], [x + box_w, y], [x + box_w, y + box_h], [x, y + box_h]], dtype=np.int32)
        )

    return polygons if polygons else None
