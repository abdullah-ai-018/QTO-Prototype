"""Room boundary detection via wall-mask watershed segmentation + contour
extraction + polygon approximation.

Flood-fill (the classic approach) requires every room to be fully enclosed,
which real floor plans never are: doorways and cased openings are
deliberate gaps, so a fill starting from open space either escapes to the
exterior (erasing every room) or leaks between rooms (merging them into one
blob). Watershed instead grows one region from each room's *core* — the
part of the interior far from every wall — and lets neighboring regions
meet at the narrowest point between them, which is exactly where a doorway
is. Enclosure is no longer a requirement.
"""

import math
from typing import NamedTuple

import cv2
import numpy as np

from app.geometry.line_extraction import Segment


class RoomCandidate(NamedTuple):
    """One detected room polygon plus the evidence behind it.

    `wall_verified` is False when at least one edge is a synthetic cut
    between OCR label positions rather than a real wall (see
    _split_region_by_label_seeds). `wall_contact` is the share of the
    polygon's outline that actually sits against wall ink (see
    contour_wall_contact) — the answer to "is this rectangle bounded by
    architectural walls?", which is what separates a real room from a
    title block, a notes box, or an open exterior slab.
    """

    points: np.ndarray
    wall_verified: bool
    wall_contact: float

MIN_WALL_MASK_THICKNESS_PX = 3
MAX_ROOM_AREA_RATIO = 0.40
POLY_APPROX_EPSILON_RATIO = 0.008

# CAD-drafted rooms are built from walls meeting at true right angles, but
# raster contouring (pixelated wall mask -> findContours -> approxPolyDP)
# leaves edges a few tenths of a degree off axis and corners that don't
# quite land on a shared line. That noise is exactly what makes our room
# outlines look hand-drawn/jagged next to a mature tool's crisp rectangles —
# the underlying room boundaries were already correct, they just weren't
# snapped straight. An edge within this many degrees of horizontal/vertical
# (relative to the building's own dominant orientation, not the page's) is
# assumed to BE horizontal/vertical and is snapped exactly; a real angled
# wall (rare, but they exist) is intentionally left alone by using a small
# threshold rather than forcing every edge to an axis.
ORTHOGONAL_SNAP_MAX_ANGLE_DEG = 12.0
ORTHOGONAL_SNAP_ITERATIONS = 4

# Thickness of the axis-aligned seed stripes the label-split watershed
# starts from (see _split_region_by_label_seeds). Only needs to be thick
# enough to survive rasterization and to seed reliably; the stripe's
# *orientation*, not its width, is what makes the resulting cut straight.
LABEL_SEED_STRIPE_THICKNESS_PAGE_RATIO = 0.002

# A general-notes / key-notes / legend / title block is a rectangle full of
# printed text. It survives every other gate here — it is large, compact,
# ink-dense, and (being a rectangle) perfectly rectilinear, so neither the
# shape tests nor the rectilinearity confidence gate can see anything wrong
# with it. Measured on a real finish-plan sheet, share of each detected
# polygon's own area covered by the PDF's printed word boxes: the four
# genuine rooms scored 0.000, 0.000, 0.008 and 0.010, while the GENERAL
# NOTES block scored 0.414 — a 40x separation, and it was being reported as
# that page's single highest-confidence "room" (828 sqft at 0.95).
#
# A real room does carry text — its name, area tag, and on a tagged CAD
# sheet a finish-schedule table printed inside it — which is why this is a
# coverage share rather than a word count, and why the threshold has to be
# measured against real rooms rather than set just above zero. Measured
# across both sheets: the busiest genuine room (a small WC on the AUC
# sheet, carrying an "A B C D E" schedule table and a "10 M²" tag in a
# 75 sqft footprint) reaches 0.234, and the next busiest 0.159; the notes
# block reaches 0.414. 0.30 sits between them with ~28% headroom over the
# busiest real room.
#
# An earlier value of 0.15 was verified WRONG in exactly the way this
# comment exists to prevent: it sat inside the real-room range and deleted
# two genuine AUC rooms (a 121.3 sqft and one of a symmetric 75.4 pair)
# while still not being what caught the notes block.
MAX_ROOM_TEXT_COVERAGE = 0.30

# Real-world size gate, used ONLY when the page's scale is actually known
# (user-calibrated, or OCR-detected from a scale annotation). Page-relative
# ratios are DPI-blind: the same building rasterized at a different DPI (see
# pdf_engine.compute_adaptive_dpi, which lowers DPI for large sheets) would
# otherwise accept a different set of rooms.
#
# This is deliberately NOT applied to an assumed scale. The fallback
# assumption (1/8"=1'-0") is frequently wrong by a factor of several, which
# makes every real room measure far too small — gating on feet in that state
# would silently delete valid rooms and look exactly like a detection bug.
MIN_ROOM_AREA_SQFT = 15.0  # smaller than a broom closet
MAX_ROOM_AREA_SQFT = 25_000.0

# Scale-free fallback gate, as a share of total page area. Applied whenever
# the scale is only assumed.
MIN_ROOM_AREA_RATIO = 0.0015

# Polsby-Popper compactness: 4*pi*area / perimeter^2. A circle scores 1.0,
# a square 0.79, a 40ft x 5ft corridor still ~0.31 — but a leaked flood-fill
# sliver (long, thin, snaking between wall gaps) scores well under 0.15.
MIN_ROOM_COMPACTNESS = 0.15

# A connected wall component must span at least this share of the page's long
# edge to count as a wall run rather than a bubble/arrow/legend mark, for the
# purpose of building the envelope below.
MIN_WALL_RUN_EXTENT_PAGE_RATIO = 0.05

# building_envelope_mask spatially clusters surviving wall-run components
# (see CLUSTER_GAP_WALL_THICKNESS_MULTIPLIER below) before hulling each
# cluster separately, rather than hulling every candidate point on the page
# as one
# mass. A single global hull is wrong whenever ANY unrelated linework
# elsewhere on the sheet individually clears the wall-run bar — verified on
# a real finish-plan sheet where a site tree's residual planter-box outline,
# a roof-overhang line fragment, and a scale bar each qualified on their own
# and, hulled together with the real building, produced one hull covering
# most of the page. Requiring a cluster's own pixel mass to be a real
# fraction of the largest cluster's mass is what tells "second building
# wing" apart from "unrelated sheet content": measured on that same sheet,
# the two halves of the actual building were 399,242px and 197,260px, while
# every non-building cluster was under 18,300px — an order of magnitude
# gap, not a close call.
MIN_ENVELOPE_CLUSTER_MASS_RATIO = 0.10

# How close two wall-run components must be to bridge into the same cluster
# via morphological closing, before the mass-ratio gate above runs.
#
# This used to be a share of the page's LONG EDGE, which turned out to mix
# up two unrelated things: an 8400px CAD sheet and a 2000px stock-graphic
# floor plan measured the SAME real wall stroke thickness in absolute
# pixels (~7-8px each) despite a 4x difference in page size — the two
# sheets aren't at different physical scales, they're just rasterized at
# different resolutions. A page-ratio gap is consequently arbitrary
# relative to what actually needs bridging (a doorway, a few multiples of
# wall thickness).
#
# Directly measured (real sheet, nearest-neighbor pixel distance from every
# non-building wall-run component to the two largest/"the building"
# components): legitimate same-building fragments — split apart only by
# Hough/antialiasing noise near a doorway or thin wall — sat 12-22px away.
# Every genuinely unrelated component (a tree, a roof-overhang line
# fragment, a scale bar, a margin dimension string) sat 237px or farther
# away. That's better than a 10x separation, not a close call, so a
# threshold anywhere in that gap works; 20x wall thickness (~140-160px on
# the two sheets this was tuned against) sits comfortably inside it.
CLUSTER_GAP_WALL_THICKNESS_MULTIPLIER = 20

# The drawing sheet's own border frame is a long, thick, page-spanning
# rectangle — it passes every "is this a wall run" test, and including it
# forced the building envelope to cover the entire sheet (measured: 100% of
# the page), which is what admitted all the empty margin as candidate room
# space. A component is treated as the sheet frame, not a wall, when its
# bounding box spans nearly the whole page in BOTH axes while enclosing
# almost nothing (a thin outline, not a solid mass). A real building's wall
# structure never spans edge-to-edge in both directions — there is always
# sheet margin around it.
SHEET_FRAME_SPAN_RATIO = 0.95
SHEET_FRAME_MAX_FILL_RATIO = 0.15

# A decorative legend/scale-bar strip is drawn as several near-identical
# thin, SOLID rectangles side by side — measured on a real sheet: 12 bars,
# each 33-36px wide x 963-1020px tall, fill ratio 1.00 (completely solid).
# A real wall run's bounding box is mostly empty (it's a thin *stroke*
# around the room it encloses) — every genuine wall run on that same sheet
# measured aspect <= 2.4 and fill <= 0.13. The one exception was a single
# lone straight wall segment (aspect 16.8, fill 1.00, cut off from its
# neighbors by a door-swing arc) — which is why this only fires on a
# *group* of several near-duplicate components, not on thinness/fill alone:
# a real floor plan has one-off long straight walls, but never several
# same-sized solid bars repeated in a row.
DECORATIVE_BAR_ASPECT_RATIO = 8.0
DECORATIVE_BAR_FILL_RATIO = 0.9
DECORATIVE_BAR_MIN_GROUP_SIZE = 3
DECORATIVE_BAR_SIZE_TOLERANCE = 0.25  # +/-25% width/height to count as "near-identical"

# NOTE (measured, do not retry naively): decorative sheet furniture drawn in
# wall weight — legend bars, scale bars, symbol strips — gets hulled into the
# envelope and the watershed then reports each bar as a room. Restricting the
# hull to wall runs within a fixed distance of the largest run does NOT
# separate them: on one sheet the real runs join at gaps up to 8.0% of the
# page's long edge and the decorative bars start at 10.2%, but on another the
# real runs need 18.6% to stay connected. Any single gap threshold either
# admits the decoration or amputates part of a real building. A sound fix
# needs a different signal (e.g. repeated-identical-shape detection, or
# requiring wall runs to participate in the wall graph).

# Room "cores" are the parts of the interior further than this from any wall.
# A doorway is a narrow neck (~3 ft, so ~1.5 ft from either jamb) while a
# room's middle is metres from anything — thresholding the distance
# transform here therefore yields exactly one core per room and none in the
# doorways, which is what lets rooms be separated without the walls having
# to be perfectly sealed.
ROOM_CORE_DISTANCE_FT = 2.5

# When the scale is only assumed (not calibrated), the threshold is a
# fraction of the page's long edge.
#
# What this is really approximating is *half a doorway width*: cores must
# survive inside rooms but vanish in the doorway necks between them, and a
# doorway is ~3ft regardless of how big the rooms are. Two very different
# plans both land on ~50px for that (2400px-wide sheet at ~33px/ft, and a
# 2000px-wide sheet at ~37px/ft), which is what this ratio encodes.
#
# Normalizing to the drawing's own maximum clearance was tried instead and
# is worse: it ties the threshold to the single most open space on the
# sheet, so a plan with a large garage or open-plan living area pushes the
# threshold far above doorway scale and merges every ordinary room. Two
# files needed fractions 0.39 and 0.10 to behave, while this single ratio
# yields a balanced 13 cores on both.
ROOM_CORE_DISTANCE_PAGE_RATIO = 0.014

# The core threshold must always be satisfiable. Converting feet through a
# scale that is wrong — an OCR misread, or a stale calibration — can demand
# a clearance larger than anything the drawing contains, in which case no
# cores exist and the page silently reports zero rooms. Capping the
# threshold at a fraction of the largest clearance actually present makes
# that impossible: there is always at least one core. (The uncalibrated
# path above is self-clamping by construction; this only ever bites the
# calibrated, real-feet path.)
MAX_CORE_DISTANCE_FRACTION = 0.45
MIN_CORE_DISTANCE_PX = 6.0

# A real room on a drawing contains interior linework — furniture, fixtures,
# hatching, dimension text. Blank sheet does not. This catches the dead space
# the convex-hull envelope admits that MIN_WALL_CONTACT_RATIO cannot: on a
# sheet carrying TWO floor plans side by side (very common on real CAD sets),
# the hull spans both plans plus the empty gutter between them, and that
# gutter is bounded by both plans' exterior walls — so it passes the wall-
# contact test and was being reported as a fabricated 3,272 sqft room.
#
# Measured across three real sheets: the phantom gutter region scored 0.030,
# while every confirmed real room scored 0.050-0.288 (commercial CAD
# 0.088-0.271, illustrated 0.052-0.095, residential 0.050-0.288). 0.04 sits
# between the two populations, but the margin is genuinely narrow (1.3x on
# either side) — this separates the cases actually measured, not a
# comfortably wide gap, so a real but completely unfurnished room on a very
# sparse plan could fall below it. Kept deliberately low for that reason:
# under-filtering leaves a phantom room a human can reject, over-filtering
# silently deletes a real one.
MIN_ROOM_INK_DENSITY = 0.05

# A real room is walled in; this exists to catch a region that merely fell
# inside the building hull without ever touching a wall (a dead corner
# between the building's actual (concave) footprint and the convex hull
# building_envelope_mask approximates it with — a porch-and-garage building
# is not convex, so the hull always overshoots into some such corners).
#
# This was lowered to 0.20 at one point to recover small rooms with many
# doorways relative to their perimeter (contact as low as 0.24 on a
# real plan), which is a genuine case this ratio gets wrong. But re-checked
# directly against real hull dead-space on that same plan: those regions
# scored 0.24-0.42, indistinguishable from the legitimate small rooms by
# this metric — no threshold value separates them, because the actual
# defect is the convex hull admitting concave dead-space in the first
# place, not this filter. Several non-convex envelope reconstructions were
# tried (dilate-bridge the wall mask, directional door-sealing + border
# flood-fill, hull-boundary flood-fill) and each either fragmented the
# building into disconnected pieces or catastrophically over-flooded
# through some gap — none were reliable enough to land.
#
# Reverted to 0.45 as the safer default until the envelope itself is fixed:
# a fabricated room inflates a cost estimate (the tool asserting square
# footage that doesn't exist), while a missed room is merely absent and
# can be added manually — the two failure modes are not equally bad for an
# estimating tool, so when neither is solved, prefer under- to over-detection.
MIN_WALL_CONTACT_RATIO = 0.45

# --- Exterior covered areas (porches, decks, covered patios) ---
#
# These are real, quantifiable spaces but they are NOT rooms: they have no
# enclosing walls, so they never appear in the wall-derived building
# envelope. On a drawing they are bounded by a thin dashed line (a roof
# overhang / covered-area outline) plus the building's own exterior wall —
# and that dashed line is exactly the kind of thin stroke the wall mask
# deliberately discards, because keeping thin strokes is what floods the
# plan with furniture and dimension lines.
#
# So they are found in a separate pass, against ALL linework rather than
# just wall-thick linework: bridge the dashes, take what is enclosed, and
# keep the parts lying outside the building envelope but touching it.
#
# They are reported with room_type EXTERIOR_AREA_ROOM_TYPE so downstream
# pricing can treat them correctly — a porch has floor and roof area but no
from app.models.enums import RoomType

EXTERIOR_AREA_ROOM_TYPE = RoomType.EXTERIOR_COVERED.value

# Kernel for closing the gaps in a dashed boundary so it encloses. Results
# were stable from 5px to 17px on a real sheet, so this is not sensitive.
EXTERIOR_DASH_BRIDGE_PX = 9

# An exterior area must be at least this share of the page, so stray
# enclosed slivers between annotation lines don't qualify.
MIN_EXTERIOR_AREA_RATIO = 0.004

# ...and at most this share. The scale-aware MAX_ROOM_AREA_SQFT cap below only
# fires when the page's scale is actually calibrated — most uploads aren't —
# so an ink gap that lets "outside the building" bridge into one giant region
# (e.g. a broken dash on one side of the envelope) would otherwise pass
# unbounded and paint most of the sheet as a single "porch". A real covered
# exterior area is always small next to the building it's attached to.
MAX_EXTERIOR_AREA_RATIO = 0.25

# How far from the building an enclosed region may sit and still count as
# attached to it (a porch abuts the building; the margin between the
# covered-area outline and the sheet border does not).
EXTERIOR_ADJACENCY_PX = 31


def wall_mask_thickness_px(image_shape: tuple[int, int]) -> int:
    """Wall strokes are thicker on a higher-resolution raster, so a fixed
    3px mask under-covers a 6000px sheet and leaves pinholes the flood
    fill escapes through. Scale with the page instead.
    """
    long_edge = max(image_shape)
    return max(MIN_WALL_MASK_THICKNESS_PX, int(round(long_edge / 1200)))


def bridge_wall_endpoint_gaps(segments: list[Segment], max_gap_px: float = 160.0, min_gap_px: float = 15.0) -> tuple[list[Segment], int]:
    """Targeted Door Opening Bridge:
    Identifies collinear wall line segment endpoints facing each other across door openings
    (15px <= gap <= 160px) and creates targeted bridging segments to seal door thresholds.
    """
    if not segments:
        return segments, 0

    new_segments = list(segments)
    bridged_count = 0

    horiz = [s for s in segments if abs(s.y1 - s.y2) < 5]
    vert = [s for s in segments if abs(s.x1 - s.x2) < 5]

    # 1. Horizontal door gaps (same Y level, gap in X)
    horiz_by_y: dict[int, list[Segment]] = {}
    for s in horiz:
        y_key = int(round((s.y1 + s.y2) / 2 / 10.0)) * 10
        horiz_by_y.setdefault(y_key, []).append(s)

    for y_key, segs in horiz_by_y.items():
        sorted_segs = sorted(segs, key=lambda s: min(s.x1, s.x2))
        for i in range(len(sorted_segs) - 1):
            s1 = sorted_segs[i]
            s2 = sorted_segs[i+1]

            right_s1 = max(s1.x1, s1.x2)
            left_s2 = min(s2.x1, s2.x2)

            gap = left_s2 - right_s1
            if min_gap_px <= gap <= max_gap_px:
                y_mid = (s1.y1 + s1.y2 + s2.y1 + s2.y2) / 4.0
                new_segments.append(Segment(x1=right_s1, y1=y_mid, x2=left_s2, y2=y_mid))
                bridged_count += 1

    # 2. Vertical door gaps (same X level, gap in Y)
    vert_by_x: dict[int, list[Segment]] = {}
    for s in vert:
        x_key = int(round((s.x1 + s.x2) / 2 / 10.0)) * 10
        vert_by_x.setdefault(x_key, []).append(s)

    for x_key, segs in vert_by_x.items():
        sorted_segs = sorted(segs, key=lambda s: min(s.y1, s.y2))
        for i in range(len(sorted_segs) - 1):
            s1 = sorted_segs[i]
            s2 = sorted_segs[i+1]

            bottom_s1 = max(s1.y1, s1.y2)
            top_s2 = min(s2.y1, s2.y2)

            gap = top_s2 - bottom_s1
            if min_gap_px <= gap <= max_gap_px:
                x_mid = (s1.x1 + s1.x2 + s2.x1 + s2.x2) / 4.0
                new_segments.append(Segment(x1=x_mid, y1=bottom_s1, x2=x_mid, y2=top_s2))
                bridged_count += 1

    return new_segments, bridged_count


def build_wall_mask(image_shape: tuple[int, int], segments: list[Segment], thickness_px: int | None = None) -> np.ndarray:
    """A binary mask (255 = wall) rasterized from the merged wall segments,
    morphologically closed so that small breaks in the linework (dashed
    stretches, faded scan lines, Hough endpoint jitter) are sealed.
    """
    bridged_segs, bridge_cnt = bridge_wall_endpoint_gaps(segments, max_gap_px=160.0, min_gap_px=15.0)
    thickness = thickness_px if thickness_px is not None else wall_mask_thickness_px(image_shape)
    mask = np.zeros(image_shape, dtype=np.uint8)
    for seg in bridged_segs:
        cv2.line(
            mask,
            (int(round(seg.x1)), int(round(seg.y1))),
            (int(round(seg.x2)), int(round(seg.y2))),
            255,
            thickness,
        )

    seal = max(3, thickness + 2)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (seal, seal))
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)


def seal_door_openings_in_wall_mask(
    wall_mask: np.ndarray,
    door_detections: list,
    thickness_px: int = 10,
) -> tuple[np.ndarray, dict]:
    """Targeted Door Opening Sealer:
    For each detected door symbol (from YOLO or vector symbol layer), seals the wall mask
    specifically across the door's threshold / opening box so flood-fill does not leak
    between rooms.

    Unlike generic morphological closing, this does NOT distort or shrink small rooms.
    
    Returns (sealed_wall_mask, tracking_metrics_dict)
    """
    if not door_detections:
        return wall_mask, {"total_door_detections": 0, "sealed_doors_count": 0, "skipped_doors_count": 0}

    h, w = wall_mask.shape[:2]
    sealed_mask = wall_mask.copy()
    
    sealed_count = 0
    skipped_count = 0

    for d in door_detections:
        # Extract pixel bbox
        if hasattr(d, "bbox_norm") and isinstance(d.bbox_norm, dict):
            bx1 = int(round(d.bbox_norm["minX"] * w))
            by1 = int(round(d.bbox_norm["minY"] * h))
            bx2 = int(round(d.bbox_norm["maxX"] * w))
            by2 = int(round(d.bbox_norm["maxY"] * h))
        elif hasattr(d, "bbox_px") and isinstance(d.bbox_px, (tuple, list)):
            bx1, by1, bx2, by2 = [int(round(coord)) for coord in d.bbox_px]
        else:
            skipped_count += 1
            continue

        bw = abs(bx2 - bx1)
        bh = abs(by2 - by1)

        if bw < 5 or bh < 5 or bw > (w * 0.25) or bh > (h * 0.25):
            skipped_count += 1
            continue

        cx = (bx1 + bx2) // 2
        cy = (by1 + by2) // 2

        line_thick = max(4, thickness_px)

        if bw > bh:
            # Horizontal door opening -> draw vertical threshold line connecting top and bottom walls
            cv2.line(sealed_mask, (cx, max(0, by1 - 4)), (cx, min(h - 1, by2 + 4)), 255, line_thick)
        else:
            # Vertical door opening -> draw horizontal threshold line connecting left and right walls
            cv2.line(sealed_mask, (max(0, bx1 - 4), cy), (min(w - 1, bx2 + 4), cy), 255, line_thick)

        sealed_count += 1

    metrics = {
        "total_door_detections": len(door_detections),
        "sealed_doors_count": sealed_count,
        "skipped_doors_count": skipped_count,
    }
    return sealed_mask, metrics


def _decorative_bar_component_ids(
    stats: np.ndarray, candidate_ids: list[int]
) -> set[int]:
    """Which of `candidate_ids` belong to a group of >= 3 near-identical
    thin, solid rectangles (a legend strip, scale bar, or similar sheet
    decoration) — see DECORATIVE_BAR_* constants for the measurements this
    is based on.
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


def building_envelope_mask(
    wall_mask: np.ndarray, walls_are_authoritative: bool = False
) -> np.ndarray | None:
    """The building footprint, as the filled convex hull of the wall runs.

    Openings break a building's walls into many disconnected pieces (73 on
    a typical sheet), so "largest connected component" is not the building —
    it is one wing of it. Instead, keep every component long enough to be a
    wall run and hull them together.

    The length test also discards the compact blobs that litter a sheet —
    grid/column bubbles, north arrows, legend marks — which are otherwise
    indistinguishable from rooms and are how detections end up floating
    outside the plan.

    `walls_are_authoritative` says the mask came from the PDF's own named
    wall layers (vector_walls.extract_wall_mask_from_layers) rather than
    from raster stroke-thickness guessing — i.e. the drafter themselves
    declared every stroke in it to be a wall. The decorative-bar filter is
    then skipped, because it exists only to guess walls apart from legend
    strips in raster masks, and its central assumption ("a real floor plan
    never has several same-sized solid bars repeated in a row") is false on
    real CAD sheets: measured on a two-floor-plan commercial sheet, 19 of
    27 wall runs were identical 7x663px party/exterior wall strokes — a
    repeated modular bay structure — and the filter deleted all of them,
    shrinking the envelope from 34.5% of the page to 15.6% and amputating
    the lower half of both plans (and with them every room there).
    """
    num, labels, stats, _ = cv2.connectedComponentsWithStats((wall_mask > 0).astype(np.uint8), connectivity=8)
    if num <= 1:
        return None

    h, w = wall_mask.shape
    min_extent = max(wall_mask.shape) * MIN_WALL_RUN_EXTENT_PAGE_RATIO
    candidate_ids: list[int] = []
    for i in range(1, num):
        box_w = stats[i, cv2.CC_STAT_WIDTH]
        box_h = stats[i, cv2.CC_STAT_HEIGHT]
        if max(box_w, box_h) < min_extent:
            continue
        # Skip the drawing sheet's border frame (see SHEET_FRAME_SPAN_RATIO).
        box_area = box_w * box_h
        if (
            box_w >= SHEET_FRAME_SPAN_RATIO * w
            and box_h >= SHEET_FRAME_SPAN_RATIO * h
            and box_area > 0
            and stats[i, cv2.CC_STAT_AREA] / box_area < SHEET_FRAME_MAX_FILL_RATIO
        ):
            continue
        candidate_ids.append(i)

    decorative = set() if walls_are_authoritative else _decorative_bar_component_ids(stats, candidate_ids)
    # A raster (non-vector-layer) wall-band mask over a densely hatched/
    # textured sheet can carry thousands of qualifying components — looping
    # per id and rescanning the whole page (`labels == i`) turned this into
    # the same O(components * page_pixels) blowup fixed elsewhere in this
    # session (line_extraction._remove_specks), just with a different loop
    # variable name that skipped that earlier audit: measured on a real
    # sheet, this single loop took 100+ seconds. A vectorized lookup table
    # over `labels` does the same job as one pass over the image.
    keep_ids = np.zeros(num, dtype=bool)
    for i in candidate_ids:
        if i not in decorative:
            keep_ids[i] = True
    runs = np.where(keep_ids[labels], np.uint8(255), np.uint8(0))

    points = cv2.findNonZero(runs)
    if points is None or len(points) < 3:
        return None

    # Spatially cluster the surviving wall-run mass — real building wings
    # are close enough to bridge through a small morphological closing;
    # unrelated sheet content sits farther away and stays its own cluster
    # (see MIN_ENVELOPE_CLUSTER_MASS_RATIO for why mass, not just presence,
    # is what decides which clusters are actually part of the building).
    cluster_kernel_px = max(3, wall_mask_thickness_px((h, w)) * CLUSTER_GAP_WALL_THICKNESS_MULTIPLIER)
    # MORPH_RECT rather than MORPH_ELLIPSE: OpenCV decomposes a rectangular
    # structuring element into two fast 1D passes, but not an elliptical
    # one — at large kernel sizes the elliptical version took 100+ seconds
    # on a single MORPH_CLOSE call on an 8400px-wide sheet, measured on a
    # real sheet. A rectangle is just as good for "bridge components within
    # X px" bridging.
    cluster_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (cluster_kernel_px, cluster_kernel_px))
    clustered = cv2.morphologyEx(runs, cv2.MORPH_CLOSE, cluster_kernel)
    n_clusters, cluster_labels = cv2.connectedComponents((clustered > 0).astype(np.uint8), connectivity=8)
    if n_clusters <= 1:
        return None

    cluster_masses: dict[int, int] = {}
    for cid in range(1, n_clusters):
        cluster_masses[cid] = int(((runs > 0) & (cluster_labels == cid)).sum())
    largest_mass = max(cluster_masses.values())
    if largest_mass <= 0:
        return None

    envelope = np.zeros_like(wall_mask)
    for cid, mass in cluster_masses.items():
        if mass < largest_mass * MIN_ENVELOPE_CLUSTER_MASS_RATIO:
            continue
        cluster_points = cv2.findNonZero(np.where((runs > 0) & (cluster_labels == cid), np.uint8(255), np.uint8(0)))
        if cluster_points is None or len(cluster_points) < 3:
            continue
        cv2.drawContours(envelope, [cv2.convexHull(cluster_points)], -1, 255, thickness=cv2.FILLED)
    return envelope if envelope.any() else None


def _wall_contact_ratio(region: np.ndarray, wall_mask: np.ndarray, probe_px: int) -> float:
    """What share of a region's outline is actually up against a wall.

    A room is enclosed by walls. A region that merely fell inside the
    building hull — the apron of empty sheet below the plan, for instance —
    borders almost nothing, and this is what separates the two.
    """
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (probe_px, probe_px))
    border = cv2.subtract(cv2.dilate(region, kernel), region)
    border_px = int((border > 0).sum())
    if border_px == 0:
        return 0.0
    touching = int((cv2.bitwise_and(border, wall_mask) > 0).sum())
    return touching / border_px


def detect_exterior_area_polygons(
    ink: np.ndarray,
    wall_mask: np.ndarray,
    scale_ft_per_px: float,
    scale_is_calibrated: bool = False,
    walls_are_authoritative: bool = False,
) -> list[np.ndarray]:
    """Covered exterior areas (porches, decks) attached to the building.

    `ink` is ALL linework, not the wall-thick subset — a porch's outer
    boundary is a thin dashed line that the wall mask correctly discards
    (see EXTERIOR_AREA_ROOM_TYPE), so this pass has to look at the raw ink
    to find one.

    Returns the same (N, 2) pixel-polygon format as detect_room_polygons.
    """
    envelope = building_envelope_mask(wall_mask, walls_are_authoritative)
    if envelope is None:
        return []

    h, w = ink.shape[:2]

    # Bridge the dashes so the covered-area outline actually encloses.
    bridge = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (EXTERIOR_DASH_BRIDGE_PX, EXTERIOR_DASH_BRIDGE_PX))
    bridged = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, bridge)

    # Everything the page border can reach is open sheet, not an enclosed area.
    # The CC bounding-box test is exact and O(n): any component whose bounding
    # box touches the image edge is reachable from outside — discard it.
    # This replaces the previous pixel-by-pixel flood-fill loop, which sampled
    # every 4th edge pixel and could miss narrow connections to the border.
    free = cv2.bitwise_not(bridged)
    num_free, free_labels, free_stats, _ = cv2.connectedComponentsWithStats(free, connectivity=8)
    # A vectorized lookup-table pass over the whole label map, rather than a
    # Python loop rescanning the full page once per component — the same
    # fix as line_extraction._remove_specks, needed here because "everything
    # not touching the border" can also be thousands of small components.
    fx = free_stats[:, cv2.CC_STAT_LEFT]
    fy = free_stats[:, cv2.CC_STAT_TOP]
    fbw = free_stats[:, cv2.CC_STAT_WIDTH]
    fbh = free_stats[:, cv2.CC_STAT_HEIGHT]
    keep_mask = (fx > 0) & (fy > 0) & (fx + fbw < w) & (fy + fbh < h)
    keep_mask[0] = False
    enclosed = np.where(keep_mask[free_labels], np.uint8(255), np.uint8(0))
    enclosed = cv2.morphologyEx(enclosed, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))


    outside_building = cv2.bitwise_and(enclosed, cv2.bitwise_not(envelope))
    near_building = cv2.dilate(envelope, np.ones((EXTERIOR_ADJACENCY_PX, EXTERIOR_ADJACENCY_PX), np.uint8))

    num, labels, stats, _ = cv2.connectedComponentsWithStats(outside_building, connectivity=8)
    page_area = h * w
    sqft_per_px = scale_ft_per_px**2 if scale_ft_per_px > 0 else 0.0

    polygons: list[np.ndarray] = []
    for i in range(1, num):
        area_px = stats[i, cv2.CC_STAT_AREA]
        if area_px < page_area * MIN_EXTERIOR_AREA_RATIO or area_px > page_area * MAX_EXTERIOR_AREA_RATIO:
            continue

        # The ring of sheet between the covered-area outline and the page
        # border spans essentially the whole page — same signature as the
        # sheet frame itself, and just as much "not a porch".
        box_w, box_h = stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
        if box_w >= SHEET_FRAME_SPAN_RATIO * w and box_h >= SHEET_FRAME_SPAN_RATIO * h:
            continue

        region = ((labels == i).astype(np.uint8)) * 255
        # A porch abuts the building; a detached enclosed box elsewhere on
        # the sheet (a detail bubble, a key plan) does not.
        if not cv2.bitwise_and(region, near_building).any():
            continue

        if scale_is_calibrated and sqft_per_px > 0:
            area_sqft = area_px * sqft_per_px
            if area_sqft < MIN_ROOM_AREA_SQFT or area_sqft > MAX_ROOM_AREA_SQFT:
                continue

        contours, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        contour = max(contours, key=cv2.contourArea)
        perimeter_px = cv2.arcLength(contour, True)
        if perimeter_px <= 0:
            continue
        approx = cv2.approxPolyDP(contour, POLY_APPROX_EPSILON_RATIO * perimeter_px, True)
        pts = approx.reshape(-1, 2)
        if len(pts) >= 3:
            polygons.append(pts)

    return polygons


# When a watershed region comes back too convoluted to be a single room, it
# is usually several rooms joined through openings too wide for the nominal
# core threshold to separate (stylised plans and open-plan layouts draw
# 6ft+ cased openings). Re-thresholding the same distance transform higher
# shrinks the cores until they stop bridging those openings. Measured on a
# sheet where A/B/G/F merged into one 33%-of-page blob: 1.5x and 2.0x still
# left A+B+G joined, 2.5x and 3.0x recovered all four rooms, 4.0x started
# losing the smallest again — so sweep and keep whichever yields the most
# valid rooms rather than trusting any single multiplier.
ROOM_SPLIT_CORE_MULTIPLIERS = (1.5, 2.0, 2.5, 3.0, 4.0)

# Only worth attempting on a region big enough to actually be several rooms;
# a small non-compact fragment is just noise.
ROOM_SPLIT_MIN_AREA_RATIO = 0.02


def _watershed_regions(area_mask: np.ndarray, distance: np.ndarray, core_distance_px: float) -> list[np.ndarray]:
    """Grow one region per room core inside `area_mask`.

    `distance` is the clearance-from-walls transform of the whole page, so a
    sub-region split reuses true wall clearance rather than distance to the
    blob's own edge.
    """
    cores = ((distance > core_distance_px) & (area_mask > 0)).astype(np.uint8)
    cores = cv2.morphologyEx(cores, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))

    num_cores, core_labels = cv2.connectedComponents(cores)
    if num_cores <= 1:
        return []

    # Standard watershed marker convention, and it has to be exact:
    #   1      -> known background (everything outside the area)
    #   2..n   -> the room cores to grow from
    #   0      -> unknown, i.e. the area between cores and walls
    #
    # Leaving the non-core area at a non-zero label makes watershed treat it
    # as one already-decided region, so the cores never expand and each
    # "room" comes back as just its core — inset from the walls by exactly
    # the core threshold.
    markers = np.zeros(core_labels.shape, dtype=np.int32)
    markers[area_mask == 0] = 1
    markers[cores > 0] = core_labels[cores > 0] + 1

    watershed_labels = cv2.watershed(cv2.cvtColor(area_mask, cv2.COLOR_GRAY2BGR), markers)

    regions: list[np.ndarray] = []
    for label in range(2, num_cores + 1):
        region = cv2.bitwise_and(((watershed_labels == label).astype(np.uint8)) * 255, area_mask)
        if region.any():
            regions.append(region)
    return regions


def _room_contour(region: np.ndarray, wall_mask: np.ndarray, probe_px: int) -> np.ndarray | None:
    """The region's outline, or None if it isn't actually walled in."""
    if _wall_contact_ratio(region, wall_mask, probe_px) < MIN_WALL_CONTACT_RATIO:
        return None
    contours, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    return max(contours, key=cv2.contourArea)


def _is_compact_room(contour: np.ndarray) -> bool:
    area_px = cv2.contourArea(contour)
    perimeter_px = cv2.arcLength(contour, True)
    if area_px <= 0 or perimeter_px <= 0:
        return False
    return contour_compactness(area_px, perimeter_px) >= MIN_ROOM_COMPACTNESS


def _label_centroids_in_region(
    region: np.ndarray, label_centroids_px: list[tuple[float, float]]
) -> list[tuple[float, float]]:
    return [
        (x, y)
        for x, y in label_centroids_px
        if 0 <= int(y) < region.shape[0] and 0 <= int(x) < region.shape[1] and region[int(y), int(x)] > 0
    ]


def _split_region_by_label_seeds(
    region: np.ndarray,
    label_centroids_px: list[tuple[float, float]],
    wall_angle_deg: float = 0.0,
) -> list[np.ndarray]:
    """Split a merged region using OCR room-name label positions as forced
    watershed seeds — one core per label, so the region divides into exactly
    as many pieces as there are room names printed inside it.

    Exists for the case the core-distance sweep above cannot fix: a merged
    region whose *wall* data is genuinely incomplete (verified on a real CAD
    export where several partition walls live on a mixed/noisy CAD layer
    that couldn't be reliably separated from non-wall linework — see the
    module docstring's note on that). No core-distance retry can recover a
    wall that was never in the mask to begin with.

    A label is independent evidence a room exists there regardless of
    whether its walls were captured, so this seeds directly from label
    positions instead of from wall clearance. Where a real (if incomplete)
    wall fragment already sits between two labels, watershed still respects
    it and the split follows that wall; where nothing at all separates two
    labeled rooms, the boundary falls roughly equidistant between them
    instead — an approximation of the true wall, not a measurement of it,
    but a labeled room split into a plausible shape is a large improvement
    over N labeled rooms left as one undifferentiated blob.

    That approximated boundary is constrained to the building's own axis
    (`wall_angle_deg`, from _dominant_wall_angle_deg). Seeding from bare
    points made the watershed front between two labels settle on their
    perpendicular bisector, which is at an arbitrary angle set by where the
    two labels happen to sit — on the AUC sheet that produced a clearly
    diagonal cut straight through rooms that are rectangular in the
    drawing. Seeding each label as a stripe perpendicular to the axis the
    labels are most separated along makes the fronts advance along that
    axis only, so where nothing separates two rooms the boundary comes out
    straight and wall-like instead of diagonal. A real wall fragment inside
    the region still diverts the front exactly as before — the stripes
    change where the fronts start, not the watershed's respect for
    barriers. Such a room is still reported unverified (see _bare_contour);
    this only stops a forced approximation from *looking* like a measured
    wall.
    """
    seeds = _label_centroids_in_region(region, label_centroids_px)
    if not seeds:
        return []

    markers = np.zeros(region.shape, dtype=np.int32)
    markers[region == 0] = 1

    theta = math.radians(wall_angle_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    # Seed coordinates in the building's own frame: u runs along the
    # building axis, v across it.
    us = [x * cos_t + y * sin_t for x, y in seeds]
    vs = [-x * sin_t + y * cos_t for x, y in seeds]
    spread_u = (max(us) - min(us)) if len(us) > 1 else 0.0
    spread_v = (max(vs) - min(vs)) if len(vs) > 1 else 0.0
    # Stripe runs perpendicular to whichever building axis the labels are
    # most separated along, so the fronts meet across that axis.
    if spread_u >= spread_v:
        dir_x, dir_y = -sin_t, cos_t
    else:
        dir_x, dir_y = cos_t, sin_t

    stripe_len = float(max(region.shape))
    stripe_px = max(3, int(round(max(region.shape) * LABEL_SEED_STRIPE_THICKNESS_PAGE_RATIO)))
    for i, (x, y) in enumerate(seeds):
        p1 = (int(round(x - dir_x * stripe_len)), int(round(y - dir_y * stripe_len)))
        p2 = (int(round(x + dir_x * stripe_len)), int(round(y + dir_y * stripe_len)))
        stripe = np.zeros(region.shape, dtype=np.uint8)
        cv2.line(stripe, p1, p2, 255, stripe_px)
        # A marker must never sit on background, or watershed would grow
        # this label's region outside the blob being split.
        stripe = cv2.bitwise_and(stripe, region)
        # Only claim pixels no earlier seed already took: two labels close
        # together along the separation axis can produce overlapping
        # stripes, and letting a later one overwrite an earlier one would
        # erase that label's seed entirely and silently drop its room.
        claim = (stripe > 0) & (markers == 0)
        if not claim.any():
            if markers[int(y), int(x)] == 0:
                cv2.circle(markers, (int(x), int(y)), 3, i + 2, -1)
            continue
        markers[claim] = i + 2

    watershed_labels = cv2.watershed(cv2.cvtColor(region, cv2.COLOR_GRAY2BGR), markers)

    regions: list[np.ndarray] = []
    for label in range(2, len(seeds) + 2):
        sub = cv2.bitwise_and(((watershed_labels == label).astype(np.uint8)) * 255, region)
        if sub.any():
            regions.append(sub)
    return regions


def _bare_contour(region: np.ndarray) -> np.ndarray | None:
    """A region's outline with no wall-contact requirement — used only for
    label-seeded splits (see _split_region_by_label_seeds), where part of
    each sub-piece's boundary is a synthetic cut between two label seeds
    rather than a real wall. The parent region already passed the wall-
    contact check as a whole before a split was attempted at all; demanding
    each post-split sliver independently reprove wall enclosure would
    reject almost every one of them by construction; measured on a real
    merged multi-office blob, sub-region wall-contact ratios of 0.07-0.50
    against the 0.45 gate, discarding label-confirmed rooms.
    """
    contours, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    return max(contours, key=cv2.contourArea)


def _split_merged_region(
    region: np.ndarray,
    distance: np.ndarray,
    wall_mask: np.ndarray,
    probe_px: int,
    base_core_distance_px: float,
    label_centroids_px: list[tuple[float, float]] | None = None,
    wall_angle_deg: float = 0.0,
) -> list[tuple[np.ndarray, bool]]:
    """Try to break one over-merged region into its constituent rooms.

    Returns (contour, wall_verified) pairs for the best split found, or []
    if the region genuinely doesn't separate — in which case the caller
    drops it, exactly as before this existed. `wall_verified` is False for
    a split produced by the label-seed fallback, whose cut is a synthetic
    line between two OCR label positions rather than a real wall (see
    _bare_contour and room_confidence).
    """
    best: list[tuple[np.ndarray, bool]] = []
    for multiplier in ROOM_SPLIT_CORE_MULTIPLIERS:
        sub_regions = _watershed_regions(region, distance, base_core_distance_px * multiplier)
        if len(sub_regions) < 2:
            continue
        kept = [
            (contour, True)
            for contour in (_room_contour(sub, wall_mask, probe_px) for sub in sub_regions)
            if contour is not None and _is_compact_room(contour)
        ]
        if len(kept) > len(best):
            best = kept

    if label_centroids_px:
        label_regions = _split_region_by_label_seeds(region, label_centroids_px, wall_angle_deg)
        if len(label_regions) >= 2:
            label_kept = [
                (contour, False)
                for contour in (_bare_contour(sub) for sub in label_regions)
                if contour is not None and _is_compact_room(contour)
            ]
            if len(label_kept) > len(best):
                best = label_kept

    return best if len(best) >= 2 else []


def _region_ink_density(contour: np.ndarray, ink: np.ndarray) -> float:
    """What share of a candidate room's own area carries drawing ink.

    Rendered per-contour into a bbox-sized scratch mask rather than a
    full-page one: a 6000x4200 sheet allocates ~25MP per call otherwise,
    once per candidate region, on a code path that already runs inside a
    parallel per-page worker.
    """
    x, y, w, h = cv2.boundingRect(contour)
    if w <= 0 or h <= 0:
        return 0.0
    local = np.zeros((h, w), dtype=np.uint8)
    cv2.drawContours(local, [contour - np.array([[x, y]])], -1, 255, thickness=cv2.FILLED)
    area_px = int((local > 0).sum())
    if area_px == 0:
        return 0.0
    ink_px = int((cv2.bitwise_and(ink[y : y + h, x : x + w], local) > 0).sum())
    return ink_px / area_px


def contour_wall_contact(contour: np.ndarray, wall_mask: np.ndarray, probe_px: int) -> float:
    """What share of a candidate room's own outline is up against wall ink.

    The contour-based twin of _wall_contact_ratio (which takes a filled
    region mask and is only reachable on the watershed path). Room
    candidates arriving from the enclosed-pocket and segment-fallback paths
    never pass through that check, so without this they reach the caller
    with no wall evidence attached at all — measured on a real sheet, all
    six candidates had 0.000 outline-on-wall and four of them were still
    reported at 0.95 confidence.

    Rendered bbox-local for the same reason as _region_ink_density.
    """
    x, y, w, h = cv2.boundingRect(contour)
    if w <= 0 or h <= 0:
        return 0.0
    pad = probe_px + 1
    x0, y0 = max(0, x - pad), max(0, y - pad)
    x1, y1 = min(wall_mask.shape[1], x + w + pad), min(wall_mask.shape[0], y + h + pad)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    local = np.zeros((y1 - y0, x1 - x0), dtype=np.uint8)
    cv2.drawContours(local, [contour - np.array([[x0, y0]])], -1, 255, thickness=cv2.FILLED)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (probe_px, probe_px))
    border = cv2.subtract(cv2.dilate(local, kernel), local)
    border_px = int((border > 0).sum())
    if border_px == 0:
        return 0.0
    touching = int((cv2.bitwise_and(border, wall_mask[y0:y1, x0:x1]) > 0).sum())
    return touching / border_px


def _region_text_coverage(contour: np.ndarray, text_mask: np.ndarray) -> float:
    """What share of a candidate room's own area is covered by printed text
    (see MAX_ROOM_TEXT_COVERAGE). Rendered bbox-local for the same reason
    as _region_ink_density.
    """
    x, y, w, h = cv2.boundingRect(contour)
    if w <= 0 or h <= 0:
        return 0.0
    local = np.zeros((h, w), dtype=np.uint8)
    cv2.drawContours(local, [contour - np.array([[x, y]])], -1, 255, thickness=cv2.FILLED)
    area_px = int((local > 0).sum())
    if area_px == 0:
        return 0.0
    text_px = int((cv2.bitwise_and(text_mask[y : y + h, x : x + w], local) > 0).sum())
    return text_px / area_px


def contour_compactness(area_px: float, perimeter_px: float) -> float:
    """Polsby-Popper compactness of a contour, in [0, 1]. Shape-only —
    independent of scale — so it is safe to apply before the pixel->feet
    conversion and unaffected by a wrong scale assumption.
    """
    if perimeter_px <= 0:
        return 0.0
    return float(4.0 * np.pi * area_px / (perimeter_px**2))


def _enclosed_pocket_regions(
    wall_mask: np.ndarray,
    dilation_px: int,
) -> list[tuple[np.ndarray, int, int]]:
    """Find rooms as enclosed pockets of free space after dilating the wall mask.

    Works by:
      1. Dilate the wall mask so thin gaps (doorways) get bridged.
      2. Invert to get free-space.
      3. Find connected components of free space whose bounding box does NOT
         touch the image edge — those are the inside-the-building pockets.

    This is the cv.py strategy. It produces excellent results on CAD drawings
    where walls are continuous thin lines forming closed room boundaries, and
    on any drawing where all rooms are genuinely fully enclosed. It fails on
    drawings where doorways are large open gaps that the dilation cannot bridge
    without also merging adjacent rooms — in that case the watershed path is
    superior.

    `dilation_px` controls how aggressively gaps are bridged. A small value
    leaves wide doorways open (rooms stay separate but some may not be enclosed),
    while a large value bridges doorways but can merge adjacent rooms through
    shared walls. The caller should sweep several values and keep whichever
    yields the most plausible number of rooms.
    """
    h, w = wall_mask.shape
    if dilation_px < 1:
        return []
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilation_px, dilation_px))
    barrier = cv2.dilate((wall_mask > 0).astype(np.uint8) * 255, kernel, iterations=1)
    free = cv2.bitwise_not(barrier)

    num, labels, stats, _ = cv2.connectedComponentsWithStats(free, connectivity=8)
    regions: list[np.ndarray] = []
    for label in range(1, num):
        x = int(stats[label, cv2.CC_STAT_LEFT])
        y = int(stats[label, cv2.CC_STAT_TOP])
        bw = int(stats[label, cv2.CC_STAT_WIDTH])
        bh = int(stats[label, cv2.CC_STAT_HEIGHT])
        # Discard any component whose bounding box touches the image border —
        # those are the exterior and margin regions that are reachable from outside.
        if x <= 0 or y <= 0 or x + bw >= w or y + bh >= h:
            continue
        # Comparing against the full-page `labels` array per surviving
        # component made this O(components * page_pixels) — a noisy/gappy
        # wall mask can produce hundreds of small enclosed pockets, and this
        # runs once per dilation radius the caller sweeps. Restricting the
        # equality check to the component's own bounding box keeps the same
        # result at a cost proportional to the component's own size.
        #
        # Also return only the cropped bounding-box region (with its page
        # offset) rather than a full page-sized array per component: on an
        # 8400x6000 sheet each full-size array is 48MB, and with hundreds of
        # small pockets surviving across a 6-value dilation sweep this
        # exhausted memory outright (measured: MemoryError allocating a 48MB
        # array with several GB already resident from earlier ones in the
        # same sweep). A component's own bounding box is typically a tiny
        # fraction of the page.
        sub_labels = labels[y : y + bh, x : x + bw]
        region = np.where(sub_labels == label, np.uint8(255), np.uint8(0))
        regions.append((region, x, y))
    return regions


def _dominant_wall_angle_deg(wall_mask: np.ndarray) -> float:
    """The building's own axis, not the page's. CAD sheets are occasionally
    drafted a degree or two off the page (or scanned/rasterized slightly
    skewed) — snapping to page-horizontal in that case would fight the real
    wall angle instead of cleaning it up. `cv2.minAreaRect` over every wall
    pixel finds the rectangle that actually bounds the wall mass tightly,
    whose angle is the building's dominant orientation.
    """
    points = cv2.findNonZero((wall_mask > 0).astype(np.uint8))
    if points is None or len(points) < 10:
        return 0.0
    angle = cv2.minAreaRect(points)[-1]
    # OpenCV's angle can reference either side of the rect depending on
    # aspect ratio, so it lands anywhere in [0, 90). Fold into [-45, 45] —
    # a wall mass is symmetric under 90-degree rotation, so this is the
    # true angle regardless of which side minAreaRect picked.
    angle = angle % 90.0
    if angle > 45.0:
        angle -= 90.0
    return angle


def _regularize_polygon(pts: np.ndarray, angle_deg: float) -> np.ndarray:
    """Snap a room polygon's near-axis-aligned edges to exactly
    horizontal/vertical in the building's own frame, and let right-angle
    corners fall out of that (see ORTHOGONAL_SNAP_MAX_ANGLE_DEG for why).

    Works by iterative constraint relaxation: rotate the polygon into the
    building's axis-aligned frame, then repeatedly average each near-axis
    edge's two endpoints onto a single shared y (horizontal) or x
    (vertical). A vertex shared by a horizontal and a vertical edge gets
    pulled by both constraints each pass and converges on their true
    intersection — i.e. a clean corner — within a few iterations, without
    needing to solve the corner system explicitly.
    """
    if len(pts) < 3:
        return pts

    theta = math.radians(angle_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    rot = np.array([[cos_t, sin_t], [-sin_t, cos_t]])
    rotated = pts.astype(np.float64) @ rot.T

    n = len(rotated)
    for _ in range(ORTHOGONAL_SNAP_ITERATIONS):
        new_pts = rotated.copy()
        for i in range(n):
            j = (i + 1) % n
            dx = rotated[j, 0] - rotated[i, 0]
            dy = rotated[j, 1] - rotated[i, 1]
            if math.hypot(dx, dy) < 1e-6:
                continue
            edge_angle = abs(math.degrees(math.atan2(dy, dx))) % 180.0
            near_horizontal = (
                edge_angle < ORTHOGONAL_SNAP_MAX_ANGLE_DEG
                or edge_angle > 180.0 - ORTHOGONAL_SNAP_MAX_ANGLE_DEG
            )
            near_vertical = abs(edge_angle - 90.0) < ORTHOGONAL_SNAP_MAX_ANGLE_DEG
            if near_horizontal:
                avg_y = (rotated[i, 1] + rotated[j, 1]) / 2.0
                new_pts[i, 1] = avg_y
                new_pts[j, 1] = avg_y
            elif near_vertical:
                avg_x = (rotated[i, 0] + rotated[j, 0]) / 2.0
                new_pts[i, 0] = avg_x
                new_pts[j, 0] = avg_x
        rotated = new_pts

    inv_rot = np.array([[cos_t, -sin_t], [sin_t, cos_t]])
    result = rotated @ inv_rot.T

    # Adjacent edges can collapse onto each other once snapped (a near-zero
    # -length edge that was only there to approximate a slight curve/notch).
    cleaned = [result[0]]
    for p in result[1:]:
        if math.hypot(*(p - cleaned[-1])) > 1.0:
            cleaned.append(p)
    if len(cleaned) > 1 and math.hypot(*(cleaned[0] - cleaned[-1])) < 1.0:
        cleaned.pop()

    if len(cleaned) < 3:
        return pts
    return np.round(np.array(cleaned)).astype(np.int32)


def detect_room_polygons(
    wall_mask: np.ndarray,
    scale_ft_per_px: float,
    scale_is_calibrated: bool = False,
    room_label_centroids_px: list[tuple[float, float]] | None = None,
    walls_are_authoritative: bool = False,
    ink: np.ndarray | None = None,
    text_mask: np.ndarray | None = None,
    wall_evidence_mask: np.ndarray | None = None,
) -> list[RoomCandidate]:
    """Watershed-segment the building's interior into rooms, then
    contour + polygon-approximate each region.

    Returns (polygon, wall_verified) pairs. `wall_verified` is False when
    at least one edge of that polygon is a synthetic cut between two OCR
    room-label positions rather than a real wall (see _bare_contour and
    _split_region_by_label_seeds) — the caller must not present such a
    room with the same confidence as a wall-enclosed one.

    Regions are gated on size, shape compactness, and wall contact, so that
    fragments left behind by imperfect wall linework are rejected rather
    than reported as rooms.

    `scale_is_calibrated` selects which size gate applies: real-world sqft
    when the page's scale is genuinely known, page-relative area otherwise
    (see MIN_ROOM_AREA_SQFT for why an assumed scale must not be trusted
    to delete rooms).

    `room_label_centroids_px` (optional) is where OCR found printed room
    names — pixel positions only, no dependency on room polygons, since
    room-label classification runs on text pattern alone (see
    ocr.parsers.classify_tokens). Used only as a last-resort seed for
    splitting a region the wall-derived core sweep still can't separate
    (see _split_merged_region) — every gate above still applies to what it
    produces, this only supplies additional candidate splits to try.

    Returns a list of (N, 2) int arrays of pixel coordinates, one closed
    polygon per detected room.
    """
    h, w = wall_mask.shape

    envelope = building_envelope_mask(wall_mask, walls_are_authoritative)
    if envelope is None:
        points = cv2.findNonZero((wall_mask > 0).astype(np.uint8))
        if points is None or len(points) < 10:
            return []
        envelope = np.zeros_like(wall_mask)
        cv2.drawContours(envelope, [cv2.convexHull(points)], -1, 255, thickness=cv2.FILLED)
    interior = cv2.bitwise_and(envelope, cv2.bitwise_not(wall_mask))

    distance = cv2.distanceTransform((interior > 0).astype(np.uint8), cv2.DIST_L2, 5)
    largest_clearance = float(distance.max())

    if scale_is_calibrated and scale_ft_per_px > 0:
        core_distance_px = ROOM_CORE_DISTANCE_FT / scale_ft_per_px
        # Keep the threshold within reach of this drawing so a wrong/stale
        # calibration can never demand more clearance than exists anywhere
        # and silently erase every room.
        core_distance_px = min(core_distance_px, largest_clearance * MAX_CORE_DISTANCE_FRACTION)
    else:
        core_distance_px = max(h, w) * ROOM_CORE_DISTANCE_PAGE_RATIO
        # Still cap against this drawing's actual clearance, so a page whose
        # rooms are all smaller than the nominal doorway scale still yields
        # cores rather than none at all.
        core_distance_px = min(core_distance_px, largest_clearance * MAX_CORE_DISTANCE_FRACTION)

    core_distance_px = max(core_distance_px, MIN_CORE_DISTANCE_PX)

    probe_px = max(3, wall_mask_thickness_px((h, w)) * 2 + 1)
    page_area_px = h * w
    # Needed by both the label-split seeding below and the polygon
    # regularization further down, so it is measured once here.
    wall_angle_deg = _dominant_wall_angle_deg(wall_mask)

    # (contour, wall_verified) — see room_confidence for what the flag gates.
    contours: list[tuple[np.ndarray, bool]] = []
    for region in _watershed_regions(interior, distance, core_distance_px):
        # Drop regions that aren't actually walled in (see _wall_contact_ratio).
        contour = _room_contour(region, wall_mask, probe_px)
        if contour is None:
            continue

        # A region containing 2+ printed room-name labels is several rooms
        # regardless of overall shape: a merged blob spanning multiple real
        # offices is often still a fairly regular rectangle (it passes
        # _is_compact_room easily), so gating the label split on "did this
        # fail compactness" — as below — never even reached it for exactly
        # the multi-office CAD sheets this was built for. Two independent
        # room names inside one region is stronger evidence of a merge than
        # shape regularity is evidence against one, so this is tried first,
        # before the compactness check decides to keep the region whole.
        if room_label_centroids_px:
            labels_inside = _label_centroids_in_region(region, room_label_centroids_px)
            if len(labels_inside) >= 2:
                label_regions = _split_region_by_label_seeds(region, labels_inside, wall_angle_deg)
                label_kept = [
                    (c, False)
                    for c in (_bare_contour(sub) for sub in label_regions)
                    if c is not None and _is_compact_room(c)
                ]
                if len(label_kept) >= 2:
                    contours.extend(label_kept)
                    continue

        if _is_compact_room(contour):
            contours.append((contour, True))
            continue
        # Too convoluted to be one room. Rather than discarding it — which
        # silently erased every room in a whole wing on a plan with wide
        # cased openings — try to separate it into the rooms it actually is.
        if cv2.contourArea(contour) < page_area_px * ROOM_SPLIT_MIN_AREA_RATIO:
            continue
        contours.extend(
            _split_merged_region(
                region,
                distance,
                wall_mask,
                probe_px,
                core_distance_px,
                room_label_centroids_px,
                wall_angle_deg,
            )
        )

    sqft_per_px = scale_ft_per_px**2 if scale_ft_per_px > 0 else 0.0
    use_real_world_gate = scale_is_calibrated and sqft_per_px > 0

    page_max_area_px = page_area_px * MAX_ROOM_AREA_RATIO
    page_min_area_px = page_area_px * MIN_ROOM_AREA_RATIO

    def _select_contours(
        real_world_gate: bool, input_contours: list[tuple[np.ndarray, bool]]
    ) -> list[RoomCandidate]:
        selected: list[RoomCandidate] = []
        for contour, wall_verified in input_contours:
            area_px = cv2.contourArea(contour)
            perimeter_px = cv2.arcLength(contour, True)
            if area_px <= 0 or perimeter_px <= 0:
                continue

            # A polygon covering most of the sheet is the building envelope
            # caught whole (interior walls didn't close), not one room.
            if area_px > page_max_area_px:
                continue

            # Blank hull dead-space, not a room (see MIN_ROOM_INK_DENSITY).
            if ink is not None and _region_ink_density(contour, ink) < MIN_ROOM_INK_DENSITY:
                continue

            # A block of printed text, not a room (see MAX_ROOM_TEXT_COVERAGE).
            if text_mask is not None and _region_text_coverage(contour, text_mask) > MAX_ROOM_TEXT_COVERAGE:
                continue

            if real_world_gate:
                area_sqft = area_px * sqft_per_px
                if area_sqft < MIN_ROOM_AREA_SQFT or area_sqft > MAX_ROOM_AREA_SQFT:
                    continue
            elif area_px < page_min_area_px:
                continue

            if contour_compactness(area_px, perimeter_px) < MIN_ROOM_COMPACTNESS:
                continue

            epsilon = POLY_APPROX_EPSILON_RATIO * perimeter_px
            approx = cv2.approxPolyDP(contour, epsilon, True)
            pts = approx.reshape(-1, 2)
            if len(pts) >= 3:
                pts = _regularize_polygon(pts, wall_angle_deg)
            if len(pts) >= 3:
                # Measured against INDEPENDENT wall evidence where the
                # caller can supply it, never against the mask that
                # produced this polygon. Measured the circular way first
                # and it does not discriminate: a room carved out of the
                # Hough-segment fallback mask trivially touches that same
                # mask, so three exterior patio/slab polygons scored
                # 0.765/0.500/0.486 — overlapping the 0.575-0.926 range of
                # genuinely wall-bounded rooms. Scored against the raster
                # wall band instead (an independent stroke-thickness
                # signal) the same three scored 0.333/0.252/0.000.
                # No independent evidence available at all means exactly
                # that: we have measured no wall support, and must report
                # 0.0 rather than fall back to the producing mask. Falling
                # back was verified to reinstate the bug — on a sheet whose
                # raster wall band comes out unusable, every title-block
                # candidate scored 0.859-0.569 against the segment mask
                # that had just carved it out, versus 0.000 against real
                # wall ink. An unverifiable room must not be certifiable.
                if wall_evidence_mask is None:
                    contact = 0.0
                else:
                    contact = contour_wall_contact(pts.reshape(-1, 1, 2), wall_evidence_mask, probe_px)
                selected.append(RoomCandidate(pts, wall_verified, contact))
        return selected

    polygons = _select_contours(use_real_world_gate, contours)

    # A scale that is wrong by a large factor makes every real room measure
    # far too small (or too large) and the sqft gate then rejects all of
    # them, reporting an empty page as though nothing were detected. The
    # room shapes are independent of scale and still valid, so fall back to
    # the scale-free gate rather than returning nothing: wrong areas are
    # recoverable by recalibrating, silently missing rooms is not.
    if use_real_world_gate and not polygons:
        polygons = _select_contours(False, contours)

    if not polygons and room_label_centroids_px:
        label_regions = _split_region_by_label_seeds(interior, room_label_centroids_px, wall_angle_deg)
        label_contours = [
            (c, False)
            for c in (_bare_contour(sub) for sub in label_regions)
            if c is not None and contour_compactness(cv2.contourArea(c), cv2.arcLength(c, True)) >= MIN_ROOM_COMPACTNESS
        ]
        polygons = _select_contours(False, label_contours)

    # --- Enclosed-pocket strategy (cv.py approach) ---
    # If watershed produced few rooms (≤ 3), also try the enclosed-pocket
    # strategy: dilate walls to bridge doorway gaps, invert to get free space,
    # keep only CC pockets that don't touch the image border. This works
    # especially well on CAD drawings with thin complete wall boundaries.
    # Try several dilation radii — smaller keeps rooms separate, larger bridges
    # wider doorways. We take whichever produces more valid rooms.
    #
    # Only runs when watershed is under-performing (≤ 3 rooms). If watershed
    # already finds many rooms, it stays authoritative because it is more robust
    # on drawings with large open-plan doorways where the pocket approach merges
    # adjacent rooms through the dilated wall.
    if len(polygons) <= 3:
        long_edge = max(h, w)
        # Dilation radii to try: from 1 wall-thickness up to ~3ft equivalent.
        # Smaller radii leave wide doorways open but won't merge rooms through
        # shared walls. The sweep finds the sweet spot automatically.
        base_thickness = wall_mask_thickness_px((h, w))
        dilation_candidates = sorted(set([
            base_thickness,
            base_thickness * 2,
            base_thickness * 3,
            max(5, long_edge // 250),
            max(9, long_edge // 150),
            max(15, long_edge // 100),
        ]))

        best_pocket_polygons: list[RoomCandidate] = []
        for dil_px in dilation_candidates:
            pocket_regions = _enclosed_pocket_regions(wall_mask, dil_px)
            # Pocket boundaries ARE the dilated wall mask itself, so every
            # edge of one is wall-derived — verified, unlike a label cut.
            pocket_contours: list[tuple[np.ndarray, bool]] = []
            for region, x_off, y_off in pocket_regions:
                contour_list, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if not contour_list:
                    continue
                largest = max(contour_list, key=cv2.contourArea)
                # Contour points are in the cropped region's own coordinate
                # space — shift back to page coordinates (see
                # _enclosed_pocket_regions for why it returns a crop).
                largest = largest + np.array([[x_off, y_off]], dtype=largest.dtype)
                pocket_contours.append((largest, True))
            pocket_polygons = _select_contours(use_real_world_gate, pocket_contours)
            if not pocket_polygons and use_real_world_gate:
                pocket_polygons = _select_contours(False, pocket_contours)
            if len(pocket_polygons) > len(best_pocket_polygons):
                best_pocket_polygons = pocket_polygons

        # Accept pocket result if it beats watershed by at least 2 rooms
        # (avoids replacing a correctly-sparse watershed with slightly-noisy
        # pocket output on a simple 2-room plan).
        if len(best_pocket_polygons) > len(polygons) + 1:
            polygons = best_pocket_polygons

    return polygons

