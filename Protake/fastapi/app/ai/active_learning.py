"""Active-Learning Auto-Dataset Generator Module
Saves image crops and annotations for low-confidence or disagreement geometry regions
so they can be directly consumed for YOLO / SAM2 fine-tuning datasets.
"""

import json
import os
import time
from pathlib import Path
import cv2

DATASET_DIR = Path("./storage/dataset/active_learning")


def save_doubt_crop(
    image_path: str,
    polygon_px: list[tuple[float, float]],
    label: str,
    confidence: float,
    reason: str,
) -> str | None:
    """Crops the bounding box of a low-confidence/doubt region from the page image,
    saves the crop image and standard YOLO/COCO annotation JSON to `./storage/dataset/active_learning/`.
    """
    try:
        DATASET_DIR.mkdir(parents=True, exist_ok=True)
        img = cv2.imread(image_path)
        if img is None:
            return None

        xs = [p[0] for p in polygon_px]
        ys = [p[1] for p in polygon_px]
        if not xs or not ys:
            return None

        h, w = img.shape[:2]
        # Add 10% padding around doubt region
        pad_x = int((max(xs) - min(xs)) * 0.1)
        pad_y = int((max(ys) - min(ys)) * 0.1)

        x1 = max(0, int(min(xs)) - pad_x)
        y1 = max(0, int(min(ys)) - pad_y)
        x2 = min(w, int(max(xs)) + pad_x)
        y2 = min(h, int(max(ys)) + pad_y)

        crop = img[y1:y2, x1:x2]
        if crop.size == 0:
            return None

        timestamp = int(time.time() * 1000)
        file_id = f"doubt_{label.replace(' ', '_').lower()}_{timestamp}"
        crop_filename = f"{file_id}.png"
        json_filename = f"{file_id}.json"

        crop_path = DATASET_DIR / crop_filename
        json_path = DATASET_DIR / json_filename

        cv2.imwrite(str(crop_path), crop)

        # Relativize polygon points to crop space
        crop_poly = [[round(p[0] - x1, 2), round(p[1] - y1, 2)] for p in polygon_px]

        annotation = {
            "file_id": file_id,
            "label": label,
            "confidence": confidence,
            "reason": reason,
            "crop_width": x2 - x1,
            "crop_height": y2 - y1,
            "polygon_crop_px": crop_poly,
            "original_image": os.path.basename(image_path),
            "timestamp": timestamp,
        }

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(annotation, f, indent=2)

        return str(crop_path)
    except Exception as exc:
        print(f"Warning: Failed to save active learning crop: {exc}")
        return None
