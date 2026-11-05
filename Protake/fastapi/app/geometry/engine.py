"""Orchestrates the deterministic geometry analysis pipeline for one
rasterized blueprint page:

    grayscale -> Hough lines -> collinear merge -> wall graph
        -> wall mask -> flood-fill room detection -> Shapely metrics

This is the primary QTO engine. Nothing here is AI-driven or
probabilistic beyond the (documented, tunable) thresholds in each
submodule — the same image always yields the same rooms and walls.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from app.geometry.drawing_zone import MIN_DRAWING_ZONE_OVERLAP, segment_bbox_norm
from app.geometry.line_extraction import (
    Segment,
    extract_raw_segments,
    extract_wall_segments_from_mask,
    filter_wall_candidates,
    merge_collinear_segments,
)
from app.geometry.metrics import (
    DEFAULT_SCALE_FT_PER_PX,
    ScaleContext,
    measure_wall_thickness_from_faces,
    measure_wall_thickness_ft,
    wall_length_ft,
)
from app.geometry.page_context import PageContext
from app.geometry.polygon_ops import contour_raster_wall_contact, polygon_metrics, room_confidence, wall_touches_room
from app.geometry.room_validation import RoomEvidence, evaluate_room_candidate


from app.geometry.room_detector import (
    EXTERIOR_AREA_ROOM_TYPE,
    build_wall_mask,
    detect_exterior_area_polygons,
    detect_room_polygons,
    wall_mask_thickness_px,
)
from app.geometry.vector_walls import extract_wall_mask_from_layers
from app.geometry.vector_windows import extract_window_polygons_from_layers
from app.geometry.wall_band import extract_wall_band_mask, ink_mask
from app.geometry.wall_graph import (
    build_wall_graph,
    classify_wall_orientation,
    segment_is_connected,
    wall_confidence,
    wall_segments_bbox,
)
from app.geometry.wall_validation import WallEvidence, evaluate_wall_candidate
from app.models.enums import ReviewStatus

logger = logging.getLogger("protake")


@dataclass
class GeometryRoom:
    name: str
    polygon_norm: list[list[float]]
    bbox_norm: dict
    centroid_norm: dict
    area_sqft: float
    perimeter_ft: float
    confidence: float
    # None for an ordinary enclosed room. Set to
    # room_detector.EXTERIOR_AREA_ROOM_TYPE for a covered exterior area
    # (porch/deck), which has floor and roof but no drywall or painted
    # wall surface — pricing must not treat the two the same.
    room_type: str | None = None
    # Set by room_validation.evaluate_room_candidate — PENDING for an
    # ordinary reviewable room, REJECTED when the candidate fell outside
    # the sheet's drawing zone or scored low wall contact (title-block box,
    # exterior slab caught by the wall mask). Never silently dropped either
    # way — both statuses are persisted, only distinguished (see
    # REPOSITORY_AUDIT_AND_MIGRATION_PLAN.md Finding F2).
    status: ReviewStatus = ReviewStatus.PENDING
    rejection_reasons: list[str] = field(default_factory=list)
    _shapely_index: int = field(repr=False, default=-1)
    boundary_edges: list[dict] = field(default_factory=list)
    bidirectional_verified: bool = False


@dataclass
class GeometryWall:
    start_norm: dict
    end_norm: dict
    length_ft: float
    wall_type: str
    room_index: int | None
    confidence: float
    thickness_ft: float | None = None
    thickness_measured: bool = False
    wall_type_code: str | None = None
    status: ReviewStatus = ReviewStatus.PENDING
    rejection_reasons: list[str] = field(default_factory=list)
    source: str = "unknown"
    face_a_segment_id: int | None = None
    face_b_segment_id: int | None = None
    face_a_coords: dict | None = None
    face_b_coords: dict | None = None
    overlap_ratio: float | None = None
    # DEF-01: height provenance must be stored so it is never silently assumed.
    height_ft: float = 9.0
    height_source: str = "ASSUMED"
    # D-004: Bidirectional Room <-> Wall Context Attributes
    side_a_room_index: int | None = None
    side_a_direction: str | None = None
    side_b_room_index: int | None = None
    side_b_direction: str | None = None
    bidirectional_verified: bool = False


@dataclass
class GeometryWindow:
    """A window found on the PDF's own WINDOW-named vector layer (see
    vector_windows.extract_window_polygons_from_layers) — a deterministic
    geometric measurement, not a raster-model guess, so it carries
    DetectionSource.GEOMETRY when persisted rather than YOLO.
    """

    polygon_norm: list[list[float]]
    bbox_norm: dict


@dataclass
class GeometryDoor:
    """A door found on the PDF's own DOOR-named vector layer (see
    vector_doors.extract_door_polygons_from_layers).
    """

    polygon_norm: list[list[float]]
    bbox_norm: dict


@dataclass
class GeometryStairs:
    """Stairs found on the PDF's own stair-named vector layer (see
    vector_stairs.extract_stairs_polygons_from_layers).
    """

    polygon_norm: list[list[float]]
    bbox_norm: dict


@dataclass
class GeometryResult:
    rooms: list[GeometryRoom]
    walls: list[GeometryWall]
    wall_segment_count_raw: int
    wall_segment_count_merged: int
    page_type: str = "floor_plan"
    is_takeoff_eligible: bool = True
    skip_reason: str | None = None
    # Carried from page_classifier.ClassificationResult — computed on every
    # page (both eligible and ineligible) but previously dropped before
    # reaching the Page row, forcing the frontend to re-derive a cruder
    # discipline guess itself. See blueprint_service.run_geometry_analysis,
    # which persists these onto Page.
    discipline: str = "General"
    primary_title: str = "ARCHITECTURAL SHEET"
    classification_confidence: float = 0.95
    geometry_authority: str = "NONE"
    # Populated only when the PDF has its own WINDOW vector layer; empty
    # otherwise (the normal case), in which case the YOLO pass is still the
    # only source of window detections for that page.
    windows: list[GeometryWindow] = field(default_factory=list)
    # Populated only when the PDF has its own DOOR vector layer; empty otherwise.
    doors: list[GeometryDoor] = field(default_factory=list)
    # Populated only when the PDF has its own stair vector layer; empty otherwise.
    stairs: list[GeometryStairs] = field(default_factory=list)
    # Architectural Physics & Multi-Constraint Verification Report
    physics_report: Any | None = None


def _extract_page_text_fast(pdf_path: str, page_number: int) -> list[str]:
    """Instant word extraction straight from the original vector PDF (same
    trick as app.ocr.paddle_engine's Method 1) — used only for page
    classification, so a scanned/text-less PDF just falls back to an
    empty token list rather than paying for full OCR here.
    """
    try:
        import fitz

        with fitz.open(pdf_path) as doc:
            page = doc.load_page(page_number - 1)
            return [w[4] for w in page.get_text("words") if w[4].strip()]
    except Exception:
        return []


def _extract_page_word_boxes_px(
    pdf_path: str, page_number: int, image_w: int, image_h: int
) -> list[tuple[float, float, float, float]]:
    """Every word's bounding box on the original vector PDF, in this page's
    raster pixel space. Free (no OCR pass) for any PDF with real text —
    reuses the same `get_text("words")` call as `_extract_page_text_fast`,
    just keeping the coordinates this time instead of discarding them.

    Used to keep general notes, key notes, legends, and printed labels out
    of Hough line detection entirely (see the caller). Verified on a real
    finish-plan sheet: the general-notes/key-notes/flooring-legend block at
    the bottom of the page produced MORE total "wall-run"-qualifying pixel
    mass than either half of the actual building — comparing cluster sizes
    against each other can't tell the two apart, because the noise cluster
    is sometimes the bigger one. Removing the text before it ever becomes a
    line segment sidesteps that entirely.
    """
    try:
        import fitz

        with fitz.open(pdf_path) as doc:
            page = doc.load_page(page_number - 1)
            page_w, page_h = page.rect.width, page.rect.height
            if page_w <= 0 or page_h <= 0:
                return []
            sx, sy = image_w / page_w, image_h / page_h
            return [
                (w[0] * sx, w[1] * sy, w[2] * sx, w[3] * sy)
                for w in page.get_text("words")
                if w[4].strip()
            ]
    except Exception:
        return []


def extract_page_text_items_norm(
    pdf_path: str, page_number: int
) -> list[tuple[float, float, float, float, str]]:
    """Every word as (x0, y0, x1, y1, text) in normalized 0-1 page space.

    The two extractors above each throw away half of what wall-tag
    resolution needs: `_extract_page_text_fast` keeps the word and drops
    its box, `_extract_page_word_boxes_px` keeps the box and drops the
    word. Both call the same `get_text("words")`, which has had both all
    along. Tag matching is inherently spatial — `WallTagResolver.
    match_tag_to_wall` scores a tag against a wall midpoint with a 0.06
    tolerance in normalized space — so a tag string without its position
    cannot be attached to a wall at all, which is why the drywall
    pipeline has been running with an empty tag list.

    Normalized (not pixel) because every downstream consumer — wall
    `start_norm`/`end_norm`, room polygons, detection bboxes — is already
    normalized, so this needs no page-resolution argument and stays
    correct regardless of the DPI a page happened to be rasterized at.
    """
    try:
        import fitz

        with fitz.open(pdf_path) as doc:
            page = doc.load_page(page_number - 1)
            page_w, page_h = page.rect.width, page.rect.height
            if page_w <= 0 or page_h <= 0:
                return []
            return [
                (w[0] / page_w, w[1] / page_h, w[2] / page_w, w[3] / page_h, w[4].strip())
                for w in page.get_text("words")
                if w[4].strip()
            ]
    except Exception:
        return []


def _extract_spatial_room_name(
    polygon_norm: list[list[float]],
    text_items: list[tuple[float, float, float, float, str]],
    default_name: str,
) -> str:
    """Extracts genuine room name from text items falling inside polygon_norm."""
    if not text_items or not polygon_norm or len(polygon_norm) < 3:
        return default_name
    try:
        from shapely.geometry import Polygon, Point
        poly = Polygon(polygon_norm)
        if not poly.is_valid:
            poly = poly.buffer(0)
        words_inside: list[str] = []
        for x0, y0, x1, y1, text in text_items:
            pt = Point((x0 + x1) / 2.0, (y0 + y1) / 2.0)
            if poly.contains(pt):
                words_inside.append(text.strip())
        if not words_inside:
            return default_name
            
        KNOWN_ROOM_KEYWORDS = [
            "TOILET", "RESTROOM", "BATHROOM", "BATH", "WC", "LAVATORY", "HAMMAM", "SAUNA",
            "CORRIDOR", "HALL", "HALLWAY", "PASSAGE", "LOBBY", "FOYER", "VESTIBULE",
            "STAIR", "STAIRWAY", "STAIRWELL", "STAIRCASE",
            "SHAFT", "CHASE", "PIPE CHASE", "ELEVATOR", "ELEV",
            "OFFICE", "STORAGE", "STOR", "MECH", "MECHANICAL", "ELECTRICAL", "ELEC",
            "BEDROOM", "LIVING", "KITCHEN", "DINING", "UNIT", "SUITE", "APT", "CLOSET"
        ]
        joined = " ".join(words_inside).upper()
        for kw in KNOWN_ROOM_KEYWORDS:
            if kw in joined:
                matching_tokens = [w for w in words_inside if any(c.isalnum() for c in w)]
                if len(matching_tokens) <= 4:
                    return " ".join(matching_tokens)
                return kw
        clean_tokens = [w for w in words_inside if len(w) > 2 and any(c.isalpha() for c in w) and not any(c in w for c in "/#=")]
        if clean_tokens:
            return " ".join(clean_tokens[:3])
        return default_name
    except Exception:
        return default_name


def analyze_page(
    image_path: str,
    scale_ft_per_px: float | None = None,
    pdf_path: str | None = None,
    page_number: int | None = None,
    scale_is_calibrated: bool = False,
    ocr_text_boxes_px: list[tuple[float, float, float, float]] | None = None,
    ocr_room_label_centroids_px: list[tuple[float, float]] | None = None,
    scale_context: ScaleContext | None = None,
    selected_trade: str | None = None,
    door_detections: list | None = None,
    doc_ctx_entry: dict | None = None,
) -> GeometryResult:
    """`scale_is_calibrated` should be True only when `scale_ft_per_px` was
    genuinely established (user calibration, or a scale annotation read off
    the sheet) rather than assumed. Size filters switch to real-world units
    when it is set, and to scale-free page-relative ones when it isn't, so
    that a wrong scale assumption cannot silently delete valid geometry.

    `ocr_text_boxes_px` is optional and purely a spatial hint — it tells the
    wall-band mask where printed text sits so those pixels can be erased
    before any wall/room geometry is derived from the mask (see
    wall_band.erase_text_regions). This does not violate "OCR never
    calculates geometry": no measurement here comes from OCR, it only says
    where NOT to look for wall pixels. Callers that don't have OCR results
    yet (or choose not to fetch them) simply omit it.

    `ocr_room_label_centroids_px` is similarly a spatial hint, not a
    measurement — where printed room names are, in case wall data is
    incomplete enough that a whole wing merges into one region no core-
    distance retry can separate (see room_detector._split_region_by_label_seeds).

    `selected_trade` is passed through into the PageContext handed to
    wall_validation.evaluate_wall_candidate and logged with every wall
    decision (see the debug log below), so it is genuinely available at
    the point walls are accepted/rejected. It intentionally does not gate
    or filter geometry itself: the same blueprint's wall/room geometry
    must stay identical regardless of which trade a project has selected
    (see FORENSIC_AUDIT_REPORT.md's discussion of why geometry is
    trade-agnostic by design) — trade-specific interpretation belongs
    downstream, in the trade engines that consume this geometry. None
    when the caller has no explicit trade selection to pass, which is the
    common case; never assumed.
    """
    # Resolve the page's scale FIRST, before any wall or room candidate
    # exists, so every physical constraint below can be evaluated in real
    # units and can distinguish a measured scale from an assumed one.
    # `scale_context`, when supplied, is authoritative and supersedes the
    # two scalar parameters; those remain accepted for callers that have
    # not migrated and are adapted via ScaleContext.from_legacy, so their
    # behaviour is unchanged.
    if scale_context is None:
        scale_context = ScaleContext.from_legacy(
            scale_ft_per_px,
            scale_is_calibrated,
            dpi=8.0 / DEFAULT_SCALE_FT_PER_PX,
        )
    scale = scale_context.ft_per_px
    scale_is_calibrated = scale_context.is_calibrated

    image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError(f"Could not read page image at {image_path}")
    if image.ndim == 3:
        # cv2.imread(..., IMREAD_GRAYSCALE) is supposed to always return a
        # plain (H, W) array, but on Windows, after ultralytics/PyTorch has
        # been used earlier in the same process (loading a YOLO model for
        # AI validation), it starts returning (H, W, 1) instead — a known
        # class of native-library conflict between PyTorch's and OpenCV's
        # bundled DLLs, not anything wrong with the file itself (verified:
        # the same file loads correctly as (H, W) in a fresh process, and
        # loads as (H, W, 1) in the same process right after running YOLO
        # detection, with no other change). Concretely, this broke every
        # page after the first one handled by a given pool worker — 11 of
        # 14 pages on a real upload, since PAGE_PARALLELISM reuses each
        # worker for several pages and only the first per worker had run
        # YOLO zero times before its own geometry pass. Squeezing the
        # trailing channel here is correct regardless of which library's
        # DLL is actually misbehaving.
        image = image[:, :, 0]
    h, w = image.shape

    # Blank out printed text before Hough ever sees it. General notes, key
    # notes, legends, and room labels routinely contain straight edges long
    # enough to pass the wall-candidate length test (list separators, table
    # borders, legend swatch outlines, underlines) — see
    # _extract_page_word_boxes_px for a real measured case where this text
    # block alone out-massed the actual building's wall network, which is
    # why filtering by "the biggest cluster is the building" doesn't work.
    # A local copy: `image` itself is still used unmodified below for ink
    # density and room-label OCR context.
    hough_input = image
    word_boxes_px = _extract_page_word_boxes_px(pdf_path, page_number, w, h) if pdf_path and page_number else []
    if word_boxes_px:
        hough_input = image.copy()
        # Same background-detection as wall_band.ink_mask
        values, counts = np.unique(image, return_counts=True)
        background = int(values[int(counts.argmax())])
        pad = 1

        # Identify dense text blocks (notes/legends) to blank out, while preserving
        # small isolated wall tags (W1, W2), door tags, and single annotations
        # so we don't punch rectangular holes through wall centerlines.
        for idx, (x0, y0, x1, y1) in enumerate(word_boxes_px):
            box_w = max(0, x1 - x0)
            box_h = max(0, y1 - y0)
            box_area = box_w * box_h

            # Check if this word is part of a dense cluster of nearby text (notes / tables)
            has_neighbors = any(
                idx != j and abs(x0 - bx0) < 60 and abs(y0 - by0) < 60
                for j, (bx0, by0, bx1, by1) in enumerate(word_boxes_px)
            )

            # Only blank large blocks or clustered notes text
            if box_area > 1200 or has_neighbors:
                xi0, yi0 = max(0, int(x0) - pad), max(0, int(y0) - pad)
                xi1, yi1 = min(w, int(x1) + pad), min(h, int(y1) + pad)
                if xi1 > xi0 and yi1 > yi0:
                    hough_input[yi0:yi1, xi0:xi1] = background

    # For vector PDFs, try direct path extraction first (Track B Upgrade)
    vector_segments = []
    if pdf_path and page_number:
        try:
            import fitz
            doc = fitz.open(pdf_path)
            src_page = doc[page_number - 1]
            page_w_pt, page_h_pt = src_page.rect.width, src_page.rect.height
            scale_x = w / page_w_pt
            scale_y = h / page_h_pt
            seg_idx = 0
            from app.geometry.vector_walls import _NON_WALL_LAYER_SUBSTRINGS, is_structural_layer

            for path in src_page.get_drawings():
                layer = (path.get("layer") or "").lower()
                width = path.get("width") or 0.0
                if any(b in layer for b in _NON_WALL_LAYER_SUBSTRINGS):
                    continue
                is_wall = "wall" in layer
                is_struct = is_structural_layer(layer)
                if layer and not (is_wall or (is_struct and width >= 0.51)):
                    continue

                for item in path.get("items", []):
                    if item[0] == "l":
                        p1, p2 = item[1], item[2]
                        x1, y1 = p1.x * scale_x, p1.y * scale_y
                        x2, y2 = p2.x * scale_x, p2.y * scale_y
                        if abs(x1 - x2) < 0.1 and abs(y1 - y2) < 0.1:
                            continue
                        vector_segments.append(
                            Segment(
                                x1,
                                y1,
                                x2,
                                y2,
                                id=seg_idx,
                                source_type="vector",
                                raw_coords=(float(p1.x), float(p1.y), float(p2.x), float(p2.y)),
                            )
                        )
                        seg_idx += 1
                    elif item[0] == "re":
                        rect = item[1]
                        x0, y0 = rect.x0 * scale_x, rect.y0 * scale_y
                        x1, y1 = rect.x1 * scale_x, rect.y1 * scale_y
                        vector_segments.append(
                            Segment(
                                x0,
                                y0,
                                x1,
                                y0,
                                id=seg_idx,
                                source_type="vector",
                                raw_coords=(float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y0)),
                            )
                        )
                        seg_idx += 1
                        vector_segments.append(
                            Segment(
                                x1,
                                y0,
                                x1,
                                y1,
                                id=seg_idx,
                                source_type="vector",
                                raw_coords=(float(rect.x1), float(rect.y0), float(rect.x1), float(rect.y1)),
                            )
                        )
                        seg_idx += 1
                        vector_segments.append(
                            Segment(
                                x1,
                                y1,
                                x0,
                                y1,
                                id=seg_idx,
                                source_type="vector",
                                raw_coords=(float(rect.x1), float(rect.y1), float(rect.x0), float(rect.y1)),
                            )
                        )
                        seg_idx += 1
                        vector_segments.append(
                            Segment(
                                x0,
                                y1,
                                x0,
                                y0,
                                id=seg_idx,
                                source_type="vector",
                                raw_coords=(float(rect.x0), float(rect.y1), float(rect.x0), float(rect.y0)),
                            )
                        )
                        seg_idx += 1
        except Exception as exc:
            print(f"[Protake] Vector path extraction notice: {exc}")

    if vector_segments:
        raw_segments = vector_segments
        merged_segments = merge_collinear_segments(raw_segments, (h, w))
    else:
        raw_segments = extract_raw_segments(hough_input)
        merged_segments = merge_collinear_segments(raw_segments, (h, w))

    # Top-Level Classifier Guard: Check line density & text page eligibility.
    # Real title-block text (when the original vector PDF is available) lets
    # the classifier tell floor plans, roof plans, elevations, and sections
    # apart — without it, classification falls back to line-density only.
    from app.geometry.page_classifier import classify_page_content

    raw_text_tokens = _extract_page_text_fast(pdf_path, page_number) if pdf_path and page_number else []
    classification = classify_page_content(image_path, raw_text_tokens, len(merged_segments))
    if not classification.is_takeoff_eligible:
        logger.info(
            "PAGE STAGE LOG [page=%s type=%s eligible=False]: "
            "total_vector_items=%d, filtered_vector_items=%d, drawing_region_items=0, "
            "candidate_segments=0, wall_pairs=0, approved_walls=0, rejected_walls=0, "
            "drywall_scope_confirmed=0, qto_walls=0 | skip_reason='%s'",
            page_number,
            classification.page_type.value,
            len(raw_segments),
            len(merged_segments),
            classification.skip_reason,
        )
        # Return empty geometry for non-drawing / text / electrical / egress / finish / elevation pages
        return GeometryResult(
            rooms=[],
            walls=[],
            wall_segment_count_raw=len(raw_segments),
            wall_segment_count_merged=len(merged_segments),
            page_type=classification.page_type.value,
            is_takeoff_eligible=False,
            skip_reason=classification.skip_reason,
            discipline=classification.discipline,
            primary_title=classification.primary_title,
            classification_confidence=classification.confidence,
            geometry_authority=classification.geometry_authority,
        )

    # Exclude Title Block Margin Zone (right 4% of page width)
    title_block_x_limit = w * 0.96
    drawing_segments = [s for s in merged_segments if max(s.x1, s.x2) <= title_block_x_limit]

    # Discard annotation linework (hatching, dimension strings, furniture,
    # door swings) before it reaches the wall mask. Without this the mask
    # is shredded by non-wall lines and the flood fill returns hundreds of
    # fragments instead of rooms — see line_extraction.filter_wall_candidates.
    wall_segments = filter_wall_candidates(drawing_segments, scale, (h, w), scale_is_calibrated, ink_mask(image))

    # --- Upstream Phase 1 & 2: Parallel Wall-Face Pairing & Centerline Reconstruction ---
    # Detect double-line parallel wall pairs (separation 3.0in - 14.0in, cavity ink <= 0.40)
    # and collapse them down to true physical wall centerlines carrying measured thickness.
    from app.geometry.double_line_walls import detect_double_line_walls
    wall_pairs = detect_double_line_walls(
        wall_segments,
        ink_mask(image),
        (h, w),
        scale_ft_per_px=scale,
        scale_is_calibrated=scale_is_calibrated,
    )
    door_gap_px = (3.5 / scale) if (scale and scale > 0) else (max(h, w) * 0.015)

    paired_seg_ids = set()
    for p in wall_pairs:
        if p.face_a:
            paired_seg_ids.add(p.face_a.id)
        if p.face_b:
            paired_seg_ids.add(p.face_b.id)

    paired_centerlines = [pair.centerline for pair in wall_pairs]
    unpaired_cands = [
        s for s in wall_segments
        if s.id not in paired_seg_ids and ((s.length * scale) if scale else s.length) >= 3.0
    ]

    bridged_paired = merge_collinear_segments(
        paired_centerlines,
        image_shape=(h, w),
        offset_cluster_px=8.0,
        max_gap_px_override=door_gap_px,
    )
    bridged_unpaired = merge_collinear_segments(
        unpaired_cands,
        image_shape=(h, w),
        offset_cluster_px=8.0,
        max_gap_px_override=door_gap_px,
    )
    vector_wall_segments = bridged_paired + bridged_unpaired
    if wall_pairs:
        wall_segments = bridged_paired

    # Rooms are flooded against the wall *bands* (thick strokes) rather than
    # the detected line segments. Line detection cannot tell a wall from a
    # sofa outline, and a sofa outline is a closed loop while a real room is
    # broken by doorways — so flooding line output finds furniture and misses
    # rooms. Stroke thickness separates the two directly. Drawings that don't
    # use a heavy/light lineweight convention return None here and fall back
    # to the segment-derived mask.
    # seal_openings stays False: room segmentation is a watershed that
    # divides at doorway necks, so it does not need openings bridged — and
    # bridging them actively merges adjoining rooms into one region, which
    # is exactly what sealing would cause here.
    # A PDF's own vector layers (when it has them — a genuine "Wall"/
    # "EX-WALL"/"Internal wall" layer from the original CAD export) are a
    # categorically better wall signal than reverse-engineering stroke
    # thickness from the raster: measured on a real professional CAD sheet
    # where the thickness heuristic below fails outright (its wall strokes
    # fragment into pieces averaging under the minimum wall-run length no
    # matter how the kernel is tuned), the wall layer alone produced a
    # clean building outline. Falls through to the raster approach when the
    # PDF has no such layer (a flattened export, a scan, an image upload).
    # Where printed text sits on this page, as boxes and as a mask. Used
    # both to keep text out of the raster wall band and to reject a
    # candidate "room" that is really a notes/legend/title block (see
    # room_detector.MAX_ROOM_TEXT_COVERAGE). The PDF's own word boxes are
    # free and always present for a vector PDF; OCR boxes are merged in
    # when the caller happened to run OCR, which is the only way a scanned
    # page contributes any.
    _combined_text_boxes = list(ocr_text_boxes_px or []) + list(word_boxes_px)
    text_mask: np.ndarray | None = None
    if _combined_text_boxes:
        text_mask = np.zeros((h, w), dtype=np.uint8)
        for _tx0, _ty0, _tx1, _ty1 in _combined_text_boxes:
            cv2.rectangle(
                text_mask,
                (max(0, int(_tx0)), max(0, int(_ty0))),
                (min(w, int(_tx1)), min(h, int(_ty1))),
                255,
                thickness=cv2.FILLED,
            )

    wall_band = None
    # A mask built from the PDF's own named wall layers is authoritative:
    # the drafter declared those strokes to be walls, so the downstream
    # "is this really a wall run or sheet decoration?" guesswork must not
    # second-guess it (see building_envelope_mask's `walls_are_authoritative`).
    walls_are_authoritative = False
    if pdf_path and page_number:
        wall_band = extract_wall_mask_from_layers(pdf_path, page_number, (h, w))
        if wall_band is not None:
            walls_are_authoritative = True
            # Seal door and window openings in the vector wall mask.
            # CAD vector wall layers have open gaps at every door/window frame.
            # Running horizontal/vertical morphological closing seals these gaps
            # so the rooms don't leak, without distorting the clean CAD linework.
            seal_px = min(180, max(3, int(round(max(h, w) * 0.025))))
            horizontal = cv2.morphologyEx(wall_band, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (seal_px, 1)))
            vertical = cv2.morphologyEx(wall_band, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (1, seal_px)))
            wall_band = cv2.bitwise_or(horizontal, vertical)
    if wall_band is None:
        # The PDF's own word boxes are a free, always-available text map for
        # any vector PDF — no OCR pass required. Previously only
        # `ocr_text_boxes_px` reached the wall band, which is None whenever
        # the caller didn't run OCR first, so on those pages the borders of
        # notes/legend/title blocks stayed in the mask and were flooded as
        # rooms. Measured on a real finish-plan sheet: the GENERAL NOTES
        # block became the single highest-confidence "room" on the page
        # (828 sqft at 0.95) with 250 printed words inside its bounding box,
        # against 0-13 for every genuine room there. It is invisible to the
        # rectilinearity gate precisely because a notes block is a perfect
        # rectangle, so it has to be kept out of the mask rather than
        # scored down afterwards.
        wall_band = extract_wall_band_mask(
            image, seal_openings=False, text_boxes_px=_combined_text_boxes or None
        )
    # Independent wall evidence for scoring room candidates: the vector
    # wall layer, or failing that the raster stroke-thickness band. NOT the
    # Hough-segment fallback mask � a polygon carved out of that mask
    # trivially touches it, so scoring against it certifies whatever it
    # produced (see detect_room_polygons' wall_evidence_mask).
    wall_evidence_mask = wall_band
    segment_mask = build_wall_mask((h, w), wall_segments) if wall_segments else None
    if wall_band is not None and segment_mask is not None:
        wall_mask = cv2.bitwise_or(wall_band, segment_mask)
    elif wall_band is not None:
        wall_mask = wall_band
    else:
        wall_mask = segment_mask if segment_mask is not None else np.zeros((h, w), dtype=np.uint8)

    # Provenance for the final persisted Wall rows (see WallEvidence.source
    # / GeometryWall.source) — which extraction path actually produced the
    # mask wall geometry is re-derived from below. Updated at each fallback
    # tier that ends up succeeding; stays at its initial value when the
    # first-choice mask already produces rooms.
    if walls_are_authoritative:
        wall_mask_source = "vector_layer"
    elif wall_band is not None:
        wall_mask_source = "raster_band"
    else:
        wall_mask_source = "vector_raw" if vector_segments else "hough_raw"

    if classification.page_type.value == "site_plan":
        from app.geometry.room_detector import building_envelope_mask
        envelope = building_envelope_mask(wall_mask, walls_are_authoritative)
        if envelope is not None:
            wall_mask = cv2.bitwise_and(wall_mask, envelope)
            if wall_evidence_mask is not None:
                wall_evidence_mask = cv2.bitwise_and(wall_evidence_mask, envelope)

    if door_detections:
        from app.geometry.room_detector import seal_door_openings_in_wall_mask
        wall_mask, door_seal_metrics = seal_door_openings_in_wall_mask(wall_mask, door_detections)
        logger.info("Targeted Door Sealing: %s", door_seal_metrics)

    room_mask = wall_mask
    room_polygons_px = detect_room_polygons(
        room_mask,
        scale,
        scale_is_calibrated,
        ocr_room_label_centroids_px,
        walls_are_authoritative,
        ink_mask(image),
        text_mask=text_mask,
        wall_evidence_mask=wall_evidence_mask,
    )

    # If the wall-band mask exists but fails to produce rooms, retry using
    # the line-derived segment mask. This can recover cases where the thick
    # wall extraction is too aggressive or misses a noisy scan's actual wall
    # ink.
    if not room_polygons_px and wall_band is not None:
        fallback_mask = build_wall_mask((h, w), wall_segments)
        if classification.page_type.value == "site_plan":
            from app.geometry.room_detector import building_envelope_mask
            envelope = building_envelope_mask(fallback_mask, False)
            if envelope is not None:
                fallback_mask = cv2.bitwise_and(fallback_mask, envelope)
        room_polygons_px = detect_room_polygons(
            fallback_mask,
            scale,
            scale_is_calibrated,
            ocr_room_label_centroids_px,
            False,
            ink_mask(image),
            text_mask=text_mask,
            wall_evidence_mask=wall_evidence_mask,
        )
        if room_polygons_px:
            room_mask = fallback_mask
            wall_mask_source = "hough_segment_fallback"

    if not room_polygons_px and wall_band is not None:
        thicker_mask = build_wall_mask((h, w), wall_segments, thickness_px=max(3, wall_mask_thickness_px((h, w)) * 2))
        if classification.page_type.value == "site_plan":
            from app.geometry.room_detector import building_envelope_mask
            envelope = building_envelope_mask(thicker_mask, False)
            if envelope is not None:
                thicker_mask = cv2.bitwise_and(thicker_mask, envelope)
        room_polygons_px = detect_room_polygons(
            thicker_mask,
            scale,
            scale_is_calibrated,
            ocr_room_label_centroids_px,
            False,
            ink_mask(image),
            text_mask=text_mask,
            wall_evidence_mask=wall_evidence_mask,
        )
        if room_polygons_px:
            room_mask = thicker_mask
            wall_mask_source = "thicker_hough_fallback"

    # Final fallback: morphological wall extractor. When both the wall-band
    # and Hough-segment masks produce zero rooms, derive a wall mask directly
    # from the raw ink using long horizontal and vertical morphological opening
    # kernels (see cv.py analysis). Opening with a long kernel only preserves
    # strokes that run at least min_line pixels in that direction — this
    # eliminates text, furniture symbols, door arcs, and dimension ticks without
    # any line detection. The two passes are OR-ed to recover walls at any angle.
    # This is most effective on scanned/rasterized plans with thick filled walls
    # where Hough sees a solid rectangle rather than two parallel edges.
    if not room_polygons_px:
        raw_ink = ink_mask(image)
        long_edge = max(h, w)
        min_line = max(35, long_edge // 75)
        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (min_line, 1))
        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, min_line))
        morph_h = cv2.morphologyEx(raw_ink, cv2.MORPH_OPEN, h_kernel)
        morph_v = cv2.morphologyEx(raw_ink, cv2.MORPH_OPEN, v_kernel)
        morph_walls = cv2.bitwise_or(morph_h, morph_v)
        # Bridge small gaps so doorway openings don't leak between rooms.
        bridge_px = max(9, long_edge // 180)
        bridge_px = bridge_px if bridge_px % 2 else bridge_px + 1
        bridge_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (bridge_px, bridge_px))
        morph_walls = cv2.morphologyEx(morph_walls, cv2.MORPH_CLOSE, bridge_kernel)
        morph_walls = cv2.dilate(morph_walls, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)), iterations=1)
        morph_room_polygons = detect_room_polygons(
            morph_walls,
            scale,
            scale_is_calibrated,
            ocr_room_label_centroids_px,
            False,
            raw_ink,
            text_mask=text_mask,
            wall_evidence_mask=wall_evidence_mask,
        )
        if morph_room_polygons:
            room_polygons_px = morph_room_polygons
            room_mask = morph_walls
            wall_mask_source = "morph_ink_fallback"


    if vector_wall_segments:
        wall_segments = vector_wall_segments
        wall_face_segments = vector_wall_segments
    elif wall_band is not None:
        # Re-derive the *persisted* wall segments from the same mask that
        # room detection ultimately succeeded on, instead of the raw Hough-on-
        # grayscale segments. On a plan with dense interior linework
        # (cabinetry, tile, countertops) those pass the length/angle filter
        # just as easily as real walls do — extracting from the mask keeps
        # wall geometry and room geometry consistent by construction, since
        # both come from the same stroke-thickness-validated signal.
        #
        # The offset-cluster tolerance widens to the mask's own thickness so
        # a thick wall's two edges collapse into one centerline instead of
        # surviving as two parallel near-duplicate segments.
        mask_segments = extract_wall_segments_from_mask(room_mask)
        # Kept for thickness measurement: these still have a wall's two
        # faces as separate lines, which is what the gap between them is
        # measured from (see metrics.measure_wall_thickness_from_faces).
        # The merge below is what collapses each pair into one centerline.
        wall_face_segments = mask_segments
        offset_tolerance = float(wall_mask_thickness_px((h, w))) * 1.5
        merged_mask_segments = merge_collinear_segments(mask_segments, (h, w), offset_cluster_px=offset_tolerance)
        drawing_mask_segments = [s for s in merged_mask_segments if max(s.x1, s.x2) <= title_block_x_limit]
        wall_segments = filter_wall_candidates(drawing_mask_segments, scale, (h, w), scale_is_calibrated)

    rooms: list[GeometryRoom] = []
    room_shapely_polys = []
    # The sheet's drawing area, as already determined by the page
    # classifier. Until now this was computed on every page and read by
    # nothing; a candidate lying outside it is documentation (title block,
    # revision table, key plan), not architecture.
    _zone = classification.drawing_zone_bbox

    def _in_drawing_zone(bbox_norm: dict) -> bool:
        # Majority-overlap rather than strict containment: a real room may
        # legitimately sit right against the drawing area's edge, while a
        # title-block box sits mostly or wholly beyond it.
        ox = max(0.0, min(bbox_norm["maxX"], _zone["maxX"]) - max(bbox_norm["minX"], _zone["minX"]))
        oy = max(0.0, min(bbox_norm["maxY"], _zone["maxY"]) - max(bbox_norm["minY"], _zone["minY"]))
        bw = max(1e-9, bbox_norm["maxX"] - bbox_norm["minX"])
        bh = max(1e-9, bbox_norm["maxY"] - bbox_norm["minY"])
        return (ox * oy) / (bw * bh) >= MIN_DRAWING_ZONE_OVERLAP

    page_text_items: list[tuple[float, float, float, float, str]] = []
    if pdf_path and page_number:
        page_text_items = extract_page_text_items_norm(pdf_path, page_number)

    for i, candidate in enumerate(room_polygons_px):
        poly_px = candidate.points
        metrics = polygon_metrics([tuple(p) for p in poly_px], scale, w, h)
        room_shapely_polys.append(metrics["shapely_polygon"])
        r_wall_contact = contour_raster_wall_contact(metrics["shapely_polygon"], wall_segments)
        room_decision = evaluate_room_candidate(
            RoomEvidence(
                area_sqft=metrics["area_sqft"],
                num_vertices=len(metrics["polygon_norm"]),
                wall_verified=candidate.wall_verified,
                polygon_norm=metrics["polygon_norm"],
                wall_contact=candidate.wall_contact,
                in_drawing_zone=_in_drawing_zone(metrics["bbox_norm"]),
                raster_wall_contact=r_wall_contact,
            )
        )

        room_name = _extract_spatial_room_name(
            metrics["polygon_norm"], page_text_items, f"Room {i + 1}"
        )

        rooms.append(
            GeometryRoom(
                name=room_name,
                polygon_norm=metrics["polygon_norm"],
                bbox_norm=metrics["bbox_norm"],
                centroid_norm=metrics["centroid_norm"],
                area_sqft=metrics["area_sqft"],
                perimeter_ft=metrics["perimeter_ft"],
                confidence=room_decision.confidence,
                status=room_decision.status,
                rejection_reasons=room_decision.reasons,
                _shapely_index=i,
            )
        )

    # Covered exterior areas (porches/decks) are found against all linework
    # rather than the wall mask, because their boundary is a thin dashed
    # overhang line the wall mask correctly discards. They are appended as
    # rooms carrying EXTERIOR_AREA_ROOM_TYPE so they can be measured but
    # priced differently — no drywall, no painted wall surface.
    if wall_band is not None:
        exterior_polygons = detect_exterior_area_polygons(
            ink_mask(image), wall_band, scale, scale_is_calibrated, walls_are_authoritative
        )
        for j, poly_px in enumerate(exterior_polygons):
            metrics = polygon_metrics([tuple(p) for p in poly_px], scale, w, h)
            # A covered area's boundary is a real (if thin/dashed) drawn
            # overhang line, not an approximated cut — but it is genuinely
            # often non-rectilinear, so it is scored with the rectilinearity
            # gate and wall_contact deliberately not applied (see
            # room_validation.py's module docstring for why wall_contact=None
            # never rejects). Drawing-zone still applies — a covered area
            # caught in the title-block margin is documentation same as
            # anything else.
            exterior_decision = evaluate_room_candidate(
                RoomEvidence(
                    area_sqft=metrics["area_sqft"],
                    num_vertices=len(metrics["polygon_norm"]),
                    wall_verified=True,
                    polygon_norm=None,
                    wall_contact=None,
                    in_drawing_zone=_in_drawing_zone(metrics["bbox_norm"]),
                )
            )
            rooms.append(
                GeometryRoom(
                    name=f"Covered Area {j + 1}",
                    polygon_norm=metrics["polygon_norm"],
                    bbox_norm=metrics["bbox_norm"],
                    centroid_norm=metrics["centroid_norm"],
                    area_sqft=metrics["area_sqft"],
                    perimeter_ft=metrics["perimeter_ft"],
                    confidence=exterior_decision.confidence,
                    status=exterior_decision.status,
                    rejection_reasons=exterior_decision.reasons,
                    room_type=EXTERIOR_AREA_ROOM_TYPE,
                )
            )
            # Deliberately NOT added to room_shapely_polys: walls are linked
            # to enclosed rooms, and a covered area has no walls to link.

    # One composed context object — page type, drawing zone, scale, vector/
    # wall-layer availability, trade selection — for the wall-candidate
    # validation gate below. Everything it carries was already being
    # computed on this page (classification, scale_context); this is the
    # first point wall extraction actually receives it rather than only
    # room detection (see FORENSIC_AUDIT_REPORT.md §1-5 for what was
    # missing before this).
    page_context = PageContext.build(
        classification=classification,
        scale_context=scale_context,
        width_px=w,
        height_px=h,
        has_vector_data=bool(vector_segments),
        has_wall_layer=walls_are_authoritative,
        ocr_available=bool(_combined_text_boxes),
        selected_trade=selected_trade,
    )

    # Built once from every surviving segment so wall_confidence can tell a
    # segment that's part of a real wall chain/corner from an isolated line
    # the Hough transform happened to pick up (see wall_graph.segment_is_connected).
    # Uses the same filtered set the mask was built from, so the walls that
    # get persisted are the ones that actually bounded the detected rooms.
    graph = build_wall_graph(wall_segments)

    # The building footprint's own extent, not the page's — see
    # is_exterior_segment's docstring for why classifying "near the page
    # edge" against raw image_w/image_h silently zeroed out every exterior
    # wall on any real sheet with margin (title block, dimension strings)
    # around the plan.
    envelope_bbox = wall_segments_bbox(wall_segments)

    # A real wall, even a short stub, almost always meets another wall at a
    # corner or T-junction — that's what "wall graph connected" means. A
    # segment that is both short AND isolated (touches nothing else) and
    # isn't on the exterior edge is something else: verified against a real
    # plan, this is almost entirely room-name text underlines and fixture
    # symbol strokes (vent hood, tub, toilet) that happen to be thick enough
    # to survive stroke-thickness selection and long/axis-aligned enough to
    # pass filter_wall_candidates. Every text label on that plan produced
    # exactly one such segment.
    ISOLATED_WALL_MIN_LENGTH_FT = 3.0
    ISOLATED_WALL_MIN_LENGTH_PAGE_RATIO = 0.045
    isolated_min_length_px = (
        ISOLATED_WALL_MIN_LENGTH_FT / scale
        if scale_is_calibrated and scale > 0
        else max(h, w) * ISOLATED_WALL_MIN_LENGTH_PAGE_RATIO
    )

    # Half the local stroke width at every wall pixel — the signal wall
    # thickness is measured from (see metrics.measure_wall_thickness_ft).
    # Computed once for the page rather than per segment.
    wall_distance_px = cv2.distanceTransform((wall_mask > 0).astype(np.uint8), cv2.DIST_L2, 5)

    # On the vector-layer path the mask is drawn at a synthetic uniform
    # width, so its stroke width says nothing about real wall thickness —
    # measure the gap between the wall's two drawn faces instead. The
    # raster path's mask *is* the drawn wall band, so its own width is the
    # measurement there. See both functions' docstrings.
    measure_from_faces = walls_are_authoritative and wall_face_segments

    # Evidence-Based Physical Wall Entity Reconstruction (Track B Vector Provenance)
    reconstructed_entities = []
    if pdf_path and page_number:
        try:
            from app.geometry.wall_entity_reconstruction import extract_and_reconstruct_wall_entities
            reconstructed_entities = extract_and_reconstruct_wall_entities(pdf_path, page_number, (h, w), scale)
        except Exception as ent_exc:
            logger.warning("Wall entity reconstruction exception: %s", ent_exc)

    walls: list[GeometryWall] = []
    if reconstructed_entities:
        # Real connectivity for the validation gate below. Without this,
        # `connected` was previously hardcoded to True for every
        # reconstructed entity regardless of whether it actually touched
        # another wall — which silently disabled the
        # isolated_unlinked_interior_segment check in evaluate_wall_candidate
        # for this entire path.
        #
        # This deliberately does NOT reuse wall_graph.build_wall_graph's
        # NODE_SNAP_PX=4.0 pixel-grid quantization — that constant is tuned
        # for `wall_segments` below, whose coordinates never leave raster
        # pixel space. Reconstructed entities' coordinates round-trip
        # through PDF-point space and back (wall_entity_reconstruction.py
        # opens the PDF itself and normalizes against its own page
        # dimensions), which measurably adds enough jitter that two
        # endpoints 2-4px apart routinely land in different 4px grid cells
        # and never connect under grid quantization — confirmed on a real
        # partition-plan page, where every one of 189 reconstructed entities
        # came back "disconnected" under the grid-snap approach despite
        # several genuine corner pairs sitting 2-4px apart. A direct
        # physical-distance check avoids the grid-boundary edge case
        # entirely. 0.5 ft comfortably covers a real wall-to-wall corner
        # offset (roughly half a partition's thickness) while the measured
        # gap to the next-nearest, genuinely unrelated endpoint on that same
        # page was over 2 ft — there is real separation between "these two
        # entities meet at a corner" and "these two entities are unrelated",
        # this constant just needs to land inside it.
        CORNER_SNAP_FT = 0.5
        corner_snap_px = CORNER_SNAP_FT / scale if scale > 0 else 4.0

        entity_endpoints_px = [
            (
                (ent["start_norm"]["x"] * w, ent["start_norm"]["y"] * h),
                (ent["end_norm"]["x"] * w, ent["end_norm"]["y"] * h),
            )
            for ent in reconstructed_entities
        ]

        def _entity_is_connected(idx: int) -> bool:
            (sx, sy), (ex, ey) = entity_endpoints_px[idx]
            for other_idx, ((osx, osy), (oex, oey)) in enumerate(entity_endpoints_px):
                if other_idx == idx:
                    continue
                for ax, ay in ((sx, sy), (ex, ey)):
                    for bx, by in ((osx, osy), (oex, oey)):
                        if ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5 <= corner_snap_px:
                            return True
            return False

        for ent_idx, ent in enumerate(reconstructed_entities):
            sn = ent["start_norm"]
            en = ent["end_norm"]
            length_ft = ent["length_ft"]
            is_exterior = (ent["wall_type"] == "exterior")
            bbox_norm = segment_bbox_norm(sn["x"], sn["y"], en["x"], en["y"])

            # Check room link
            linked_room_index: int | None = None
            start_px = (sn["x"] * w, sn["y"] * h)
            end_px = (en["x"] * w, en["y"] * h)
            for idx, poly in enumerate(room_shapely_polys):
                if wall_touches_room(start_px, end_px, poly):
                    linked_room_index = idx
                    break

            connected = _entity_is_connected(ent_idx)

            # Compute angle from normalized coords for physics gate
            import math as _math
            _edx = en["x"] - sn["x"]
            _edy = en["y"] - sn["y"]
            _ent_angle = _math.degrees(_math.atan2(abs(_edy), abs(_edx))) if (_edx != 0 or _edy != 0) else 0.0
            _ent_thick_in = (ent.get("thickness_ft") or 0.0) * 12.0 or None
            _ent_face_pair = ent.get("face_b_segment_id") is not None

            evidence = WallEvidence(
                length_ft=length_ft,
                connected=connected,
                linked_room_index=linked_room_index,
                exterior=is_exterior,
                bbox_norm=bbox_norm,
                source=ent.get("source", "reconstructed_vector_entity"),
                angle_deg=_ent_angle,
                thickness_in=_ent_thick_in if _ent_thick_in else None,
                face_pair_detected=_ent_face_pair,
            )
            decision = evaluate_wall_candidate(evidence, page_context)
            
            # Validation gate wins on rejection; if the gate passes, use the
            # reconstruction's own status (APPROVED for dual-face, NEEDS_REVIEW
            # for unnamed-long-stroke, PENDING otherwise). The previous code
            # had this inverted: it only used ent["status"] when the gate
            # returned APPROVED, which it never does, so reconstruction APPROVED
            # was always silently overridden to PENDING. (D4 defect)
            if decision.status == ReviewStatus.REJECTED:
                final_status = ReviewStatus.REJECTED
            else:
                final_status = ent.get("status", ReviewStatus.PENDING)
            final_reasons = list(set(list(decision.reasons) + list(ent.get("rejection_reasons", []))))

            walls.append(
                GeometryWall(
                    start_norm=sn,
                    end_norm=en,
                    length_ft=length_ft,
                    wall_type=ent["wall_type"],
                    room_index=linked_room_index,
                    confidence=min(ent.get("confidence", 0.95), decision.confidence),
                    thickness_ft=ent["thickness_ft"],
                    thickness_measured=ent["thickness_measured"],
                    wall_type_code=ent.get("wall_type_code"),
                    status=final_status,
                    rejection_reasons=final_reasons,
                    source=ent.get("source", "reconstructed_vector_entity"),
                    face_a_segment_id=ent.get("face_a_segment_id") or ent.get("id"),
                    face_b_segment_id=ent.get("face_b_segment_id"),
                    face_a_coords=ent.get("face_a_coords"),
                    face_b_coords=ent.get("face_b_coords"),
                )
            )
    else:
        for seg in wall_segments:
            start_px, end_px = (seg.x1, seg.y1), (seg.x2, seg.y2)
            length_ft = wall_length_ft(start_px, end_px, scale)
            if length_ft < 1.0:  # sub-foot fragments are noise, not real walls
                continue

            exterior, orientation_reasons = classify_wall_orientation(
                seg, w, h, room_shapely_polys, wall_distance_px, envelope_bbox=envelope_bbox
            )
            connected = segment_is_connected(graph, seg)
            if not connected and not exterior and seg.length < isolated_min_length_px:
                continue

            linked_room_index: int | None = None
            for idx, poly in enumerate(room_shapely_polys):
                if wall_touches_room(start_px, end_px, poly):
                    linked_room_index = idx
                    break

            if getattr(seg, "thickness_in", None) is not None:
                measured_thickness = seg.thickness_in / 12.0
            elif measure_from_faces:
                measured_thickness = measure_wall_thickness_from_faces(seg, wall_face_segments, scale)
            else:
                measured_thickness = measure_wall_thickness_ft(start_px, end_px, wall_distance_px, scale)

            bbox_norm = segment_bbox_norm(seg.x1 / w, seg.y1 / h, seg.x2 / w, seg.y2 / h)

            # Physics evidence for D-003 constraint gates
            import math as _math
            _dx, _dy = seg.x2 - seg.x1, seg.y2 - seg.y1
            _seg_angle_deg = _math.degrees(_math.atan2(abs(_dy), abs(_dx))) if (_dx != 0 or _dy != 0) else 0.0
            _thickness_in = getattr(seg, "thickness_in", None)
            _face_pair = getattr(seg, "face_b_id", None) is not None
            # D-010: propagate thickness_consistent from WallPair detection
            _thickness_ok = getattr(seg, "thickness_consistent", True)

            evidence = WallEvidence(
                length_ft=length_ft,
                connected=connected,
                linked_room_index=linked_room_index,
                exterior=exterior,
                bbox_norm=bbox_norm,
                source=wall_mask_source,
                angle_deg=_seg_angle_deg,
                thickness_in=_thickness_in,
                face_pair_detected=_face_pair,
                thickness_consistent=_thickness_ok,
            )
            decision = evaluate_wall_candidate(evidence, page_context)
            logger.debug(
                "WallCandidate source=%s page_type=%s zone_overlap=%.2f scale=%s trade=%s "
                "length_ft=%.2f connected=%s linked_room=%s exterior=%s orientation_reasons=%s "
                "confidence=%.2f status=%s reasons=%s",
                evidence.source,
                page_context.page_type,
                decision.zone_overlap,
                "CALIBRATED" if page_context.scale_is_calibrated else "ASSUMED",
                page_context.selected_trade,
                length_ft,
                connected,
                linked_room_index,
                exterior,
                orientation_reasons,
                decision.confidence,
                decision.status.value,
                decision.reasons,
            )

            fa_id = getattr(seg, "face_a_id", None)
            fb_id = getattr(seg, "face_b_id", None)
            fa_seg = getattr(seg, "face_a", None)
            fb_seg = getattr(seg, "face_b", None)
            fa_coords = (
                {"x1": round(fa_seg.x1 / w, 5), "y1": round(fa_seg.y1 / h, 5), "x2": round(fa_seg.x2 / w, 5), "y2": round(fa_seg.y2 / h, 5)}
                if fa_seg is not None
                else None
            )
            fb_coords = (
                {"x1": round(fb_seg.x1 / w, 5), "y1": round(fb_seg.y1 / h, 5), "x2": round(fb_seg.x2 / w, 5), "y2": round(fb_seg.y2 / h, 5)}
                if fb_seg is not None
                else None
            )
            overlap_r = getattr(seg, "overlap_ratio", None)

            if fb_id is None and not walls_are_authoritative:
                from app.geometry.single_face_promotion import SingleFaceContextEvidence, evaluate_single_face_promotion
                sf_ev = SingleFaceContextEvidence(
                    has_room_boundary=(linked_room_index is not None),
                    room_ids=[linked_room_index] if linked_room_index is not None else [],
                    is_exterior_envelope=exterior,
                    is_connected_at_corners=connected,
                    length_ft=length_ft,
                )
                promotion = evaluate_single_face_promotion(sf_ev)
                if promotion.is_promoted and decision.status != ReviewStatus.REJECTED:
                    wall_status = ReviewStatus.APPROVED
                    rejection_reasons = list(decision.reasons) + [promotion.diagnostic_reason]
                    single_face_conf = max(decision.confidence, promotion.recommended_confidence)
                else:
                    wall_status = ReviewStatus.NEEDS_REVIEW
                    rejection_reasons = list(decision.reasons) + ["unsupported_face_b_geometry"]
                    single_face_conf = min(0.50, decision.confidence)
            else:
                wall_status = decision.status
                rejection_reasons = decision.reasons
                single_face_conf = decision.confidence

            walls.append(
                GeometryWall(
                    start_norm={"x": round(seg.x1 / w, 5), "y": round(seg.y1 / h, 5)},
                    end_norm={"x": round(seg.x2 / w, 5), "y": round(seg.y2 / h, 5)},
                    length_ft=length_ft,
                    wall_type="exterior" if exterior else "interior",
                    room_index=linked_room_index,
                    confidence=single_face_conf if fb_id is not None or walls_are_authoritative else single_face_conf,
                    thickness_ft=measured_thickness,
                    thickness_measured=measured_thickness is not None,
                    status=wall_status,
                    rejection_reasons=rejection_reasons,
                    source=evidence.source,
                    face_a_segment_id=fa_id if fa_id is not None else getattr(seg, "id", None),
                    face_b_segment_id=fb_id,
                    face_a_coords=fa_coords,
                    face_b_coords=fb_coords,
                    overlap_ratio=overlap_r,
                )
            )

    # D3 FIX + D-001 CONFLICT RESOLUTION:
    # When reconstructed_entities is non-empty, raster wall_segments that were
    # NOT covered by any reconstruction are processed as D3-FALLBACK candidates.
    # "Covered" = meaningful geometric overlap, not just midpoint proximity.
    # Two segments overlap when their normalized length that lies within
    # FALLBACK_COVER_NORM of the other's line exceeds FALLBACK_OVERLAP_RATIO
    # of the shorter segment's length.  This replaces the old midpoint-only
    # check that suppressed real parallel walls whose midpoints were close to
    # (but not part of) a reconstruction entity.
    if reconstructed_entities and wall_segments:
        FALLBACK_COVER_NORM = 0.025    # perpendicular distance threshold (norm)
        FALLBACK_OVERLAP_RATIO = 0.60  # min fraction of segment that must overlap

        def _seg_norm(seg):
            return seg.x1 / w, seg.y1 / h, seg.x2 / w, seg.y2 / h

        def _point_to_seg_dist_norm(px, py, x1, y1, x2, y2) -> float:
            dx, dy = x2 - x1, y2 - y1
            sq = dx * dx + dy * dy
            if sq < 1e-10:
                return ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
            t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / sq))
            return ((px - x1 - t * dx) ** 2 + (py - y1 - t * dy) ** 2) ** 0.5

        def _geometric_overlap_ratio(sx1, sy1, sx2, sy2, rx1, ry1, rx2, ry2) -> float:
            """Fraction of the test segment (s*) that lies within FALLBACK_COVER_NORM
            of the reference entity line (r*).  Sampled at 10 points along s*."""
            samples = 10
            close = sum(
                1 for i in range(samples + 1)
                if _point_to_seg_dist_norm(
                    sx1 + (sx2 - sx1) * i / samples,
                    sy1 + (sy2 - sy1) * i / samples,
                    rx1, ry1, rx2, ry2,
                ) < FALLBACK_COVER_NORM
            )
            return close / (samples + 1)

        recon_lines = [
            (ent["start_norm"]["x"], ent["start_norm"]["y"],
             ent["end_norm"]["x"], ent["end_norm"]["y"])
            for ent in reconstructed_entities
        ]

        fallback_count = 0
        for seg in wall_segments:
            sx1, sy1, sx2, sy2 = _seg_norm(seg)
            # A segment is "covered" when it substantially overlaps a reconstruction
            # entity — not just when its midpoint happens to be nearby.
            covered = any(
                _geometric_overlap_ratio(sx1, sy1, sx2, sy2, rx1, ry1, rx2, ry2) >= FALLBACK_OVERLAP_RATIO
                for rx1, ry1, rx2, ry2 in recon_lines
            )
            if covered:
                continue

            length_ft = wall_length_ft((seg.x1, seg.y1), (seg.x2, seg.y2), scale)
            if length_ft < 1.0:
                continue

            exterior, _ = classify_wall_orientation(
                seg, w, h, room_shapely_polys, wall_distance_px, envelope_bbox=envelope_bbox
            )
            connected = segment_is_connected(graph, seg)
            if not connected and not exterior and seg.length < isolated_min_length_px:
                continue

            linked_room_index = None
            for idx, poly in enumerate(room_shapely_polys):
                if wall_touches_room((seg.x1, seg.y1), (seg.x2, seg.y2), poly):
                    linked_room_index = idx
                    break

            bbox_norm = segment_bbox_norm(seg.x1 / w, seg.y1 / h, seg.x2 / w, seg.y2 / h)

            import math as _math
            _fb_dx, _fb_dy = seg.x2 - seg.x1, seg.y2 - seg.y1
            _fb_angle = _math.degrees(_math.atan2(abs(_fb_dy), abs(_fb_dx))) if (_fb_dx or _fb_dy) else 0.0

            evidence = WallEvidence(
                length_ft=length_ft,
                connected=connected,
                linked_room_index=linked_room_index,
                exterior=exterior,
                bbox_norm=bbox_norm,
                source="raster_fallback_uncovered_by_reconstruction",
                angle_deg=_fb_angle,
                thickness_in=None,
                face_pair_detected=False,
            )
            decision = evaluate_wall_candidate(evidence, page_context)
            logger.debug("D3-FALLBACK wall_segment not covered by reconstruction: len=%.2f status=%s", length_ft, decision.status.value)
            fallback_count += 1

            walls.append(
                GeometryWall(
                    start_norm={"x": round(seg.x1 / w, 5), "y": round(seg.y1 / h, 5)},
                    end_norm={"x": round(seg.x2 / w, 5), "y": round(seg.y2 / h, 5)},
                    length_ft=length_ft,
                    wall_type="exterior" if exterior else "interior",
                    room_index=linked_room_index,
                    confidence=min(0.60, decision.confidence),
                    thickness_ft=None,
                    thickness_measured=False,
                    status=ReviewStatus.NEEDS_REVIEW,
                    rejection_reasons=list(decision.reasons) + ["raster_fallback_reconstruction_miss"],
                    source="raster_fallback_uncovered_by_reconstruction",
                    face_a_segment_id=getattr(seg, "id", None),
                    face_b_segment_id=None,
                    face_a_coords=None,
                    face_b_coords=None,
                )
            )
        if fallback_count:
            logger.info("D3-FALLBACK: %d wall_segments added that reconstruction did not cover", fallback_count)

    windows: list[GeometryWindow] = []
    doors: list[GeometryDoor] = []
    stairs: list[GeometryStairs] = []
    if pdf_path and page_number:
        window_polygons_px = extract_window_polygons_from_layers(pdf_path, page_number, (h, w))
        for poly_px in window_polygons_px or []:
            xs = [p[0] / w for p in poly_px]
            ys = [p[1] / h for p in poly_px]
            windows.append(
                GeometryWindow(
                    polygon_norm=[[round(x, 5), round(y, 5)] for x, y in zip(xs, ys)],
                    bbox_norm={"minX": min(xs), "minY": min(ys), "maxX": max(xs), "maxY": max(ys)},
                )
            )

        from app.geometry.vector_doors import extract_door_polygons_from_layers
        door_polygons_px = extract_door_polygons_from_layers(pdf_path, page_number, (h, w))
        for poly_px in door_polygons_px or []:
            xs = [p[0] / w for p in poly_px]
            ys = [p[1] / h for p in poly_px]
            doors.append(
                GeometryDoor(
                    polygon_norm=[[round(x, 5), round(y, 5)] for x, y in zip(xs, ys)],
                    bbox_norm={"minX": min(xs), "minY": min(ys), "maxX": max(xs), "maxY": max(ys)},
                )
            )

        from app.geometry.vector_stairs import extract_stairs_polygons_from_layers
        stair_polygons_px = extract_stairs_polygons_from_layers(pdf_path, page_number, (h, w))
        for poly_px in stair_polygons_px or []:
            xs = [p[0] / w for p in poly_px]
            ys = [p[1] / h for p in poly_px]
            stairs.append(
                GeometryStairs(
                    polygon_norm=[[round(x, 5), round(y, 5)] for x, y in zip(xs, ys)],
                    bbox_norm={"minX": min(xs), "minY": min(ys), "maxX": max(xs), "maxY": max(ys)},
                )
            )

    # D-004: Comprehensive Bidirectional Room <-> Wall Context Verification
    # Every room boundary edge must correspond to a wall, and every wall must agree
    # that the room is attached to its reciprocal face. Disagreements and unverified
    # phantom candidates are flagged as NEEDS_REVIEW.
    from app.geometry.room_graph import RoomGraph
    _spatial_room_graph = RoomGraph(rooms)
    _proof_report = _spatial_room_graph.attach_and_verify_walls(walls)

    # 1. Update walls with bidirectional attachment details
    for _wi, _w in enumerate(walls):
        _att = _spatial_room_graph.wall_attachments.get(_wi)
        if _att:
            _w.side_a_room_index = _att.side_a_room_id if isinstance(_att.side_a_room_id, int) else None
            _w.side_a_direction = _att.side_a_direction
            _w.side_b_room_index = _att.side_b_room_id if isinstance(_att.side_b_room_id, int) else None
            _w.side_b_direction = _att.side_b_direction
            _w.bidirectional_verified = _att.side_a_verified or _att.side_b_verified

    # 2. Check for mismatched pairs and flag NEEDS_REVIEW on walls
    _mismatched_wall_ids = {m["wall_id"] for m in _proof_report.mismatched_pairs}
    _mismatched_room_ids = {m["room_id"] for m in _proof_report.mismatched_pairs}

    for _wi, _w in enumerate(walls):
        if _wi in _mismatched_wall_ids:
            if _w.status != ReviewStatus.REJECTED:
                _w.status = ReviewStatus.NEEDS_REVIEW
            if "bidirectional_room_wall_mismatch" not in _w.rejection_reasons:
                _w.rejection_reasons = list(_w.rejection_reasons) + ["bidirectional_room_wall_mismatch"]
        elif _w.bidirectional_verified and _w.status == ReviewStatus.NEEDS_REVIEW:
            if "unsupported_face_b_geometry" in _w.rejection_reasons:
                _w.status = ReviewStatus.APPROVED
                _w.rejection_reasons = [r for r in _w.rejection_reasons if r != "unsupported_face_b_geometry"]
                _w.rejection_reasons.append("single_face_promoted_by_context:bidirectional_room_boundary_verified")
                _w.confidence = max(_w.confidence, 0.85)

    # 3. Check rooms: each enclosed room must have verified bounding walls and no unresolved mismatch
    for _ri, _room in enumerate(rooms):
        if getattr(_room, "room_type", None) == EXTERIOR_AREA_ROOM_TYPE:
            continue

        _boundaries = _spatial_room_graph.room_boundaries.get(_ri, [])
        _room.boundary_edges = [
            {
                "edge_index": b.edge_index,
                "start": b.start,
                "end": b.end,
                "direction": b.direction,
                "matched_wall_id": b.matched_wall_id,
                "matched_wall_side": b.matched_wall_side,
                "verified": b.verified,
                "verification_reason": b.verification_reason,
            }
            for b in _boundaries
        ]

        _verified_boundaries = [b for b in _boundaries if b.verified]
        _room.bidirectional_verified = len(_verified_boundaries) > 0 and (_ri not in _mismatched_room_ids)

        if _ri in _mismatched_room_ids:
            if _room.status == ReviewStatus.PENDING:
                _room.status = ReviewStatus.NEEDS_REVIEW
            if "boundary_wall_bidirectional_mismatch" not in _room.rejection_reasons:
                _room.rejection_reasons = list(_room.rejection_reasons) + ["boundary_wall_bidirectional_mismatch"]
        elif len(_verified_boundaries) == 0:
            if _room.status == ReviewStatus.PENDING:
                _room.status = ReviewStatus.NEEDS_REVIEW
            if "no_accepted_wall_on_boundary" not in _room.rejection_reasons:
                _room.rejection_reasons = list(_room.rejection_reasons) + ["no_accepted_wall_on_boundary"]

    approved_walls_count = sum(1 for wall in walls if wall.status == ReviewStatus.APPROVED)
    rejected_walls_count = sum(1 for wall in walls if wall.status == ReviewStatus.REJECTED)
    drywall_scope_confirmed_count = sum(1 for wall in walls if wall.status != ReviewStatus.REJECTED)
    qto_walls_count = approved_walls_count

    # Run Architectural Physics & Multi-Constraint Validation
    from app.geometry.physics_engine import ArchitecturalPhysicsEngine
    _physics_engine = ArchitecturalPhysicsEngine()
    _physics_report = _physics_engine.validate_physics_constraints(
        walls=walls,
        rooms=rooms,
        scale_ft_per_px=scale or 0.05,
        dpi=getattr(scale_context, "dpi", 150.0) or 150.0,
    )

    logger.info(
        "PAGE STAGE LOG [page=%s type=%s eligible=True]: "
        "total_vector_items=%d, filtered_vector_items=%d, drawing_region_items=%d, "
        "candidate_segments=%d, wall_pairs=%d, approved_walls=%d, rejected_walls=%d, "
        "drywall_scope_confirmed=%d, qto_walls=%d, physics_score=%.2f, junctions=%d",
        page_number,
        classification.page_type.value,
        len(raw_segments),
        len(merged_segments),
        len(drawing_segments),
        len(wall_segments),
        len(wall_pairs) if 'wall_pairs' in locals() and wall_pairs else 0,
        approved_walls_count,
        rejected_walls_count,
        drywall_scope_confirmed_count,
        qto_walls_count,
        _physics_report.overall_physics_score,
        len(_physics_report.junctions),
    )

    return GeometryResult(
        rooms=rooms,
        walls=walls,
        wall_segment_count_raw=len(raw_segments),
        wall_segment_count_merged=len(merged_segments),
        page_type=classification.page_type.value,
        is_takeoff_eligible=True,
        skip_reason=None,
        windows=windows,
        doors=doors,
        stairs=stairs,
        discipline=classification.discipline,
        primary_title=classification.primary_title,
        classification_confidence=classification.confidence,
        geometry_authority=classification.geometry_authority,
        physics_report=_physics_report,
    )
