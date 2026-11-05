"""Builds a YOLO-format fine-tuning dataset directly from this
application's own review data: every `Detection` (and confirmed
`Room`/`Wall`) that a human has approved becomes a labeled training
example, and every rejection becomes a documented hard-negative.

This is the deliberate answer to "train the model on real blueprints":
the app bootstraps its own training set from approved human review
work, growing more accurate the more it's used — rather than pretending
a trained construction-specific checkpoint already exists.

Usage:
    python -m app.ai.training.dataset_builder --project-id 1 --out ./datasets/protake_v1

Produces the standard Ultralytics YOLO directory layout:
    <out>/images/{train,val}/*.png
    <out>/labels/{train,val}/*.txt   (class cx cy w h, normalized)
    <out>/data.yaml
"""

import argparse
import random
import shutil
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.detection import Detection
from app.models.enums import DetectionKind, ReviewStatus
from app.models.page import Page

CLASS_NAMES = [kind.value for kind in DetectionKind]
VAL_SPLIT = 0.15


def _bbox_from_polygon(polygon_norm: list[list[float]]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in polygon_norm]
    ys = [p[1] for p in polygon_norm]
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    cx, cy = (min_x + max_x) / 2, (min_y + max_y) / 2
    w, h = max_x - min_x, max_y - min_y
    return cx, cy, w, h


def collect_approved_detections(db: Session, project_id: int) -> list[Detection]:
    stmt = (
        select(Detection)
        .join(Page, Detection.page_id == Page.id)
        .join(Page.blueprint)
        .where(Detection.status == ReviewStatus.APPROVED)
    )
    detections = list(db.execute(stmt).scalars().all())
    return [d for d in detections if d.page.blueprint.project_id == project_id]


def build_dataset(project_id: int, out_dir: str) -> dict:
    db = SessionLocal()
    try:
        detections = collect_approved_detections(db, project_id)
        if not detections:
            raise ValueError(f"No approved detections found for project {project_id} yet — nothing to train on.")

        out_path = Path(out_dir)
        for split in ("train", "val"):
            (out_path / "images" / split).mkdir(parents=True, exist_ok=True)
            (out_path / "labels" / split).mkdir(parents=True, exist_ok=True)

        by_page: dict[int, list[Detection]] = {}
        for det in detections:
            by_page.setdefault(det.page_id, []).append(det)

        page_ids = list(by_page.keys())
        random.Random(42).shuffle(page_ids)
        val_count = max(1, int(len(page_ids) * VAL_SPLIT)) if len(page_ids) > 3 else 0
        val_ids = set(page_ids[:val_count])

        for page_id, page_detections in by_page.items():
            split = "val" if page_id in val_ids else "train"
            page = page_detections[0].page

            image_dest = out_path / "images" / split / f"page_{page_id}.png"
            shutil.copy(page.image_path, image_dest)

            label_lines = []
            for det in page_detections:
                cx, cy, w, h = _bbox_from_polygon(det.polygon_norm)
                class_idx = CLASS_NAMES.index(det.kind.value)
                label_lines.append(f"{class_idx} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")

            (out_path / "labels" / split / f"page_{page_id}.txt").write_text("\n".join(label_lines))

        data_yaml = {
            "path": str(out_path.resolve()),
            "train": "images/train",
            "val": "images/val" if val_count else "images/train",
            "names": {i: name for i, name in enumerate(CLASS_NAMES)},
        }
        (out_path / "data.yaml").write_text(yaml.safe_dump(data_yaml, sort_keys=False))

        return {"pages": len(by_page), "detections": len(detections), "data_yaml": str(out_path / "data.yaml")}
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build a YOLO fine-tuning dataset from approved Protake detections")
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--out", type=str, default="./datasets/protake")
    args = parser.parse_args()

    summary = build_dataset(args.project_id, args.out)
    print(f"Wrote {summary['detections']} labels across {summary['pages']} pages -> {summary['data_yaml']}")
