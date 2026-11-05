"""Tests for Ground Truth Forensic & Multi-Metric Evaluation Engine.

Validates the full 12-metric QA verification pipeline:
  1. TP, FP, FN
  2. Precision, Recall, F1 Score
  3. Split Walls Count (1 GT -> N Detected)
  4. Merged Walls Count (N GT -> 1 Detected)
  5. Diagonal Recall
  6. Single-Face Recall
  7. Room-Wall Consistency Rate %
  8. QTO Accuracy % (Net Drywall SF vs Ground Truth)
"""

import pytest
from app.geometry.ground_truth_evaluation import evaluate_ground_truth
from app.models.enums import ReviewStatus


# Mock Detected Wall Helper
class MockDetectedWall:
    def __init__(
        self,
        id: str,
        start_norm: dict,
        end_norm: dict,
        length_ft: float,
        height_ft: float = 9.0,
        status: ReviewStatus = ReviewStatus.APPROVED,
        wall_type: str = "interior",
        has_independent_faces: bool = True,
        face_b_segment_id: int | None = 200,
        room_id: int | None = 101,
        opening_deduction_sqft: float = 0.0,
    ):
        self.id = id
        self.start_norm = start_norm
        self.end_norm = end_norm
        self.length_ft = length_ft
        self.height_ft = height_ft
        self.status = status
        self.wall_type = wall_type
        self.has_independent_faces = has_independent_faces
        self.face_b_segment_id = face_b_segment_id
        self.room_id = room_id
        self.opening_deduction_sqft = opening_deduction_sqft


def test_evaluate_ground_truth_perfect_match():
    """Exact alignment produces Precision=1.0, Recall=1.0, F1=1.0, and QTO Accuracy=100.0%."""
    gt_walls = [
        {
            "id": "gt-1",
            "start_norm": {"x": 0.10, "y": 0.10},
            "end_norm": {"x": 0.50, "y": 0.10},
            "length_ft": 40.0,
            "height_ft": 9.0,
            "opening_deduction_sqft": 0.0,
            "wall_type": "interior",
            "room_ids": [101],
            "is_single_face": False,
        }
    ]

    detected = [
        MockDetectedWall(
            id="det-1",
            start_norm={"x": 0.10, "y": 0.10},
            end_norm={"x": 0.50, "y": 0.10},
            length_ft=40.0,
            height_ft=9.0,
            room_id=101,
        )
    ]

    report = evaluate_ground_truth(detected, gt_walls)

    assert report.true_positives == 1
    assert report.false_positives == 0
    assert report.false_negatives == 0
    assert report.precision == 1.0
    assert report.recall == 1.0
    assert report.f1_score == 1.0
    assert report.qto_accuracy_pct == 100.0
    assert report.room_wall_consistency_pct == 100.0


def test_evaluate_ground_truth_split_walls():
    """1 Ground Truth wall detected as 2 split segments identifies split_walls_count=1."""
    gt_walls = [
        {
            "id": "gt-long",
            "start_norm": {"x": 0.10, "y": 0.20},
            "end_norm": {"x": 0.70, "y": 0.20},
            "length_ft": 60.0,
            "height_ft": 9.0,
            "opening_deduction_sqft": 0.0,
            "wall_type": "interior",
            "room_ids": [101],
        }
    ]

    detected = [
        MockDetectedWall(
            id="det-seg-1",
            start_norm={"x": 0.10, "y": 0.20},
            end_norm={"x": 0.40, "y": 0.20},
            length_ft=30.0,
        ),
        MockDetectedWall(
            id="det-seg-2",
            start_norm={"x": 0.42, "y": 0.20},
            end_norm={"x": 0.70, "y": 0.20},
            length_ft=28.0,
        ),
    ]

    report = evaluate_ground_truth(detected, gt_walls)
    assert report.split_walls_count == 1
    assert report.recall == 1.0


def test_evaluate_ground_truth_merged_walls():
    """2 collinear Ground Truth walls detected as 1 canonical merged wall identifies merged_walls_count=1."""
    gt_walls = [
        {
            "id": "gt-seg-1",
            "start_norm": {"x": 0.10, "y": 0.30},
            "end_norm": {"x": 0.35, "y": 0.30},
            "length_ft": 25.0,
            "height_ft": 9.0,
            "opening_deduction_sqft": 0.0,
        },
        {
            "id": "gt-seg-2",
            "start_norm": {"x": 0.40, "y": 0.30},
            "end_norm": {"x": 0.65, "y": 0.30},
            "length_ft": 25.0,
            "height_ft": 9.0,
            "opening_deduction_sqft": 0.0,
        },
    ]

    detected = [
        MockDetectedWall(
            id="det-bridged-1",
            start_norm={"x": 0.10, "y": 0.30},
            end_norm={"x": 0.65, "y": 0.30},
            length_ft=55.0,
        )
    ]

    report = evaluate_ground_truth(detected, gt_walls)
    assert report.merged_walls_count == 1
    assert report.true_positives == 2


def test_evaluate_ground_truth_diagonal_and_single_face_recall():
    """Computes distinct recall metrics for diagonal and single-face partitions."""
    gt_walls = [
        # Diagonal wall (45 deg)
        {
            "id": "gt-diag",
            "start_norm": {"x": 0.10, "y": 0.10},
            "end_norm": {"x": 0.30, "y": 0.30},
            "length_ft": 28.28,
            "height_ft": 9.0,
            "opening_deduction_sqft": 0.0,
            "is_single_face": False,
        },
        # Single-face promoted wall
        {
            "id": "gt-single-face",
            "start_norm": {"x": 0.50, "y": 0.10},
            "end_norm": {"x": 0.50, "y": 0.40},
            "length_ft": 30.0,
            "height_ft": 9.0,
            "opening_deduction_sqft": 0.0,
            "is_single_face": True,
        },
    ]

    # Only detect the diagonal wall (miss the single-face wall)
    detected = [
        MockDetectedWall(
            id="det-diag",
            start_norm={"x": 0.10, "y": 0.10},
            end_norm={"x": 0.30, "y": 0.30},
            length_ft=28.28,
        )
    ]

    report = evaluate_ground_truth(detected, gt_walls)
    assert report.diagonal_walls_gt_count == 1
    assert report.diagonal_recall == 1.0
    assert report.single_face_walls_gt_count == 1
    assert report.single_face_recall == 0.0
    assert report.recall == 0.5


def test_evaluate_ground_truth_qto_accuracy_with_openings():
    """QTO accuracy accounts for gross square footage and opening deductions."""
    gt_walls = [
        {
            "id": "gt-1",
            "start_norm": {"x": 0.10, "y": 0.10},
            "end_norm": {"x": 0.60, "y": 0.10},
            "length_ft": 50.0,
            "height_ft": 10.0,
            "opening_deduction_sqft": 42.0,  # e.g. two 3x7 doors
        }
    ]

    # Predicted detection has exact geometry and exact opening deduction
    detected = [
        MockDetectedWall(
            id="det-1",
            start_norm={"x": 0.10, "y": 0.10},
            end_norm={"x": 0.60, "y": 0.10},
            length_ft=50.0,
            height_ft=10.0,
            opening_deduction_sqft=42.0,
        )
    ]

    report = evaluate_ground_truth(detected, gt_walls)
    # Ref Gross = 50 * 10 * 2 = 1000 SF; Net = 1000 - 42 = 958 SF
    assert report.reference_qto_gross_sf == 1000.0
    assert report.reference_qto_net_sf == 958.0
    assert report.predicted_qto_net_sf == 958.0
    assert report.qto_variance_pct == 0.0
    assert report.qto_accuracy_pct == 100.0
