"""Wall extraction by stroke thickness, rather than by line detection.

Architectural drawings encode a hard distinction that the Hough transform
throws away: **walls are drawn as thick solid bands, and everything else
(furniture, fixtures, dimension strings, hatching, door swings, text) is
drawn thin**. Canny + Hough sees only "an edge is here", so it returns the
outline of a sofa with exactly the same authority as a load-bearing wall —
and since a sofa outline is a perfectly closed loop while a real room is
interrupted by doorways, a flood fill over Hough output reliably finds the
furniture and misses the rooms.

Selecting strokes by thickness inverts that: a morphological opening with a
kernel wider than the thin linework erases all of it in one pass and leaves
the wall bands standing. What remains is close to a wall skeleton, which is
what the room flood fill actually needs.

The wall *segments* used for wall quantities still come from the Hough
pipeline in line_extraction.py; this module only produces the mask that
room detection floods.
"""

import cv2
import numpy as np

# Ink is anything far enough from the page's background tone. Works for
# dark-on-white CAD output and for light-on-dark "blueprint" renderings
# alike, because it keys off distance from the modal tone rather than
# assuming a polarity.
INK_DELTA = 40

# Thin linework is erased by an opening this size. Scaled to the page so a
# sheet rasterized at a different DPI behaves the same way.
THIN_STROKE_KERNEL_PAGE_RATIO = 1 / 300
MIN_THIN_STROKE_KERNEL_PX = 3

# Openings (doors, windows, cased passages) are deliberate gaps in a wall
# run. They must be bridged or the room fill escapes through them, but only
# *along* the wall's own direction — a plain square close would fatten every
# wall and swallow narrow rooms whole.
OPENING_SEAL_PAGE_RATIO = 0.06

# If thickness selection leaves almost nothing, the drawing does not use a
# heavy/light lineweight convention (a faint scan, a sketch, a hatched-only
# sheet). Callers should fall back to the Hough-derived mask rather than
# flood a nearly empty page.
MIN_WALL_INK_SHARE = 0.004

# A connected wall-thick component spanning at least this share of the
# page's long edge is treated as an established wall run, and is protected
# from OCR text erasure below — see erase_text_regions.
PROTECTED_WALL_RUN_EXTENT_PAGE_RATIO = 0.05

DECORATIVE_BAR_ASPECT_RATIO = 8.0
DECORATIVE_BAR_FILL_RATIO = 0.9
DECORATIVE_BAR_MIN_GROUP_SIZE = 3
DECORATIVE_BAR_SIZE_TOLERANCE = 0.25  # +/-25% width/height to count as "near-identical"


def ink_mask(gray: np.ndarray, ink_delta: int = INK_DELTA) -> np.ndarray:
    """Everything drawn on the page, regardless of ink/paper polarity."""
    values, counts = np.unique(gray, return_counts=True)
    background = int(values[int(counts.argmax())])
    return ((np.abs(gray.astype(np.int16) - background) > ink_delta).astype(np.uint8)) * 255


def thin_stroke_kernel_px(image_shape: tuple[int, int]) -> int:
    size = max(MIN_THIN_STROKE_KERNEL_PX, int(round(max(image_shape) * THIN_STROKE_KERNEL_PAGE_RATIO)))
    return size if size % 2 else size + 1


def _protected_wall_run_mask(mask: np.ndarray) -> np.ndarray:
    """Pixels belonging to a connected thick-stroke component long enough to
    be an established wall run (same test as room_detector's building
    envelope), which erase_text_regions must never remove.
    """
    num, labels, stats, _ = cv2.connectedComponentsWithStats((mask > 0).astype(np.uint8), connectivity=8)
    if num <= 1:
        return np.zeros_like(mask)
    min_extent = max(mask.shape) * PROTECTED_WALL_RUN_EXTENT_PAGE_RATIO
    protected = np.zeros_like(mask)
    for i in range(1, num):
        if max(stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]) >= min_extent:
            protected[labels == i] = 255
    return protected


def erase_text_regions(mask: np.ndarray, text_boxes_px: list[tuple[float, float, float, float]]) -> np.ndarray:
    """Zero out OCR'd text bounding boxes (dilated a few px) in a wall mask —
    except pixels that belong to an established long wall run.

    Bold or underlined room-name labels are drawn thick enough to survive
    stroke-thickness selection right alongside real walls — on a verified
    plan, every printed room label produced a spurious "wall" segment this
    way, and neither length nor wall-graph connectivity could tell those
    apart from genuine short interior walls (multi-word labels like
    "KITCHEN / DINING" underline to 15+ ft, well past any short-wall cutoff).

    But a label describing a wall feature is sometimes printed running
    *along* the wall itself (e.g. "BARN DOOR" lettered vertically beside a
    sliding door, right on top of the wall it's labeling) — blanket-erasing
    its whole bounding box then erases the real wall underneath too, opening
    a gap that disconnects two rooms that should share a border. The
    distinguishing signal is the same one used for wall segments elsewhere:
    a real wall continues in a straight run well past the label; a text
    stroke doesn't. So only the parts of the bounding box that are NOT
    already part of an established long run get erased — a wall passing
    through a label's box is left standing, and only genuinely isolated
    bold/underlined text (which was never part of a long run to begin with)
    is removed.
    """
    if not text_boxes_px:
        return mask
    protected = _protected_wall_run_mask(mask)
    cleaned = mask.copy()
    h, w = mask.shape[:2]
    pad = 3
    for x1, y1, x2, y2 in text_boxes_px:
        xa, ya = max(0, int(x1) - pad), max(0, int(y1) - pad)
        xb, yb = min(w, int(x2) + pad), min(h, int(y2) + pad)
        if xb > xa and yb > ya:
            region = cleaned[ya:yb, xa:xb]
            keep = protected[ya:yb, xa:xb]
            region[keep == 0] = 0
    return cleaned


def _decorative_bar_component_ids(stats: np.ndarray, candidate_ids: list[int]) -> set[int]:
    """Identify repeated near-identical thin solid rectangle components.

    These are usually legend strips, scale bars, or decorative sheet art
    that can be mistaken for wall mask ink.
    """
    thin_solid: list[int] = []
    for i in candidate_ids:
        box_w, box_h = int(stats[i, cv2.CC_STAT_WIDTH]), int(stats[i, cv2.CC_STAT_HEIGHT])
        aspect = max(box_w, box_h) / max(1, min(box_w, box_h))
        fill = stats[i, cv2.CC_STAT_AREA] / max(1, box_w * box_h)
        if aspect >= DECORATIVE_BAR_ASPECT_RATIO and fill >= DECORATIVE_BAR_FILL_RATIO:
            thin_solid.append(i)

    decorative: set[int] = set()
    unassigned = set(thin_solid)
    while unassigned:
        seed = unassigned.pop()
        sw, sh = int(stats[seed, cv2.CC_STAT_WIDTH]), int(stats[seed, cv2.CC_STAT_HEIGHT])
        group = [seed]
        for other in list(unassigned):
            ow, oh = int(stats[other, cv2.CC_STAT_WIDTH]), int(stats[other, cv2.CC_STAT_HEIGHT])
            if (
                abs(ow - sw) <= DECORATIVE_BAR_SIZE_TOLERANCE * sw
                and abs(oh - sh) <= DECORATIVE_BAR_SIZE_TOLERANCE * sh
            ):
                group.append(other)
                unassigned.discard(other)
        if len(group) >= DECORATIVE_BAR_MIN_GROUP_SIZE:
            decorative.update(group)
    return decorative


def _remove_decorative_bars(mask: np.ndarray) -> np.ndarray:
    num, labels, stats, _ = cv2.connectedComponentsWithStats((mask > 0).astype(np.uint8), connectivity=8)
    if num <= 1:
        return mask

    candidate_ids = [i for i in range(1, num)]
    decorative = _decorative_bar_component_ids(stats, candidate_ids)
    if not decorative:
        return mask

    cleaned = mask.copy()
    for i in decorative:
        cleaned[labels == i] = 0
    return cleaned


def extract_wall_band_mask(
    gray: np.ndarray,
    seal_openings: bool = True,
    text_boxes_px: list[tuple[float, float, float, float]] | None = None,
) -> np.ndarray | None:
    """Isolate the wall bands, optionally sealing door/window openings.

    Returns None when the page has no meaningful thick linework, which is
    the signal to fall back to the line-detection mask instead of trusting
    an almost-empty result.
    """
    h, w = gray.shape[:2]
    ink = ink_mask(gray)

    kernel_px = thin_stroke_kernel_px((h, w))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_px, kernel_px))
    walls = cv2.morphologyEx(ink, cv2.MORPH_OPEN, kernel)

    if text_boxes_px:
        walls = erase_text_regions(walls, text_boxes_px)

    walls = _remove_decorative_bars(walls)

    if float((walls > 0).mean()) < MIN_WALL_INK_SHARE:
        return None

    if not seal_openings:
        return walls

    seal_px = max(3, int(round(max(h, w) * OPENING_SEAL_PAGE_RATIO)))
    horizontal = cv2.morphologyEx(walls, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (seal_px, 1)))
    vertical = cv2.morphologyEx(walls, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (1, seal_px)))

    sealed = cv2.bitwise_or(horizontal, vertical)
    return cv2.bitwise_or(sealed, walls)
