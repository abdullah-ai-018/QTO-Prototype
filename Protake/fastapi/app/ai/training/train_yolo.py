"""Fine-tunes YOLOv11 on a dataset produced by `dataset_builder.py`.

This is a real, runnable training script — not a stub — but it requires
a dataset (built from your own approved review data, or any COCO/YOLO
formatted construction-symbol dataset you supply) and meaningful compute
time to actually converge. There are no pretrained construction-specific
weights bundled with this project; running this script against enough
labeled data is how you get one.

Usage:
    python -m app.ai.training.train_yolo --data ./datasets/protake/data.yaml --epochs 100
"""

import argparse


def train(data_yaml: str, base_model: str = "yolo11n.pt", epochs: int = 100, image_size: int = 960) -> str:
    from ultralytics import YOLO

    model = YOLO(base_model)
    results = model.train(data=data_yaml, epochs=epochs, imgsz=image_size, patience=20, project="runs/protake_yolo")
    best_weights_path = str(results.save_dir / "weights" / "best.pt")
    print(f"Training complete. Best weights: {best_weights_path}")
    print("Point YOLO_MODEL_PATH in your .env at this file to use the fine-tuned model.")
    return best_weights_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fine-tune YOLOv11 on a Protake-built dataset")
    parser.add_argument("--data", type=str, required=True, help="Path to data.yaml")
    parser.add_argument("--base-model", type=str, default="yolo11n.pt")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=960)
    args = parser.parse_args()

    train(args.data, args.base_model, args.epochs, args.imgsz)
