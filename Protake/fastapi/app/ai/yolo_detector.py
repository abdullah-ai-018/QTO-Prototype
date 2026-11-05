"""YOLOv11 symbol/object detector, via the Ultralytics unified API.

Runs every configured checkpoint as its own inference pass over the same
page and merges their findings into one list — each model was fine-tuned
for a different vocabulary, so this is genuinely additive, not redundant:

  * `yolo_model_path` (required, the primary — `best.pt` by default) is a
    fine-tuned YOLOv11-seg model carrying 17 blueprint classes — door,
    windows, cav-sliders, internal-walls, external-walls, footprint,
    stairs, toilet, sinks, shower, bathtub, vanity, robes, area,
    dimensions, scale, title-block.
  * `yolo_secondary_model_path` (optional — `best_new.pt`) is a 158-class
    room-name/furniture/wall model (BEDROOM, GARAGE, PORCH, WALL, ...).
  * `yolo_furniture_model_path` (optional — `best_furniture.pt`) is a
    12-class furniture/fixture model (armchair, bed, chair, coffee table,
    dining table, sink, sofa, toilet, door, ...).
  * `yolo_roomtype_model_path` (optional — `best_roomtype.pt`) is a
    12-class room-type model (Bedroom, Closet, Dining, Dressing Room,
    Foyer, Hall, Kitchen, Living, Office, Stairs, Study, Washroom).
  * `yolo_cabinet_model_path` (optional — `best_cabinet.pt`) is a 17-class
    furniture/fixture model (Kitchen_bar, Stairs, armchair, bed,
    coffee_table, dining_table, door, large_sofa, round_table, sink,
    small_sink, small_sofa, toilet, tub, twin_sink, wall, window).
    Verified excellent (tight, accurate boxes) on illustrated/scanned
    floor plans, but its bounding boxes collapse to wildly oversized on
    dense real-CAD linework — see
    validation_engine._CABINET_MAX_PLAUSIBLE_SIZE_FT, which exists
    specifically to catch and drop that failure mode.

`yolo11n.pt` (the stock COCO checkpoint) is NOT one of these — it
recognizes people, cars and sofas, not construction symbols. Useful only
for smoke-testing the plumbing before any fine-tuned weights exist.

`validation_engine._YOLO_CLASS_KIND` maps every class name from every one
of these onto a DetectionKind. See `app/ai/training/train_yolo.py` for the
fine-tuning pipeline that produces this style of checkpoint.
"""

from dataclasses import dataclass
from functools import lru_cache

from app.config import get_settings

settings = get_settings()

# Which settings fields hold an optional extra model path, each skipped
# when left blank. The primary (`yolo_model_path`) is required and always
# loaded separately below — this whole module raises if it can't load.
_OPTIONAL_MODEL_SETTINGS = (
    "yolo_secondary_model_path",
    "yolo_furniture_model_path",
    "yolo_roomtype_model_path",
    "yolo_cabinet_model_path",
)

# Short identifier per model, carried on every YoloDetection it produces
# (see `model_role` below) so a caller can single out one model's findings
# without guessing from class-name vocabulary — which was tried for telling
# a commercial floor plan's room-type guesses apart from a residential
# one's and measurably failed (0.44 vs 0.40 vocabulary-overlap ratio on two
# real sheets, indistinguishable). Attribution by model identity is exact;
# attribution by output content is not.
_MODEL_ROLE_BY_SETTING = {
    "yolo_secondary_model_path": "secondary",
    "yolo_furniture_model_path": "furniture",
    "yolo_roomtype_model_path": "roomtype",
    "yolo_cabinet_model_path": "cabinet",
}
PRIMARY_MODEL_ROLE = "primary"


class AiModelUnavailableError(RuntimeError):
    pass


@dataclass
class YoloDetection:
    class_name: str
    confidence: float
    bbox_px: tuple[float, float, float, float]  # x1, y1, x2, y2
    polygon_px: list[tuple[float, float]] | None = None
    # Which configured checkpoint produced this — "primary", "secondary",
    # "furniture", or "roomtype" (see _MODEL_ROLE_BY_SETTING). Lets a caller
    # single out one model's contribution precisely.
    model_role: str = PRIMARY_MODEL_ROLE


@lru_cache(maxsize=None)
def _load_yolo_model(model_path: str):
    from ultralytics import YOLO

    return YOLO(model_path)


def _get_yolo_model():
    try:
        return _load_yolo_model(settings.yolo_model_path)
    except ImportError as exc:  # pragma: no cover
        raise AiModelUnavailableError(
            "ultralytics is not installed. Run `pip install ultralytics` to enable AI validation."
        ) from exc
    except Exception as exc:  # pragma: no cover - network/environment dependent
        raise AiModelUnavailableError(f"Failed to load YOLO model '{settings.yolo_model_path}': {exc}") from exc


def _get_optional_models() -> list[tuple[str, object]]:
    """Every configured optional model that loads successfully, as
    (role, model) pairs — see `model_role` on YoloDetection.

    Each is independent: one bad/missing checkpoint is logged and skipped
    rather than taking down the whole AI-validation pass (a door detection
    from the primary model must never be lost because a fine-tune of a
    different model failed to load).
    """
    models = []
    for setting_name in _OPTIONAL_MODEL_SETTINGS:
        path = getattr(settings, setting_name)
        if not path:
            continue
        try:
            models.append((_MODEL_ROLE_BY_SETTING[setting_name], _load_yolo_model(path)))
        except Exception as exc:
            print(f"Failed to load optional YOLO model '{path}' ({setting_name}): {exc}")
    return models


# Windows are systematically under-confident on illustrated/stylised sheets
# (verified on a real upload: the model found 2-3 real window locations the
# primary model's own training set doesn't closely resemble at 3-10%
# confidence, alongside the one it caught normally at 50%) — the standard
# 0.25 cutoff was discarding real windows, not just noise, on this drawing
# style. Lowered for this class alone: raising recall for every other class
# this liberally would flood real detections with noise, but a window symbol
# is visually simple enough (a rectangle with cross-hatching) that even a
# handful of clearly-noise boxes (see the model's own two implausibly wide
# ones spanning almost the whole sheet, still below even this threshold) cost
# less than silently dropping real windows a human then has to catch by hand.
_CLASS_CONFIDENCE_OVERRIDES = {
    "windows": 0.025,
    "window": 0.025,
    "door": 0.025,
    "doors": 0.025,
}


def _mask_text_regions(image_path: str, text_boxes_px: list[tuple[float, float, float, float]]) -> str:
    """A copy of the page image with every OCR-detected text box painted
    over in white, for the YOLO fixture/room-type passes to run against
    instead of the original.

    Verified on a real commercial floor plan: bold sheet text — the title
    block ("SILESHI CONSULT"), sheet titles ("THIRD FLOOR PLAN"), and
    general notes ("(GENERAL STAFFS OFFICE)") — was being classified as
    "Sink"/"Toilet" fixtures at 25-80% confidence by the furniture model,
    the same failure mode as the earlier finding that it also reads room-
    name labels as "toilet". Blanking every region OCR already knows is
    text, before this model ever sees the page, removes the signal it was
    keying on rather than trying to threshold noisy text-shaped detections
    out after the fact.

    Returns `image_path` unchanged if there are no boxes to mask (the
    common case — no OCR result available for this caller).
    """
    if not text_boxes_px:
        return image_path

    import os
    import tempfile

    import cv2

    img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img is None:
        return image_path

    h, w = img.shape[:2]
    pad = 4
    for x0, y0, x1, y1 in text_boxes_px:
        xi0, yi0 = max(0, int(x0 - pad)), max(0, int(y0 - pad))
        xi1, yi1 = min(w, int(x1 + pad)), min(h, int(y1 + pad))
        if xi1 > xi0 and yi1 > yi0:
            img[yi0:yi1, xi0:xi1] = 255

    fd, tmp_path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    cv2.imwrite(tmp_path, img)
    return tmp_path


def detect_objects(
    image_path: str,
    confidence_threshold: float = 0.25,
    text_boxes_px: list[tuple[float, float, float, float]] | None = None,
) -> list[YoloDetection]:
    if not settings.ai_validation_enabled:
        return []

    models: list[tuple[str, object]] = []
    try:
        models.append((PRIMARY_MODEL_ROLE, _get_yolo_model()))
    except Exception as exc:
        print(f"Error loading primary YOLO model: {exc}")

    models.extend(_get_optional_models())

    # Ultralytics' own `conf` cutoff happens before class is known to us, so
    # it has to be set to the lowest threshold any class needs — the
    # per-class thresholds below then do the real filtering in Python.
    predict_floor = min([confidence_threshold, *_CLASS_CONFIDENCE_OVERRIDES.values()])

    inference_path = _mask_text_regions(image_path, text_boxes_px or [])

    detections: list[YoloDetection] = []
    try:
        for role, model in models:
            results = model.predict(source=inference_path, conf=predict_floor, verbose=False)
            for result in results:
                names = result.names
                has_masks = result.masks is not None
                for i, box in enumerate(result.boxes):
                    class_id = int(box.cls.item())
                    confidence = float(box.conf.item())
                    class_name = names.get(class_id, str(class_id))

                    required_confidence = _CLASS_CONFIDENCE_OVERRIDES.get(class_name.lower(), confidence_threshold)
                    if confidence < required_confidence:
                        continue

                    x1, y1, x2, y2 = (float(v) for v in box.xyxy[0].tolist())

                    polygon_px = None
                    if has_masks and result.masks.xy is not None and len(result.masks.xy) > i:
                        poly_coords = result.masks.xy[i]
                        if len(poly_coords) > 0:
                            polygon_px = [(float(x), float(y)) for x, y in poly_coords.tolist()]

                    detections.append(
                        YoloDetection(
                            class_name=class_name,
                            confidence=confidence,
                            bbox_px=(x1, y1, x2, y2),
                            polygon_px=polygon_px,
                            model_role=role,
                        )
                    )
    finally:
        if inference_path != image_path:
            import os

            try:
                os.remove(inference_path)
            except OSError:
                pass
    return detections
