"""Stairs extraction from a PDF's own "stair" vector layer, when it has
one — similar to vector_windows.py and vector_doors.py.
"""

import cv2
import fitz
import numpy as np

# Layers get named "stair", "STAIRS", "Staircase" etc. by different CAD tools.
_STAIR_LAYER_SUBSTRING = "stair"

_LINE_THICKNESS_PX = 5
_BRIDGE_KERNEL_PX = 30
MIN_STAIR_COMPONENT_AREA_PX = 400


def extract_stairs_polygons_from_layers(
    pdf_path: str, page_number: int, image_shape: tuple[int, int]
) -> list[np.ndarray] | None:
    """Pixel-space bounding-box polygons, one per stair symbol found on
    the PDF's own stair-named vector layer(s), or None if this PDF has no
    such layer (or can't be opened).
    """
    try:
        doc = fitz.open(pdf_path)
        page = doc[page_number - 1]
        drawings = page.get_drawings()
    except Exception:
        return None

    stair_objects = [d for d in drawings if _STAIR_LAYER_SUBSTRING in (d.get("layer") or "").lower()]
    if not stair_objects:
        return None

    h, w = image_shape
    page_w, page_h = page.rect.width, page.rect.height
    if page_w <= 0 or page_h <= 0:
        return None
    scale_x, scale_y = w / page_w, h / page_h

    mask = np.zeros(image_shape, dtype=np.uint8)
    for obj in stair_objects:
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
        if stats[i, cv2.CC_STAT_AREA] < MIN_STAIR_COMPONENT_AREA_PX:
            continue
        x = stats[i, cv2.CC_STAT_LEFT]
        y = stats[i, cv2.CC_STAT_TOP]
        box_w = stats[i, cv2.CC_STAT_WIDTH]
        box_h = stats[i, cv2.CC_STAT_HEIGHT]
        polygons.append(
            np.array([[x, y], [x + box_w, y], [x + box_w, y + box_h], [x, y + box_h]], dtype=np.int32)
        )

    return polygons if polygons else None
