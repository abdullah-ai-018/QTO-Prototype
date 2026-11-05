"""SAM2 segmentation, via Ultralytics' unified `SAM` interface (official
Meta SAM2 weights, e.g. `sam2.1_b.pt`) — used to independently segment
room boundaries from point prompts and cross-check them against the
geometry engine's flood-fill result, and to segment around a YOLO
bounding box to get a tighter symbol outline.

Lazily loaded and cached, same pattern as the YOLO detector.
"""

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from app.ai.yolo_detector import AiModelUnavailableError
from app.config import get_settings

settings = get_settings()


@dataclass
class SamMask:
    polygon_px: list[tuple[float, float]]
    confidence: float


@lru_cache(maxsize=1)
def _get_sam_model():
    try:
        from ultralytics import SAM
    except ImportError as exc:  # pragma: no cover
        raise AiModelUnavailableError(
            "ultralytics is not installed. Run `pip install ultralytics` to enable SAM2 segmentation."
        ) from exc

    try:
        return SAM(settings.sam_model_path)
    except Exception as exc:  # pragma: no cover - network/environment dependent
        raise AiModelUnavailableError(f"Failed to load SAM model '{settings.sam_model_path}': {exc}") from exc


def _mask_to_polygon(mask: np.ndarray) -> list[tuple[float, float]] | None:
    import cv2

    binary = (mask > 0.5).astype(np.uint8) * 255
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    largest = max(contours, key=cv2.contourArea)
    epsilon = 0.01 * cv2.arcLength(largest, True)
    approx = cv2.approxPolyDP(largest, epsilon, True)
    pts = approx.reshape(-1, 2)
    if len(pts) < 3:
        return None
    return [(float(x), float(y)) for x, y in pts]


def segment_at_points(image_path: str, point_prompts_px: list[tuple[float, float]]) -> list[SamMask]:
    """Run SAM2 with one positive point prompt per room centroid,
    producing one candidate segmentation polygon per prompt.
    """
    if not settings.ai_validation_enabled or not point_prompts_px:
        return []

    model = _get_sam_model()
    masks: list[SamMask] = []

    for point in point_prompts_px:
        results = model.predict(source=image_path, points=[[point[0], point[1]]], labels=[1], verbose=False)
        for result in results:
            if result.masks is None:
                continue
            for mask_tensor, conf_tensor in zip(result.masks.data, getattr(result, "boxes", []) or [None] * len(result.masks.data)):
                polygon = _mask_to_polygon(mask_tensor.cpu().numpy())
                if polygon:
                    confidence = float(conf_tensor.conf.item()) if conf_tensor is not None else 0.75
                    masks.append(SamMask(polygon_px=polygon, confidence=confidence))
    return masks


def segment_box(image_path: str, bbox_px: tuple[float, float, float, float]) -> SamMask | None:
    """Refine a YOLO bounding box into a tight polygon via SAM2."""
    if not settings.ai_validation_enabled:
        return None

    model = _get_sam_model()
    results = model.predict(source=image_path, bboxes=[list(bbox_px)], verbose=False)
    for result in results:
        if result.masks is None or len(result.masks.data) == 0:
            continue
        polygon = _mask_to_polygon(result.masks.data[0].cpu().numpy())
        if polygon:
            return SamMask(polygon_px=polygon, confidence=0.8)
    return None
