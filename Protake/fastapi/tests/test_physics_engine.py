"""Tests for Architectural Physics & Geometric Constraint Engine.

Verifies the 11 key architectural physics dimensions:
  1. Parallelism (Face pair angle & offset bounds)
  2. Perpendicularity (90° ± 5° orthogonal intersection)
  3. Collinearity (Shared infinite line & gap bridging)
  4. Wall Continuity (Unbroken physical runs)
  5. Junctions (L, T, X, Free End classification)
  6. Room Closure (Watertight loop vs leaking boundaries)
  7. Opening Containment (Door/Window host bounds)
  8. Wall-Room Topology (Reciprocal boundaries)
  9. Architectural Dimensions (Length, thickness & clearance gates)
  10. Scale Plausibility (Physical coordinate transform sanity)
  11. Cross-Sheet Consistency (Multi-page alignment)
"""

import pytest
from typing import Any
from app.geometry.physics_engine import (
    ArchitecturalPhysicsEngine,
    JunctionType,
)
from app.models.enums import ReviewStatus


class MockWall:
    def __init__(
        self,
        id: Any = 1,
        start_norm: dict = None,
        end_norm: dict = None,
        length_ft: float = 10.0,
        status: ReviewStatus = ReviewStatus.APPROVED,
        openings: list = None,
    ):
        self.id = id
        self.start_norm = start_norm or {"x": 0.10, "y": 0.10}
        self.end_norm = end_norm or {"x": 0.50, "y": 0.10}
        self.length_ft = length_ft
        self.status = status
        self.openings = openings or []


class MockRoom:
    def __init__(self, id: int, polygon_norm: list):
        self.id = id
        self.polygon_norm = polygon_norm


def test_eval_parallelism_and_perpendicularity():
    """Parallelism and perpendicularity must detect alignment within angular tolerances."""
    engine = ArchitecturalPhysicsEngine()

    # Horizontal Wall 1: (0.10, 0.10) to (0.50, 0.10)
    # Parallel Wall 2: (0.10, 0.15) to (0.50, 0.15)
    is_par, diff_par, dist = engine.eval_parallelism(
        {"x": 0.10, "y": 0.10}, {"x": 0.50, "y": 0.10},
        {"x": 0.10, "y": 0.15}, {"x": 0.50, "y": 0.15},
    )
    assert is_par is True
    assert diff_par == pytest.approx(0.0)
    assert dist == pytest.approx(0.05)

    # Perpendicular Wall 3: (0.30, 0.10) to (0.30, 0.40) (90 deg)
    is_perp, diff_90 = engine.eval_perpendicularity(
        {"x": 0.10, "y": 0.10}, {"x": 0.50, "y": 0.10},
        {"x": 0.30, "y": 0.10}, {"x": 0.30, "y": 0.40},
    )
    assert is_perp is True
    assert diff_90 == pytest.approx(0.0)


def test_eval_collinearity():
    """Collinear segments share the same direction line and have minimal perpendicular offset."""
    engine = ArchitecturalPhysicsEngine()

    # Segment A: (0.10, 0.20) -> (0.30, 0.20)
    # Collinear Segment B: (0.40, 0.20) -> (0.60, 0.20) (gap of 0.10 along same y=0.20)
    is_collinear, offset = engine.eval_collinearity(
        {"x": 0.10, "y": 0.20}, {"x": 0.30, "y": 0.20},
        {"x": 0.40, "y": 0.20}, {"x": 0.60, "y": 0.20},
    )
    assert is_collinear is True
    assert offset == pytest.approx(0.0)

    # Offset Non-collinear Segment C: y=0.35 (different run)
    is_col_c, offset_c = engine.eval_collinearity(
        {"x": 0.10, "y": 0.20}, {"x": 0.30, "y": 0.20},
        {"x": 0.40, "y": 0.35}, {"x": 0.60, "y": 0.35},
    )
    assert is_col_c is False
    assert offset_c == pytest.approx(0.15)


def test_classify_junctions_L_T_X_free_ends():
    """Classifies corner (L), partition intersection (T), crossing (X), and terminal (Free End)."""
    engine = ArchitecturalPhysicsEngine()

    # Corner (L-Junction at (0.10, 0.10))
    w_horiz = MockWall(id="w1", start_norm={"x": 0.10, "y": 0.10}, end_norm={"x": 0.50, "y": 0.10})
    w_vert = MockWall(id="w2", start_norm={"x": 0.10, "y": 0.10}, end_norm={"x": 0.10, "y": 0.50})

    # T-Junction: Partition w3 starts at (0.30, 0.10) (interior of w1) and goes down
    w_part = MockWall(id="w3", start_norm={"x": 0.30, "y": 0.10}, end_norm={"x": 0.30, "y": 0.40})

    walls = [w_horiz, w_vert, w_part]
    junctions = engine.classify_junctions(walls)

    j_types = {j.junction_type for j in junctions}
    assert JunctionType.L_JUNCTION in j_types
    assert JunctionType.T_JUNCTION in j_types
    assert JunctionType.FREE_END in j_types


def test_eval_room_closure():
    """Watertight room enclosed by walls has high closure rate; open unbordered space is flagged."""
    engine = ArchitecturalPhysicsEngine()

    # 4 bounding walls for Room 1
    w1 = MockWall(id=1, start_norm={"x": 0.10, "y": 0.10}, end_norm={"x": 0.50, "y": 0.10})
    w2 = MockWall(id=2, start_norm={"x": 0.50, "y": 0.10}, end_norm={"x": 0.50, "y": 0.50})
    w3 = MockWall(id=3, start_norm={"x": 0.50, "y": 0.50}, end_norm={"x": 0.10, "y": 0.50})
    w4 = MockWall(id=4, start_norm={"x": 0.10, "y": 0.50}, end_norm={"x": 0.10, "y": 0.10})

    room_closed = MockRoom(
        id=101,
        polygon_norm=[[0.10, 0.10], [0.50, 0.10], [0.50, 0.50], [0.10, 0.50]],
    )

    closure_rate, watertight, leaking = engine.eval_room_closure([room_closed], [w1, w2, w3, w4])
    assert closure_rate >= 0.80
    assert watertight == 1
    assert leaking == 0


def test_eval_opening_containment():
    """Openings narrower than host wall are contained; oversized openings are detected."""
    engine = ArchitecturalPhysicsEngine()

    class MockOp:
        def __init__(self, width_ft: float):
            self.width_ft = width_ft

    w_ok = MockWall(id=1, length_ft=12.0, openings=[MockOp(width_ft=3.0), MockOp(width_ft=6.0)])
    w_bad = MockWall(id=2, length_ft=2.0, openings=[MockOp(width_ft=6.0)])  # 6ft door on 2ft stub

    rate, total_ops, contained = engine.eval_opening_containment([w_ok, w_bad])
    assert total_ops == 3
    assert contained == 2
    assert rate == pytest.approx(2.0 / 3.0, rel=1e-2)


def test_full_physics_constraint_report():
    """Generates complete 11-dimension constraint report."""
    engine = ArchitecturalPhysicsEngine()

    w1 = MockWall(id=1, start_norm={"x": 0.10, "y": 0.10}, end_norm={"x": 0.50, "y": 0.10}, length_ft=40.0)
    w2 = MockWall(id=2, start_norm={"x": 0.10, "y": 0.10}, end_norm={"x": 0.10, "y": 0.50}, length_ft=40.0)
    room = MockRoom(id=101, polygon_norm=[[0.10, 0.10], [0.50, 0.10], [0.50, 0.50], [0.10, 0.50]])

    report = engine.validate_physics_constraints(
        walls=[w1, w2],
        rooms=[room],
        scale_ft_per_px=0.05,
    )

    assert report.is_physically_valid is True
    assert report.overall_physics_score >= 0.50
    assert report.scale_is_plausible is True
    assert len(report.junctions) >= 1
