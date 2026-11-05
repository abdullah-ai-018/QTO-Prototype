"""AI validation orchestration: run YOLOv11 + SAM2 over a page, compare
their output against the deterministic geometry engine's rooms, and
produce a list of pending `Detection` rows plus confidence adjustments.

Hard rule enforced throughout this module: AI never writes area,
perimeter, or quantity values. It only proposes labels, flags
disagreements, and assigns confidence scores for a human (or the
approval workflow) to act on.
"""

from dataclasses import dataclass

from shapely.geometry import Polygon

from app.ai.sam_segmenter import SamMask, segment_at_points
from app.ai.yolo_detector import YoloDetection, detect_objects
from app.geometry.engine import GeometryResult
from app.models.enums import DetectionKind, DetectionSource

# SAM2 is a full segmentation-model inference per room, and easily the
# single most expensive step in the AI validation pass — on a real 14-page
# set this was a major contributor to ~3 minutes/page. Cross-checking every
# room on a dense commercial floor plan (30-50+ rooms) doesn't add much
# beyond the point where a handful of samples has already confirmed the
# geometry engine's boundary quality; capping this trades a little of that
# blanket coverage for a real, direct reduction in per-page time.
MAX_SAM_PROMPTS_PER_PAGE = 6
IOU_AGREEMENT_THRESHOLD = 0.45

# Every class from every configured YOLO checkpoint (see
# yolo_detector.py's module docstring for which models those are),
# explicitly mapped — no silent fallback to a generic kind for a class we
# know about. `area`/`internal-walls`/`external-walls`/`footprint` map onto
# ROOM/WALL for completeness, but the frontend deliberately excludes those
# from what it renders: they describe the same physical geometry already
# computed and persisted by the deterministic engine (see
# backendConversion.isSymbolDetection), so drawing them again would double
# up on every room/wall on the sheet.
_YOLO_CLASS_KIND = {
    "door": DetectionKind.DOOR,
    "cav-sliders": DetectionKind.DOOR,
    "windows": DetectionKind.WINDOW,
    "internal-walls": DetectionKind.WALL,
    "external-walls": DetectionKind.WALL,
    "footprint": DetectionKind.WALL,
    "area": DetectionKind.ROOM,
    "bathtub": DetectionKind.FIXTURE,
    "shower": DetectionKind.FIXTURE,
    "sinks": DetectionKind.FIXTURE,
    "vanity": DetectionKind.FIXTURE,
    "toilet": DetectionKind.FIXTURE,
    "robes": DetectionKind.FIXTURE,
    "stairs": DetectionKind.STAIRS,
    "scale": DetectionKind.ANNOTATION,
    "title-block": DetectionKind.ANNOTATION,
    "dimensions": DetectionKind.ANNOTATION,
    # Roboflow Bedroom-Washroom-Hall-Office dataset classes (best_roomtype.pt)
    "bedroom-washroom-hall-office": DetectionKind.ROOM,
    "study": DetectionKind.ROOM,
    "dining": DetectionKind.ROOM,
    "office": DetectionKind.ROOM,
    "dressing room": DetectionKind.ROOM,
    "closet": DetectionKind.ROOM,
    "foyer": DetectionKind.ROOM,
    "kitchen": DetectionKind.ROOM,
    "washroom": DetectionKind.ROOM,
    "bedroom": DetectionKind.ROOM,
    "living": DetectionKind.ROOM,
    "hall": DetectionKind.ROOM,
    # best_furniture.pt (12-class furniture/fixture model). "sink"
    # (singular) is this model's own name for the same fixture the
    # original 17-class model calls "sinks" (plural) — both map to
    # FIXTURE, so approving either produces the same kind of Detection.
    # "achair"/"ctable"/"dtable" are this model's shorthand for armchair /
    # coffee table / dining table; "ssink"/"ssofa" are its shorthand for a
    # secondary sink/sofa (e.g. a bar sink, a loveseat) — same kind as
    # their base counterpart.
    "sink": DetectionKind.FIXTURE,
    "ssink": DetectionKind.FIXTURE,
    "achair": DetectionKind.OBJECT,
    "bed": DetectionKind.OBJECT,
    "chair": DetectionKind.OBJECT,
    "ctable": DetectionKind.OBJECT,
    "dtable": DetectionKind.OBJECT,
    "sofa": DetectionKind.OBJECT,
    "ssofa": DetectionKind.OBJECT,
    # best_cabinet.pt (17-class furniture/fixture model, "cabinet" role).
    # Its own class names, distinct from best_furniture.pt's shorthand
    # above ("armchair" not "achair", "small_sink"/"twin_sink" not "ssink").
    # "window" (singular) is this model's own name — distinct from the
    # primary/furniture models' "windows" (plural) — and gets excluded the
    # same way when a PDF's own WINDOW vector layer already found every
    # window on the page (see blueprint_service.py).
    "armchair": DetectionKind.OBJECT,
    "coffee_table": DetectionKind.OBJECT,
    "dining_table": DetectionKind.OBJECT,
    "round_table": DetectionKind.OBJECT,
    "large_sofa": DetectionKind.OBJECT,
    "small_sofa": DetectionKind.OBJECT,
    "small_sink": DetectionKind.FIXTURE,
    "twin_sink": DetectionKind.FIXTURE,
    "tub": DetectionKind.FIXTURE,
    "kitchen_bar": DetectionKind.FIXTURE,
    "window": DetectionKind.WINDOW,
    # best_new.pt (158-class room-name/furniture/wall model). The huge
    # majority of its vocabulary is genuine room/space names (ATRIUM,
    # GARAGE, GREAT ROOM, ...) — those all map to ROOM. A handful are
    # equipment, furniture, or decorative items that happen to share this
    # model's training set rather than a real enclosed space (a bench, a
    # duct run, a plant shelf) -> OBJECT; a few describe what's drawn
    # above/below rather than a physical thing on this sheet -> ANNOTATION.
    # "wall" is this model's own name for a wall run (distinct from the
    # primary model's "internal-walls"/"external-walls").
    "wall": DetectionKind.WALL,
    "ceiling below": DetectionKind.ANNOTATION,
    "open to below": DetectionKind.ANNOTATION,
    "space below": DetectionKind.ANNOTATION,
    "air condition": DetectionKind.OBJECT,
    "bbq": DetectionKind.OBJECT,
    "bench": DetectionKind.OBJECT,
    "bench hooks": DetectionKind.OBJECT,
    "books shelf": DetectionKind.OBJECT,
    "broom": DetectionKind.OBJECT,
    "coats": DetectionKind.OBJECT,
    "cofee": DetectionKind.OBJECT,
    "coffee": DetectionKind.OBJECT,
    "computer": DetectionKind.OBJECT,
    "cupboard": DetectionKind.OBJECT,
    "desk": DetectionKind.OBJECT,
    "drop": DetectionKind.OBJECT,
    "ductwork": DetectionKind.OBJECT,
    "laun chulo": DetectionKind.OBJECT,
    "locker": DetectionKind.OBJECT,
    "mesh": DetectionKind.OBJECT,
    "plant shelf": DetectionKind.OBJECT,
    "ramp": DetectionKind.OBJECT,
    "seat": DetectionKind.OBJECT,
    "shelf": DetectionKind.OBJECT,
    "shelves": DetectionKind.OBJECT,
    "shoes": DetectionKind.OBJECT,
    "stacked": DetectionKind.OBJECT,
    "stain glass dome": DetectionKind.OBJECT,
    "trellis": DetectionKind.OBJECT,
    "wine": DetectionKind.OBJECT,
    "atrium": DetectionKind.ROOM,
    "attic": DetectionKind.ROOM,
    "balcony": DetectionKind.ROOM,
    "bar": DetectionKind.ROOM,
    "basement": DetectionKind.ROOM,
    "bath room": DetectionKind.ROOM,
    "billiard": DetectionKind.ROOM,
    "bonus room": DetectionKind.ROOM,
    "bunk room": DetectionKind.ROOM,
    "breakfast room": DetectionKind.ROOM,
    "breezway": DetectionKind.ROOM,
    "carport": DetectionKind.ROOM,
    "casita": DetectionKind.ROOM,
    "casito": DetectionKind.ROOM,
    "comp loft": DetectionKind.ROOM,
    "comp room": DetectionKind.ROOM,
    "corridor": DetectionKind.ROOM,
    "courtyard": DetectionKind.ROOM,
    "covered carport": DetectionKind.ROOM,
    "covered chilling": DetectionKind.ROOM,
    "covered deck": DetectionKind.ROOM,
    "covered force": DetectionKind.ROOM,
    "covered patio": DetectionKind.ROOM,
    "covered porch": DetectionKind.ROOM,
    "covered scenic": DetectionKind.ROOM,
    "covered storage": DetectionKind.ROOM,
    "covered walk": DetectionKind.ROOM,
    "covered wood deck": DetectionKind.ROOM,
    "craft room": DetectionKind.ROOM,
    "deck": DetectionKind.ROOM,
    "den": DetectionKind.ROOM,
    "dressing area": DetectionKind.ROOM,
    "drop zone": DetectionKind.ROOM,
    "eating area": DetectionKind.ROOM,
    "elevator": DetectionKind.ROOM,
    "entry": DetectionKind.ROOM,
    "expandable": DetectionKind.ROOM,
    "family room": DetectionKind.ROOM,
    "fitness": DetectionKind.ROOM,
    "flex room": DetectionKind.ROOM,
    "front porch": DetectionKind.ROOM,
    "future bath": DetectionKind.ROOM,
    "future closet": DetectionKind.ROOM,
    "gallery": DetectionKind.ROOM,
    "game room": DetectionKind.ROOM,
    "garage": DetectionKind.ROOM,
    "gathering room": DetectionKind.ROOM,
    "gazebo": DetectionKind.ROOM,
    "grand room": DetectionKind.ROOM,
    "great porch": DetectionKind.ROOM,
    "great room": DetectionKind.ROOM,
    "grilling force": DetectionKind.ROOM,
    "guest exercise room": DetectionKind.ROOM,
    "guest room": DetectionKind.ROOM,
    "hobby room": DetectionKind.ROOM,
    "home theater": DetectionKind.ROOM,
    "kids nook": DetectionKind.ROOM,
    "kids playroom": DetectionKind.ROOM,
    "lanai": DetectionKind.ROOM,
    "laundry": DetectionKind.ROOM,
    "library room": DetectionKind.ROOM,
    "linen": DetectionKind.ROOM,
    "living room": DetectionKind.ROOM,
    "lodge room": DetectionKind.ROOM,
    "loft": DetectionKind.ROOM,
    "mech": DetectionKind.ROOM,
    "mechanical": DetectionKind.ROOM,
    "media": DetectionKind.ROOM,
    "morning room": DetectionKind.ROOM,
    "mud room": DetectionKind.ROOM,
    "niche": DetectionKind.ROOM,
    "nook": DetectionKind.ROOM,
    "observatory": DetectionKind.ROOM,
    "open deck": DetectionKind.ROOM,
    "optional covered patio": DetectionKind.ROOM,
    "outdoor room": DetectionKind.ROOM,
    "pantry": DetectionKind.ROOM,
    "patio": DetectionKind.ROOM,
    "pet center": DetectionKind.ROOM,
    "pocket office": DetectionKind.ROOM,
    "pool": DetectionKind.ROOM,
    "porch": DetectionKind.ROOM,
    "rear deck": DetectionKind.ROOM,
    "rear porch": DetectionKind.ROOM,
    "recreation room": DetectionKind.ROOM,
    "roof area": DetectionKind.ROOM,
    "safe room": DetectionKind.ROOM,
    "scenic mezzanine": DetectionKind.ROOM,
    "screen deck": DetectionKind.ROOM,
    "seasonal room": DetectionKind.ROOM,
    "shop": DetectionKind.ROOM,
    "sitting area": DetectionKind.ROOM,
    "snack area": DetectionKind.ROOM,
    "social room": DetectionKind.ROOM,
    "stoop": DetectionKind.ROOM,
    "storage": DetectionKind.ROOM,
    "store": DetectionKind.ROOM,
    "storm shelter": DetectionKind.ROOM,
    "story rv bay": DetectionKind.ROOM,
    "study loft": DetectionKind.ROOM,
    "sun room": DetectionKind.ROOM,
    "sundeck": DetectionKind.ROOM,
    "supply room": DetectionKind.ROOM,
    "screened porch": DetectionKind.ROOM,
    "tech center": DetectionKind.ROOM,
    "terrace": DetectionKind.ROOM,
    "tv room": DetectionKind.ROOM,
    "unfinished storage": DetectionKind.ROOM,
    "utility": DetectionKind.ROOM,
    "veranda": DetectionKind.ROOM,
    "vestibule": DetectionKind.ROOM,
    "wet bar": DetectionKind.ROOM,
    "wine bar": DetectionKind.ROOM,
    "wine cellar": DetectionKind.ROOM,
    "wine celler": DetectionKind.ROOM,
    "woodworking room": DetectionKind.ROOM,
    "workshop area": DetectionKind.ROOM,
    "optional future expansion": DetectionKind.ROOM,
}


@dataclass
class ValidationFinding:
    kind: DetectionKind
    label: str
    confidence: float
    polygon_px: list[tuple[float, float]]
    source: DetectionSource
    note: str | None = None
    # Which YOLO checkpoint produced this (yolo_detector.YoloDetection.model_role),
    # None for a FUSION finding (cross_check_rooms, not model output).
    model_role: str | None = None


def _polygon_iou(a: Polygon, b: Polygon) -> float:
    if not a.is_valid or not b.is_valid or a.is_empty or b.is_empty:
        return 0.0
    intersection = a.intersection(b).area
    union = a.union(b).area
    return intersection / union if union > 0 else 0.0


def cross_check_rooms(geometry: GeometryResult, image_w: int, image_h: int, image_path: str) -> list[ValidationFinding]:
    """For up to MAX_SAM_PROMPTS_PER_PAGE geometry rooms, run SAM2 at the
    room's centroid and compare the resulting mask polygon against the
    geometry room polygon via IoU. Rooms with poor AI agreement are
    surfaced as review-worthy findings rather than being trusted blindly.
    """
    rooms = geometry.rooms[:MAX_SAM_PROMPTS_PER_PAGE]
    if not rooms:
        return []

    centroids_px = [(r.centroid_norm["x"] * image_w, r.centroid_norm["y"] * image_h) for r in rooms]
    sam_masks: list[SamMask] = segment_at_points(image_path, centroids_px)

    findings: list[ValidationFinding] = []
    for room in rooms:
        room_poly_px = Polygon([(p[0] * image_w, p[1] * image_h) for p in room.polygon_norm])

        best_iou = 0.0
        for mask in sam_masks:
            mask_poly = Polygon(mask.polygon_px)
            if not mask_poly.is_valid or mask_poly.area == 0:
                continue
            best_iou = max(best_iou, _polygon_iou(room_poly_px, mask_poly))

        agreement_confidence = min(0.99, 0.55 + best_iou * 0.44)
        note = None
        if best_iou < IOU_AGREEMENT_THRESHOLD:
            note = "AI segmentation disagrees with geometry boundary — review recommended"
            # Active-Learning Hook: Save crop to dataset for fine-tuning
            from app.ai.active_learning import save_doubt_crop
            save_doubt_crop(
                image_path=image_path,
                polygon_px=[(p[0] * image_w, p[1] * image_h) for p in room.polygon_norm],
                label=room.name,
                confidence=round(agreement_confidence, 2),
                reason="IOU_DISAGREEMENT",
            )

        findings.append(
            ValidationFinding(
                kind=DetectionKind.ROOM,
                label=room.name,
                confidence=round(agreement_confidence, 2),
                polygon_px=[(p[0] * image_w, p[1] * image_h) for p in room.polygon_norm],
                source=DetectionSource.FUSION,
                note=note,
            )
        )
    return findings


def detect_symbols(
    image_path: str,
    ocr_text_boxes_px: list[tuple[float, float, float, float]] | None = None,
    scale_ft_per_px: float | None = None,
) -> list[ValidationFinding]:
    """Run YOLOv11-seg and keep only fixture/symbol/architectural relevant classes."""
    raw: list[YoloDetection] = detect_objects(image_path, text_boxes_px=ocr_text_boxes_px)
    findings: list[ValidationFinding] = []

    from PIL import Image
    with Image.open(image_path) as img:
        image_w, image_h = img.size

    for det in raw:
        class_name_lower = det.class_name.lower()
        kind = _YOLO_CLASS_KIND.get(class_name_lower)
        if kind is None:
            # A class the model was never trained to produce (or a future
            # checkpoint's new class we haven't mapped yet) — surface it as
            # a generic symbol rather than dropping it silently, so a
            # dataset/weights change doesn't just make findings vanish.
            kind = DetectionKind.SYMBOL

        if _is_implausibly_large_fixture_finding(det, scale_ft_per_px, image_w, image_h):
            continue

        # Use segmentation polygon coords directly if model supports instance segmentation mask
        if det.polygon_px:
            polygon_px = det.polygon_px
        else:
            x1, y1, x2, y2 = det.bbox_px
            polygon_px = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]

        findings.append(
            ValidationFinding(
                kind=kind,
                label=det.class_name.replace("-", " ").title(),
                confidence=round(det.confidence, 2),
                polygon_px=polygon_px,
                source=DetectionSource.YOLO,
                model_role=det.model_role,
            )
        )
    return findings


# A furniture/fixture symbol's box collapsing to wildly oversized on dense
# real-CAD linework was first found on best_cabinet.pt (a "sink" box
# spanning ~1,500x1,500px, a quarter of an entire building, across
# multiple offices) — but auditing a full real reprocess afterward found
# the exact same failure mode already present, unguarded, from
# best_furniture.pt: "Sofa" boxes at 30-61% of the page on 7 of 8 eligible
# pages. Every YOLO fixture/furniture model here is liable to this on a
# scene far busier than its training data; the gate below is keyed on
# class name and applies across every model's findings, not just one.
#
# A room-context filter (see
# analysis_service._drop_implausible_fixture_findings) doesn't catch this:
# a box that huge still has *some* room polygon under its centroid.
#
# What does catch it: no real example of any of these fixtures/furniture
# pieces is anywhere near this size. Generous ceilings (a big sectional
# sofa, a large kitchen island) so a genuinely large but real piece of
# furniture on an illustrated plan is never rejected — only used when the
# page's scale is actually known, since a wrong/assumed scale must not be
# trusted to delete real findings (same reasoning as the room-detector's
# own real-world size gates).
_FIXTURE_MAX_PLAUSIBLE_SIZE_FT = {
    # best_cabinet.pt's own class names
    "sink": 4.0,
    "small_sink": 3.0,
    "twin_sink": 5.0,
    "toilet": 3.0,
    "tub": 7.0,
    "armchair": 4.0,
    "coffee_table": 5.0,
    "dining_table": 10.0,
    "round_table": 6.0,
    "large_sofa": 10.0,
    "small_sofa": 6.0,
    "bed": 8.0,
    "door": 6.0,
    "window": 10.0,
    "kitchen_bar": 15.0,
    # best_furniture.pt's shorthand names for the same/similar items
    "achair": 4.0,
    "chair": 4.0,
    "ctable": 5.0,
    "dtable": 10.0,
    "sofa": 10.0,
    "ssink": 3.0,
    "ssofa": 6.0,
    "bathtub": 7.0,
    # best.pt's own names (plural "sinks", singular fixtures)
    "sinks": 4.0,
    "vanity": 4.0,
    "shower": 6.0,
    "robes": 4.0,
}


def _is_implausibly_large_fixture_finding(
    det: YoloDetection, scale_ft_per_px: float | None, image_w: int, image_h: int
) -> bool:
    x1, y1, x2, y2 = det.bbox_px
    w_ratio = (x2 - x1) / image_w
    h_ratio = (y2 - y1) / image_h
    # Runaway detection boxes can span half the page on dense linework, whereas
    # a real symbol is never larger than 18% of the sheet size.
    if w_ratio > 0.18 or h_ratio > 0.18:
        return True

    if not scale_ft_per_px or scale_ft_per_px <= 0:
        return False
    max_size_ft = _FIXTURE_MAX_PLAUSIBLE_SIZE_FT.get(det.class_name.lower())
    if max_size_ft is None:
        return False
    longest_side_ft = max(x2 - x1, y2 - y1) * scale_ft_per_px
    return longest_side_ft > max_size_ft


def run_validation(
    geometry: GeometryResult,
    image_path: str,
    image_w: int,
    image_h: int,
    ocr_text_boxes_px: list[tuple[float, float, float, float]] | None = None,
    scale_ft_per_px: float | None = None,
) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    findings.extend(cross_check_rooms(geometry, image_w, image_h, image_path))
    findings.extend(detect_symbols(image_path, ocr_text_boxes_px, scale_ft_per_px))
    return findings


def to_normalized_polygon(finding: ValidationFinding, image_w: int, image_h: int) -> list[list[float]]:
    return [[round(x / image_w, 5), round(y / image_h, 5)] for x, y in finding.polygon_px]
