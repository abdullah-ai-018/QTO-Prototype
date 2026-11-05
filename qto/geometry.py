"""
2D Geometry primitives and vector math for blueprint vector linework.
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Any, Tuple


@dataclass
class Point:
    x: float
    y: float

    def distance_to(self, other: Point) -> float:
        return math.hypot(self.x - other.x, self.y - other.y)

    def __add__(self, other: Point) -> Point:
        return Point(self.x + other.x, self.y + other.y)

    def __sub__(self, other: Point) -> Point:
        return Point(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> Point:
        return Point(self.x * scalar, self.y * scalar)

    def __rmul__(self, scalar: float) -> Point:
        return Point(self.x * scalar, self.y * scalar)

    def dot(self, other: Point) -> float:
        return self.x * other.x + self.y * other.y

    @property
    def norm(self) -> float:
        return math.hypot(self.x, self.y)

    def to_tuple(self) -> Tuple[float, float]:
        return (self.x, self.y)

    def to_dict(self) -> dict[str, float]:
        return {"x": round(self.x, 4), "y": round(self.y, 4)}


@dataclass
class BoundingBox:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return max(0.0, self.x1 - self.x0)

    @property
    def height(self) -> float:
        return max(0.0, self.y1 - self.y0)

    @property
    def center(self) -> Point:
        return Point((self.x0 + self.x1) / 2.0, (self.y0 + self.y1) / 2.0)

    def contains_point(self, px: float, py: float) -> bool:
        return self.x0 <= px <= self.x1 and self.y0 <= py <= self.y1

    def intersects(self, other: BoundingBox) -> bool:
        return not (
            self.x1 < other.x0
            or self.x0 > other.x1
            or self.y1 < other.y0
            or self.y0 > other.y1
        )

    def expand(self, margin: float) -> BoundingBox:
        return BoundingBox(
            x0=self.x0 - margin,
            y0=self.y0 - margin,
            x1=self.x1 + margin,
            y1=self.y1 + margin,
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "x0": round(self.x0, 4),
            "y0": round(self.y0, 4),
            "x1": round(self.x1, 4),
            "y1": round(self.y1, 4),
        }


@dataclass
class Segment:
    x1: float
    y1: float
    x2: float
    y2: float
    length: float = 0.0
    angle: float = 0.0
    min_x: float = 0.0
    max_x: float = 0.0
    min_y: float = 0.0
    max_y: float = 0.0
    ux: float = 0.0
    uy: float = 0.0
    metadata: dict[str, Any] | None = None

    def __post_init__(self):
        dx = self.x2 - self.x1
        dy = self.y2 - self.y1
        if self.length == 0.0:
            self.length = math.hypot(dx, dy)
        if self.angle == 0.0 and self.length > 1e-9:
            self.angle = math.atan2(dy, dx) % math.pi
        self.min_x = min(self.x1, self.x2)
        self.max_x = max(self.x1, self.x2)
        self.min_y = min(self.y1, self.y2)
        self.max_y = max(self.y1, self.y2)
        if self.length > 1e-9:
            self.ux = dx / self.length
            self.uy = dy / self.length
        else:
            self.ux = 0.0
            self.uy = 0.0

    @property
    def midpoint(self) -> Point:
        return Point((self.x1 + self.x2) / 2.0, (self.y1 + self.y2) / 2.0)

    @property
    def bbox(self) -> BoundingBox:
        return BoundingBox(self.min_x, self.min_y, self.max_x, self.max_y)

    def to_dict(self) -> dict[str, Any]:
        d = {
            "x1": round(self.x1, 4),
            "y1": round(self.y1, 4),
            "x2": round(self.x2, 4),
            "y2": round(self.y2, 4),
            "length": round(self.length, 4),
            "angle": round(self.angle, 6),
        }
        if self.metadata:
            d["metadata"] = self.metadata
        return d

    @classmethod
    def from_coords(cls, x1: float, y1: float, x2: float, y2: float, **kwargs) -> Segment:
        return cls(x1=x1, y1=y1, x2=x2, y2=y2, **kwargs)


def point_to_segment_distance(
    px: float, py: float, x1: float, y1: float, x2: float, y2: float
) -> Tuple[float, float, float, float]:
    """
    Computes distance from (px, py) to line segment (x1, y1)-(x2, y2).
    Returns (distance, closest_x, closest_y, projection_parameter_t).
    """
    dx = x2 - x1
    dy = y2 - y1
    len_sq = dx * dx + dy * dy
    if len_sq < 1e-9:
        d = math.hypot(px - x1, py - y1)
        return (d, x1, y1, 0.0)

    t = ((px - x1) * dx + (py - y1) * dy) / len_sq
    t_clamped = max(0.0, min(1.0, t))
    cx = x1 + t_clamped * dx
    cy = y1 + t_clamped * dy
    dist = math.hypot(px - cx, py - cy)
    return (dist, cx, cy, t_clamped)


def angle_diff(a1: float, a2: float) -> float:
    """
    Smallest angle difference in radians between two undirected line angles in [0, pi).
    Returns a value in [0, pi/2].
    """
    diff = abs(a1 - a2) % math.pi
    return min(diff, math.pi - diff)


def project_point_to_axis(
    px: float, py: float, ox: float, oy: float, ux: float, uy: float
) -> Tuple[float, float]:
    """
    Projects point (px, py) onto local 1D wall coordinate system:
    - Origin (ox, oy)
    - Unit vector (ux, uy) along the wall
    - Normal vector (-uy, ux) perpendicular to the wall
    Returns (t_along, d_perp).
    """
    dx = px - ox
    dy = py - oy
    t_along = dx * ux + dy * uy
    d_perp = -dx * uy + dy * ux
    return (t_along, d_perp)


def reconstruct_point_from_axis(
    ox: float, oy: float, ux: float, uy: float, t: float, d: float
) -> Tuple[float, float]:
    """
    Reconstructs 2D world coordinates from local axis (t, d).
    """
    px = ox + t * ux - d * uy
    py = oy + t * uy + d * ux
    return (px, py)


def intervals_overlap(
    t1_min: float, t1_max: float, t2_min: float, t2_max: float
) -> float:
    """
    Calculates overlap between two 1D intervals [t1_min, t1_max] and [t2_min, t2_max].
    Returns positive value for overlap length, or negative value for gap length.
    """
    overlap_start = max(t1_min, t2_min)
    overlap_end = min(t1_max, t2_max)
    return overlap_end - overlap_start


def are_collinear(
    seg1: Segment, seg2: Segment, max_angle_tol: float = math.radians(3.5), max_perp_dist: float = 2.5
) -> bool:
    """
    Checks if seg2 is collinear with seg1 within angle tolerance and perpendicular distance.
    """
    if angle_diff(seg1.angle, seg2.angle) > max_angle_tol:
        return False
    _, d1 = project_point_to_axis(seg2.x1, seg2.y1, seg1.x1, seg1.y1, seg1.ux, seg1.uy)
    _, d2 = project_point_to_axis(seg2.x2, seg2.y2, seg1.x1, seg1.y1, seg1.ux, seg1.uy)
    d_avg = 0.5 * (d1 + d2)
    return abs(d_avg) <= max_perp_dist


def are_parallel(
    seg1: Segment,
    seg2: Segment,
    max_angle_tol: float = math.radians(3.5),
    min_perp_dist: float = 1.0,
    max_perp_dist: float = 13.0,
) -> Tuple[bool, float]:
    """
    Checks if seg2 is parallel to seg1 (opposite wall face).
    Returns (is_parallel, perp_distance).
    """
    if angle_diff(seg1.angle, seg2.angle) > max_angle_tol:
        return (False, 0.0)
    _, d1 = project_point_to_axis(seg2.x1, seg2.y1, seg1.x1, seg1.y1, seg1.ux, seg1.uy)
    _, d2 = project_point_to_axis(seg2.x2, seg2.y2, seg1.x1, seg1.y1, seg1.ux, seg1.uy)
    d_avg = 0.5 * (d1 + d2)
    is_par = min_perp_dist <= abs(d_avg) <= max_perp_dist
    return (is_par, d_avg)
