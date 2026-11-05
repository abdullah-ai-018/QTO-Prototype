"""Automated Multi-Blueprint Benchmark Evaluation Harness

Evaluates system room and wall detection output against the ground-truth benchmark
dataset across 5 blueprint sheets (vector PDF and raster images).

Computes:
  - Room Match Error %
  - Wall Precision (TP / (TP + FP))
  - Wall Recall (TP / (TP + FN))
  - Wall F1-Score (2 * P * R / (P + R))
  - Interior / Exterior Classification Accuracy %
"""

import json
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from shapely.geometry import LineString, Polygon

from app.database import SessionLocal
from app.models.room import Room
from app.models.wall import Wall
from app.trades.drywall_semantic import DrywallSemanticWallPipeline
from app.models.enums import ReviewStatus


def load_ground_truth(path: str = "tests/benchmarks/ground_truth_dataset.json") -> dict:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Ground truth dataset file '{path}' not found.")
    with open(path, "r") as f:
        return json.load(f)


def _to_line_string(start_norm: dict, end_norm: dict) -> LineString:
    p1 = (start_norm.get("x", 0.0), start_norm.get("y", 0.0))
    p2 = (end_norm.get("x", 0.0), end_norm.get("y", 0.0))
    return LineString([p1, p2])


def evaluate_sheet(sheet_key: str, gt_data: dict, db: SessionLocal, pipeline: DrywallSemanticWallPipeline) -> dict:
    page_id = gt_data["page_id"]
    
    # Query current system DB output
    db_rooms = db.query(Room).filter(Room.page_id == page_id).all()
    db_walls = db.query(Wall).filter(Wall.page_id == page_id).all()
    
    # Process through Drywall Semantic Pipeline
    semantic_walls = pipeline.process(db_rooms, db_walls)
    pred_approved = [w for w in semantic_walls if w.status == ReviewStatus.APPROVED]

    # Evaluate via GroundTruthForensicEngine
    from app.geometry.ground_truth_evaluation import evaluate_ground_truth
    gt_walls = gt_data.get("ground_truth_walls", [])
    report = evaluate_ground_truth(
        detected_walls=pred_approved,
        ground_truth_walls=gt_walls,
        detected_rooms=db_rooms,
        ground_truth_rooms=gt_data.get("rooms", []),
    )
    
    # Room Metrics
    exp_rooms = gt_data["expected_room_count"]
    pred_rooms = len(db_rooms)
    room_diff = abs(pred_rooms - exp_rooms)
    room_error_pct = (room_diff / exp_rooms * 100.0) if exp_rooms > 0 else 0.0
    
    return {
        "sheet_key": sheet_key,
        "page_id": page_id,
        "name": gt_data["name"],
        "expected_rooms": exp_rooms,
        "predicted_rooms": pred_rooms,
        "room_error_pct": round(room_error_pct, 1),
        "expected_walls": gt_data.get("expected_wall_count", len(gt_walls)),
        "predicted_approved_walls": len(pred_approved),
        "tp": report.true_positives,
        "fp": report.false_positives,
        "fn": report.false_negatives,
        "precision": report.precision,
        "recall": report.recall,
        "f1_score": report.f1_score,
        "split_walls": report.split_walls_count,
        "merged_walls": report.merged_walls_count,
        "diagonal_recall": report.diagonal_recall,
        "single_face_recall": report.single_face_recall,
        "room_wall_consistency_pct": report.room_wall_consistency_pct,
        "reference_qto_net_sf": report.reference_qto_net_sf,
        "predicted_qto_net_sf": report.predicted_qto_net_sf,
        "qto_accuracy_pct": report.qto_accuracy_pct,
    }


def run_benchmark():
    gt_dataset = load_ground_truth()
    db = SessionLocal()
    pipeline = DrywallSemanticWallPipeline()
    
    results = []
    print("=" * 80)
    print("      QUANTITATIVE MULTI-BLUEPRINT BENCHMARK EVALUATION HARNESS")
    print("=" * 80)
    
    for key, gt_data in gt_dataset.items():
        res = evaluate_sheet(key, gt_data, db, pipeline)
        results.append(res)
        
        print(f"\nSheet: {res['name']} (Page {res['page_id']})")
        print(f"  Rooms: Expected = {res['expected_rooms']} | Predicted = {res['predicted_rooms']} | Room Error = {res['room_error_pct']}%")
        print(f"  Walls: Expected = {res['expected_walls']} | Approved Output = {res['predicted_approved_walls']} (TP={res['tp']}, FP={res['fp']}, FN={res['fn']})")
        print(f"  Scores: Precision = {res['precision']:.4f} | Recall = {res['recall']:.4f} | F1-Score = {res['f1_score']:.4f}")
        print(f"  Topology: Split Walls = {res['split_walls']} | Merged Walls = {res['merged_walls']} | Diagonal Recall = {res['diagonal_recall']:.2f} | Single-Face Recall = {res['single_face_recall']:.2f} | Room-Wall Consistency = {res['room_wall_consistency_pct']}%")
        print(f"  Takeoff: Predicted Net = {res['predicted_qto_net_sf']:.1f} SF | Reference Net = {res['reference_qto_net_sf']:.1f} SF | QTO Accuracy = {res['qto_accuracy_pct']:.1f}%")

    # Overall Summary Metrics
    avg_prec = sum(r["precision"] for r in results) / len(results)
    avg_rec = sum(r["recall"] for r in results) / len(results)
    avg_f1 = sum(r["f1_score"] for r in results) / len(results)
    avg_room_err = sum(r["room_error_pct"] for r in results) / len(results)
    avg_room_consistency = sum(r["room_wall_consistency_pct"] for r in results) / len(results)
    avg_qto_acc = sum(r["qto_accuracy_pct"] for r in results) / len(results)
    
    summary = {
        "benchmark_sheets_count": len(results),
        "avg_precision": round(avg_prec, 4),
        "avg_recall": round(avg_rec, 4),
        "avg_f1_score": round(avg_f1, 4),
        "avg_room_error_pct": round(avg_room_err, 1),
        "avg_room_wall_consistency_pct": round(avg_room_consistency, 1),
        "avg_qto_accuracy_pct": round(avg_qto_acc, 1),
        "sheet_results": results,
    }
    
    out_path = "tests/benchmarks/baseline_scores.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
        
    print("\n" + "=" * 80)
    print("                      OVERALL BENCHMARK SUMMARY")
    print("=" * 80)
    print(f"Total Benchmark Sheets Evaluated:    {len(results)}")
    print(f"Average Wall Precision:               {avg_prec:.4f}")
    print(f"Average Wall Recall:                  {avg_rec:.4f}")
    print(f"Average Wall F1-Score:                {avg_f1:.4f}")
    print(f"Average Room Count Error:             {avg_room_err:.1f}%")
    print(f"Average Room-Wall Consistency:        {avg_room_consistency:.1f}%")
    print(f"Average Drywall QTO Accuracy:         {avg_qto_acc:.1f}%")
    print(f"Saved baseline results to: {out_path}")
    print("=" * 80)
    
    db.close()


if __name__ == "__main__":
    run_benchmark()
