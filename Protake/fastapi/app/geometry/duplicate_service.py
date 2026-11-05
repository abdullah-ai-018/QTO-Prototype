"""Spatial Duplicate Detection & Canonical Room Merging Engine (D-012).

Detects duplicate / overlapping room polygons, walls, and door bounding boxes,
and performs principled canonical merging to synthesize optimal boundary geometry,
combine multiple evidence sources, boost confidence, and remap all downstream references.
"""

from dataclasses import dataclass, field
import re
from typing import Any
from shapely.geometry import Polygon
from shapely.ops import unary_union

from app.models.room import Room
from app.models.wall import Wall


@dataclass
class DuplicateFlag:
    entity_type: str
    entity_id_1: int
    entity_id_2: int
    iou_score: float
    message: str


@dataclass
class RoomEvidenceSource:
    room_id: int
    name: str
    area_sqft: float
    perimeter_ft: float
    confidence: float
    source: str
    polygon_norm: list[list[float]]
    room_type: str | None = None
    floor_finish: str | None = None
    wall_finish: str | None = None
    ceiling_finish: str | None = None


@dataclass
class RoomMergeResult:
    canonical_room_id: int
    absorbed_room_ids: list[int]
    merged_polygon_norm: list[list[float]]
    merged_bbox_norm: dict[str, float]
    merged_centroid_norm: dict[str, float]
    merged_area_sqft: float
    merged_perimeter_ft: float
    merged_confidence: float
    merged_name: str
    merged_room_type: str | None
    merged_floor_finish: str | None
    merged_wall_finish: str | None
    merged_ceiling_finish: str | None
    evidence_sources: list[dict[str, Any]]
    iou_score: float


def is_same_physical_room(
    p1: Polygon, p2: Polygon, iou_threshold: float = 0.70, coverage_threshold: float = 0.80
) -> tuple[bool, float]:
    """Determines if two polygons represent the same physical room.
    Returns (is_same, score).
    """
    if not p1.is_valid or not p2.is_valid or p1.is_empty or p2.is_empty:
        return False, 0.0

    a1 = p1.area
    a2 = p2.area
    if a1 <= 0 or a2 <= 0:
        return False, 0.0

    try:
        inter = p1.intersection(p2).area
        union = a1 + a2 - inter
        iou = inter / union if union > 0 else 0.0
        cov1 = inter / a1
        cov2 = inter / a2
    except Exception:
        return False, 0.0

    is_same = (iou >= iou_threshold) or (cov1 >= coverage_threshold) or (cov2 >= coverage_threshold)
    score = max(iou, min(cov1, cov2))
    return is_same, score


def synthesize_room_names(name1: str, name2: str) -> str:
    """Synthesizes a combined name preserving specific OCR labels over generic defaults."""
    n1 = (name1 or "").strip()
    n2 = (name2 or "").strip()

    if not n1:
        return n2 or "Room"
    if not n2:
        return n1

    if n1.lower() == n2.lower():
        return n1

    _generic_re = re.compile(r"^room\s*\d*$", re.IGNORECASE)
    is_gen1 = bool(_generic_re.match(n1))
    is_gen2 = bool(_generic_re.match(n2))

    if is_gen1 and not is_gen2:
        return n2
    if is_gen2 and not is_gen1:
        return n1

    # Both specific: if one is number e.g. "101" and other is "OFFICE", merge as "OFFICE 101"
    if n1.isdigit() and not n2.isdigit():
        return f"{n2} {n1}"
    if n2.isdigit() and not n1.isdigit():
        return f"{n1} {n2}"

    # If already contained
    if n1.lower() in n2.lower():
        return n2
    if n2.lower() in n1.lower():
        return n1

    return f"{n1} / {n2}"


def detect_duplicates(rooms: list[Room], walls: list[Wall]) -> list[DuplicateFlag]:
    """Identifies spatial duplicates across rooms and walls."""
    flags: list[DuplicateFlag] = []
    room_polys = [Polygon(r.polygon_norm) for r in rooms if r.polygon_norm and len(r.polygon_norm) >= 3]

    for i in range(len(room_polys)):
        p1 = room_polys[i]
        for j in range(i + 1, len(room_polys)):
            p2 = room_polys[j]
            is_same, score = is_same_physical_room(p1, p2)
            if is_same:
                flags.append(
                    DuplicateFlag(
                        entity_type="Room",
                        entity_id_1=rooms[i].id,
                        entity_id_2=rooms[j].id,
                        iou_score=round(score, 2),
                        message=f"Duplicate room detected: '{rooms[i].name}' (ID {rooms[i].id}) overlaps with '{rooms[j].name}' (ID {rooms[j].id}) with {int(score*100)}% overlap.",
                    )
                )

    return flags


def merge_room_candidates(rooms: list[Room], scale_ft_per_px: float = 0.0) -> list[RoomMergeResult]:
    """Identifies clusters of duplicate/overlapping room polygons and merges them
    into canonical rooms with synthesized geometry, combined evidence, and boosted confidence.
    """
    if len(rooms) < 2:
        return []

    valid_rooms: list[tuple[Room, Polygon]] = []
    for r in rooms:
        coords = r.polygon_norm
        if coords and len(coords) >= 3:
            p = Polygon(coords)
            if not p.is_valid:
                p = p.buffer(0)
            if p.is_valid and not p.is_empty and p.area > 0:
                valid_rooms.append((r, p))

    n = len(valid_rooms)
    visited = set()
    results: list[RoomMergeResult] = []

    for i in range(n):
        if i in visited:
            continue

        cluster = [i]
        for j in range(i + 1, n):
            if j in visited:
                continue
            r_i, p_i = valid_rooms[i]
            r_j, p_j = valid_rooms[j]
            is_same, score = is_same_physical_room(p_i, p_j)
            if is_same:
                cluster.append(j)

        if len(cluster) > 1:
            for idx in cluster:
                visited.add(idx)

            cluster_rooms = [valid_rooms[idx][0] for idx in cluster]
            cluster_polys = [valid_rooms[idx][1] for idx in cluster]

            # Canonical keeper is the room with the largest area / cleanest polygon
            keeper_idx = max(range(len(cluster_rooms)), key=lambda k: cluster_rooms[k].area_sqft)
            keeper = cluster_rooms[keeper_idx]
            absorbed = [r for k, r in enumerate(cluster_rooms) if k != keeper_idx]

            # Compute union polygon
            try:
                union_poly = unary_union(cluster_polys)
                if union_poly.geom_type == "MultiPolygon":
                    union_poly = max(union_poly.geoms, key=lambda g: g.area)
                if not union_poly.is_valid:
                    union_poly = union_poly.buffer(0)
            except Exception:
                union_poly = cluster_polys[keeper_idx]

            # Extract normalized coordinates
            ext_coords = list(union_poly.exterior.coords)
            if ext_coords and ext_coords[0] == ext_coords[-1]:
                ext_coords = ext_coords[:-1]
            merged_poly_norm = [[round(x, 5), round(y, 5)] for x, y in ext_coords]

            xs = [p[0] for p in merged_poly_norm]
            ys = [p[1] for p in merged_poly_norm]
            merged_bbox = {"minX": min(xs), "minY": min(ys), "maxX": max(xs), "maxY": max(ys)}
            centroid = union_poly.centroid
            merged_centroid = {"x": round(centroid.x, 5), "y": round(centroid.y, 5)}

            # Recalculate area & perimeter proportionally from base keeper polygon
            base_p = valid_rooms[cluster[keeper_idx]][1]
            scale_factor_sq = (keeper.area_sqft / base_p.area) if base_p.area > 0 else 1.0
            merged_area_sqft = round(union_poly.area * scale_factor_sq, 2)
            scale_factor_len = (keeper.perimeter_ft / base_p.length) if base_p.length > 0 else 1.0
            merged_perim_ft = round(union_poly.length * scale_factor_len, 2)

            # Synthesize name
            merged_name = keeper.name
            for r in absorbed:
                merged_name = synthesize_room_names(merged_name, r.name)

            # Synthesize finishes & room type
            merged_type = next((r.room_type for r in cluster_rooms if r.room_type), None)
            merged_floor = next((r.floor_finish for r in cluster_rooms if r.floor_finish), None)
            merged_wall = next((r.wall_finish for r in cluster_rooms if r.wall_finish), None)
            merged_ceiling = next((r.ceiling_finish for r in cluster_rooms if r.ceiling_finish), None)

            # Multi-evidence confidence boost
            max_conf = max(r.confidence for r in cluster_rooms)
            merged_conf = round(min(0.99, max_conf + 0.05 * (len(cluster_rooms) - 1)), 2)

            # Preserve full evidence trail
            evidence_sources = [
                {
                    "room_id": r.id,
                    "name": r.name,
                    "area_sqft": r.area_sqft,
                    "perimeter_ft": r.perimeter_ft,
                    "confidence": r.confidence,
                    "source": str(r.source.value if hasattr(r.source, "value") else r.source),
                    "polygon_norm": r.polygon_norm,
                    "room_type": r.room_type,
                    "floor_finish": r.floor_finish,
                    "wall_finish": r.wall_finish,
                    "ceiling_finish": r.ceiling_finish,
                }
                for r in cluster_rooms
            ]

            results.append(
                RoomMergeResult(
                    canonical_room_id=keeper.id,
                    absorbed_room_ids=[r.id for r in absorbed],
                    merged_polygon_norm=merged_poly_norm,
                    merged_bbox_norm=merged_bbox,
                    merged_centroid_norm=merged_centroid,
                    merged_area_sqft=merged_area_sqft,
                    merged_perimeter_ft=merged_perim_ft,
                    merged_confidence=merged_conf,
                    merged_name=merged_name,
                    merged_room_type=merged_type,
                    merged_floor_finish=merged_floor,
                    merged_wall_finish=merged_wall,
                    merged_ceiling_finish=merged_ceiling,
                    evidence_sources=evidence_sources,
                    iou_score=round(max(is_same_physical_room(valid_rooms[cluster[0]][1], valid_rooms[cluster[k]][1])[1] for k in range(1, len(cluster))), 2),
                )
            )

    return results
