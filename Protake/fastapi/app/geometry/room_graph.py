import math
from dataclasses import dataclass, field
from typing import Any
import networkx as nx
from shapely.geometry import Polygon, LineString, MultiPolygon, Point
from shapely.ops import unary_union

from app.geometry.polygon_ops import (
    RECIPROCAL_DIRECTIONS,
    classify_cardinal_direction,
    compute_wall_face_directions,
    extract_room_boundary_segments,
)


@dataclass
class RoomBoundaryEdge:
    room_id: int | str
    edge_index: int
    start: dict[str, float]
    end: dict[str, float]
    midpoint: dict[str, float]
    length_norm: float
    outward_normal: dict[str, float]
    direction: str
    matched_wall_id: int | str | None = None
    matched_wall_side: str | None = None  # "side_a" or "side_b"
    verified: bool = False
    verification_reason: str | None = None


@dataclass
class WallAttachment:
    wall_id: int | str
    start_norm: dict[str, float]
    end_norm: dict[str, float]
    side_a_room_id: int | str | None = None
    side_a_direction: str = "unknown"
    side_a_verified: bool = False
    side_b_room_id: int | str | None = None
    side_b_direction: str = "unknown"
    side_b_verified: bool = False
    status: str = "pending"
    reasons: list[str] = field(default_factory=list)


@dataclass
class BidirectionalVerificationReport:
    is_consistent: bool
    verified_pairs: list[dict[str, Any]] = field(default_factory=list)
    mismatched_pairs: list[dict[str, Any]] = field(default_factory=list)
    unattached_boundaries: list[dict[str, Any]] = field(default_factory=list)
    orphaned_walls: list[int | str] = field(default_factory=list)


class RoomGraph:
    """Topological graph of architectural spaces and boundary interfaces with
    deterministic Bidirectional Room <-> Wall Context Verification (D-004).
    """

    def __init__(self, rooms: list[Any]):
        self.rooms = rooms
        self.graph = nx.Graph()
        self.room_polygons: dict[int | str, Polygon] = {}
        self.room_boundaries: dict[int | str, list[RoomBoundaryEdge]] = {}
        self.wall_attachments: dict[int | str, WallAttachment] = {}
        self._build_polygons()
        self._build_boundaries()
        self._build_envelope()

    def _build_polygons(self):
        for idx, r in enumerate(self.rooms):
            if isinstance(r, dict):
                rid = r.get("id", idx)
            else:
                rid = getattr(r, "id", None)
                if rid is None:
                    rid = idx

            polygon_norm = getattr(r, "polygon_norm", None)
            if not polygon_norm and isinstance(r, dict):
                polygon_norm = r.get("polygon_norm")
            if not polygon_norm:
                continue

            pts = []
            for p in polygon_norm:
                if isinstance(p, dict) and "x" in p and "y" in p:
                    pts.append((float(p["x"]), float(p["y"])))
                elif isinstance(p, (list, tuple)) and len(p) >= 2:
                    pts.append((float(p[0]), float(p[1])))

            if len(pts) >= 3:
                poly = Polygon(pts)
                if not poly.is_valid:
                    poly = poly.buffer(0)
                if not poly.is_empty:
                    self.room_polygons[rid] = poly
                    name = r.get("name") if isinstance(r, dict) else getattr(r, "name", f"Room {rid}")
                    area = r.get("area_sqft") if isinstance(r, dict) else getattr(r, "area_sqft", poly.area)
                    r_type = r.get("room_type") if isinstance(r, dict) else getattr(r, "room_type", None)
                    is_unconditioned = (
                        r_type in ("exterior_covered", "outdoor", "balcony")
                        or any(kw in str(name).lower() for kw in ["covered", "patio", "deck", "porch", "outdoor", "trellis", "gazebo", "canopy"])
                    )
                    self.graph.add_node(rid, name=name, area=area, poly=poly, unconditioned=is_unconditioned)

    def _build_boundaries(self):
        """Extracts and stores directional boundary edges for all rooms."""
        for idx, r in enumerate(self.rooms):
            if isinstance(r, dict):
                rid = r.get("id", idx)
            else:
                rid = getattr(r, "id", None)
                if rid is None:
                    rid = idx

            polygon_norm = getattr(r, "polygon_norm", None)
            if not polygon_norm and isinstance(r, dict):
                polygon_norm = r.get("polygon_norm")
            if not polygon_norm:
                continue

            edges = extract_room_boundary_segments(polygon_norm)
            self.room_boundaries[rid] = [
                RoomBoundaryEdge(
                    room_id=rid,
                    edge_index=e["edge_index"],
                    start=e["start"],
                    end=e["end"],
                    midpoint=e["midpoint"],
                    length_norm=e["length_norm"],
                    outward_normal=e["outward_normal"],
                    direction=e["direction"],
                )
                for e in edges
            ]

    def _build_envelope(self):
        """Constructs the true conditioned space footprint."""
        if not self.room_polygons:
            self.envelope_polygon = Polygon([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)])
            self.envelope_bbox = {"minX": 0.0, "minY": 0.0, "maxX": 1.0, "maxY": 1.0}
            return

        conditioned_polys = [
            poly for rid, poly in self.room_polygons.items()
            if not (self.graph.nodes[rid].get("unconditioned", False) if rid in self.graph.nodes else False)
        ]
        all_polys = conditioned_polys or list(self.room_polygons.values())
        try:
            union_poly = unary_union(all_polys)
            self.envelope_polygon = union_poly
        except Exception:
            self.envelope_polygon = unary_union(all_polys)

        bounds = self.envelope_polygon.bounds
        self.envelope_bbox = {
            "minX": bounds[0],
            "minY": bounds[1],
            "maxX": bounds[2],
            "maxY": bounds[3],
        }

    def classify_wall_topology(
        self, p1: tuple[float, float], p2: tuple[float, float]
    ) -> tuple[str, list[int], list[int], str]:
        """Classifies a wall segment topologically:
        - 'interior': Separates two interior rooms or forms internal corridor/room partition
        - 'exterior': Bounds a conditioned room directly along the outer building envelope facade
        - 'unconditioned_exterior': Unattached balcony railing / outdoor terrace / site line
        
        Returns:
            (classification, room_ids, adjacent_room_ids, reason)
        """
        wall_line = LineString([p1, p2])
        dx1 = p2[0] - p1[0]
        dy1 = p2[1] - p1[1]
        w_len = math.hypot(dx1, dy1)
        if w_len < 1e-6:
            return "unconditioned_exterior", [], [], "zero_length"

        if not self.room_polygons:
            return "interior", [], [], "no_rooms_in_graph"

        intersecting_rooms = []

        # Match against room boundary edges with strict collinear span overlap
        for room_id, edges in self.room_boundaries.items():
            matched_room = False
            for edge in edges:
                esx, esy = edge.start["x"], edge.start["y"]
                eex, eey = edge.end["x"], edge.end["y"]
                edx = eex - esx
                edy = eey - esy
                e_len = math.hypot(edx, edy)
                if e_len < 1e-6:
                    continue

                # Angle check (must be parallel within 10.0 degrees)
                ang1 = math.degrees(math.atan2(dy1, dx1)) % 180.0
                ang2 = math.degrees(math.atan2(edy, edx)) % 180.0
                diff = abs(ang1 - ang2)
                if diff > 90.0:
                    diff = 180.0 - diff
                if diff > 10.0:
                    continue

                # Perpendicular distance check (<= 0.025 norm ~ 25 inches)
                edge_line = LineString([(esx, esy), (eex, eey)])
                if wall_line.distance(edge_line) > 0.025:
                    continue

                # Longitudinal span overlap check (>= 20% of shorter span or close proximity)
                ux, uy = dx1 / w_len, dy1 / w_len
                proj_s = (esx - p1[0]) * ux + (esy - p1[1]) * uy
                proj_e = (eex - p1[0]) * ux + (eey - p1[1]) * uy
                min_p, max_p = min(proj_s, proj_e), max(proj_s, proj_e)
                overlap = max(0.0, min(w_len, max_p) - max(0.0, min_p))
                if overlap >= 0.20 * min(w_len, e_len) or wall_line.distance(edge_line) <= 0.012:
                    matched_room = True
                    break

            if matched_room:
                intersecting_rooms.append(room_id)

        # If no edge was matched, check if wall is an internal partition inside a room polygon
        if not intersecting_rooms:
            for room_id, poly in self.room_polygons.items():
                if poly.contains(wall_line) or poly.intersects(wall_line) or wall_line.distance(poly) <= 0.015:
                    intersecting_rooms.append(room_id)

        # Filter to only conditioned interior building rooms
        conditioned_intersecting_rooms = [
            rid for rid in intersecting_rooms
            if not (self.graph.nodes[rid].get("unconditioned", False) if rid in self.graph.nodes else False)
        ]

        # Topological classification rules:
        if len(conditioned_intersecting_rooms) >= 2:
            # Separates two distinct interior spaces -> True Interior Partition (2 sides GWB)
            return "interior", conditioned_intersecting_rooms, conditioned_intersecting_rooms, "separates_two_interior_rooms"
        elif len(conditioned_intersecting_rooms) == 1:
            # Bounds a single conditioned room:
            # Check if wall is along the outer perimeter boundary of the entire footprint
            is_on_outer_envelope = False
            try:
                if hasattr(self.envelope_polygon, "exterior"):
                    env_line = LineString(self.envelope_polygon.exterior.coords)
                    is_on_outer_envelope = (wall_line.distance(env_line) <= 0.030)
                elif hasattr(self.envelope_polygon, "geoms"):
                    is_on_outer_envelope = any(
                        wall_line.distance(LineString(g.exterior.coords)) <= 0.030
                        for g in self.envelope_polygon.geoms
                    )
            except Exception:
                is_on_outer_envelope = False

            if is_on_outer_envelope:
                return "exterior", conditioned_intersecting_rooms, [], "conditioned_room_exterior_envelope"
            else:
                # Internal corridor partition bounding a room
                return "interior", conditioned_intersecting_rooms, [], "interior_corridor_or_room_partition"
        else:
            return "unconditioned_exterior", [], [], "unconditioned_exterior_railing_or_site_element"

    def attach_and_verify_walls(
        self,
        walls: list[Any],
        tolerance_norm: float = 0.040,
        probe_dist_norm: float = 0.015,
    ) -> BidirectionalVerificationReport:
        """D-004: Comprehensive Bidirectional Proof Engine between Walls and Rooms.
        
        Performs full geometric and directional verification:
        1. Decomposes each Wall into Side A / Side B faces with directional bearings.
        2. Probes Side A and Side B to identify attached rooms.
        3. Matches room boundary segments against candidate walls.
        4. Cross-verifies reciprocal agreement:
           - Room R's boundary in direction D (e.g. North) <=> Wall W's face in reciprocal direction D' (e.g. South).
        5. Returns a structured audit report and updates attachment state.
        """
        import math

        verified_pairs: list[dict[str, Any]] = []
        mismatched_pairs: list[dict[str, Any]] = []
        orphaned_walls: list[int | str] = []

        for idx, w in enumerate(walls):
            if isinstance(w, dict):
                wid = w.get("id", idx)
            else:
                wid = getattr(w, "id", None)
                if wid is None:
                    wid = idx

            # Extract start and end coordinates
            sn = getattr(w, "start_norm", None)
            en = getattr(w, "end_norm", None)
            if isinstance(w, dict):
                sn = sn or w.get("start_norm")
                en = en or w.get("end_norm")

            if not sn or not en:
                continue

            sx, sy = float(sn["x"]), float(sn["y"])
            ex, ey = float(en["x"]), float(en["y"])
            wall_line = LineString([(sx, sy), (ex, ey)])

            face_info = compute_wall_face_directions((sx, sy), (ex, ey))
            sa_dir = face_info["side_a_direction"]
            sb_dir = face_info["side_b_direction"]
            sa_nx = face_info["side_a_normal"]["x"]
            sa_ny = face_info["side_a_normal"]["y"]
            sb_nx = face_info["side_b_normal"]["x"]
            sb_ny = face_info["side_b_normal"]["y"]

            # Midpoint & probe points for Side A and Side B
            mx = (sx + ex) / 2.0
            my = (sy + ey) / 2.0
            probe_a = Point(mx + sa_nx * probe_dist_norm, my + sa_ny * probe_dist_norm)
            probe_b = Point(mx + sb_nx * probe_dist_norm, my + sb_ny * probe_dist_norm)

            # Probe Side A room
            side_a_room: int | str | None = None
            side_b_room: int | str | None = None

            for rid, poly in self.room_polygons.items():
                if poly.contains(probe_a) or poly.distance(probe_a) <= 0.005:
                    side_a_room = rid
                if poly.contains(probe_b) or poly.distance(probe_b) <= 0.005:
                    side_b_room = rid

            # If probe didn't land inside, fallback to boundary distance + normal projection
            if side_a_room is None or side_b_room is None:
                for rid, poly in self.room_polygons.items():
                    if wall_line.distance(poly.exterior) <= tolerance_norm:
                        # Test if room centroid is on Side A or Side B
                        cx, cy = poly.centroid.x, poly.centroid.y
                        dot_a = sa_nx * (cx - mx) + sa_ny * (cy - my)
                        if dot_a > 0 and side_a_room is None:
                            side_a_room = rid
                        elif dot_a < 0 and side_b_room is None:
                            side_b_room = rid

            # Create attachment record
            attachment = WallAttachment(
                wall_id=wid,
                start_norm={"x": sx, "y": sy},
                end_norm={"x": ex, "y": ey},
                side_a_room_id=side_a_room,
                side_a_direction=sa_dir,
                side_b_room_id=side_b_room,
                side_b_direction=sb_dir,
            )
            self.wall_attachments[wid] = attachment

            if side_a_room is None and side_b_room is None:
                orphaned_walls.append(wid)

        # Now link Room Boundaries to Walls and perform Bidirectional Verification
        for rid, boundaries in self.room_boundaries.items():
            for edge in boundaries:
                edge_line = LineString([
                    (edge.start["x"], edge.start["y"]),
                    (edge.end["x"], edge.end["y"]),
                ])
                emx = edge.midpoint["x"]
                emy = edge.midpoint["y"]
                e_dir = edge.direction
                e_reciprocal = RECIPROCAL_DIRECTIONS.get(e_dir, "unknown")

                # Find closest wall within tolerance that is roughly collinear
                best_wall_id = None
                best_dist = tolerance_norm
                best_side = None

                for wid, att in self.wall_attachments.items():
                    w_line = LineString([
                        (att.start_norm["x"], att.start_norm["y"]),
                        (att.end_norm["x"], att.end_norm["y"]),
                    ])
                    dist = edge_line.distance(w_line)
                    if dist <= best_dist:
                        # Check angular alignment: dot product of edge vector and wall vector
                        edx = edge.end["x"] - edge.start["x"]
                        edy = edge.end["y"] - edge.start["y"]
                        wdx = att.end_norm["x"] - att.start_norm["x"]
                        wdy = att.end_norm["y"] - att.start_norm["y"]
                        e_len = math.hypot(edx, edy)
                        w_len = math.hypot(wdx, wdy)
                        if e_len > 0 and w_len > 0:
                            cos_theta = abs((edx * wdx + edy * wdy) / (e_len * w_len))
                            if cos_theta >= 0.70:  # within ~45 degrees collinear
                                best_dist = dist
                                best_wall_id = wid
                                # Check which wall face points back toward this room boundary
                                if att.side_a_room_id == rid:
                                    best_side = "side_a"
                                elif att.side_b_room_id == rid:
                                    best_side = "side_b"
                                else:
                                    # Compare facing direction with wall face directions
                                    if att.side_a_direction == e_reciprocal:
                                        best_side = "side_a"
                                    elif att.side_b_direction == e_reciprocal:
                                        best_side = "side_b"

                if best_wall_id is not None:
                    edge.matched_wall_id = best_wall_id
                    edge.matched_wall_side = best_side
                    att = self.wall_attachments[best_wall_id]

                    # Bidirectional Consistency Proof:
                    # Room says: "Wall W is my boundary in direction D (e.g. North)"
                    # Wall must say: "Room R is attached on my reciprocal face (e.g. South)"
                    wall_face_dir = getattr(att, f"{best_side}_direction", "unknown") if best_side else "unknown"
                    attached_room = getattr(att, f"{best_side}_room_id", None) if best_side else None

                    direction_agrees = (wall_face_dir == e_reciprocal or e_reciprocal == "unknown" or wall_face_dir == "unknown")
                    room_agrees = (attached_room == rid or attached_room is None)

                    if direction_agrees and room_agrees:
                        edge.verified = True
                        edge.verification_reason = "bidirectional_proof_confirmed"
                        if best_side == "side_a":
                            att.side_a_room_id = rid
                            att.side_a_verified = True
                        elif best_side == "side_b":
                            att.side_b_room_id = rid
                            att.side_b_verified = True

                        verified_pairs.append({
                            "room_id": rid,
                            "wall_id": best_wall_id,
                            "room_boundary_direction": e_dir,
                            "wall_face_direction": wall_face_dir,
                            "wall_side": best_side,
                        })
                    else:
                        edge.verified = False
                        edge.verification_reason = f"orientation_mismatch (room_boundary={e_dir}, wall_face={wall_face_dir}, attached_room={attached_room})"
                        mismatched_pairs.append({
                            "room_id": rid,
                            "wall_id": best_wall_id,
                            "room_boundary_direction": e_dir,
                            "wall_face_direction": wall_face_dir,
                            "expected_wall_face": e_reciprocal,
                            "attached_room": attached_room,
                            "reason": edge.verification_reason,
                        })

        unattached_boundaries = []
        for rid, boundaries in self.room_boundaries.items():
            for edge in boundaries:
                if not edge.verified:
                    unattached_boundaries.append({
                        "room_id": rid,
                        "edge_index": edge.edge_index,
                        "direction": edge.direction,
                        "matched_wall_id": edge.matched_wall_id,
                        "reason": edge.verification_reason or "no_matching_wall",
                    })

        is_consistent = len(mismatched_pairs) == 0
        return BidirectionalVerificationReport(
            is_consistent=is_consistent,
            verified_pairs=verified_pairs,
            mismatched_pairs=mismatched_pairs,
            unattached_boundaries=unattached_boundaries,
            orphaned_walls=orphaned_walls,
        )
