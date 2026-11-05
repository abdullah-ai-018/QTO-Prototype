"""Graph representation of wall segments (NetworkX): nodes are snapped
endpoints, edges are wall segments. Used for adjacency queries and to
rasterize a clean wall mask for room flood-fill detection.
"""

import networkx as nx

from app.geometry.line_extraction import Segment
from app.geometry.polygon_ops import wall_orientation_by_topology

NODE_SNAP_PX = 4.0

# Minimum "closeness" to the building envelope's own edge (1.0 = on the
# edge, 0.0 = dead center) a topology "exterior" verdict must clear before
# it's trusted. Without this gate, "exterior" fires whenever one probed
# side has no room polygon at all -- which is correct when that side is
# genuinely outside the building, but indistinguishable, with topology
# alone, from a real interior wall whose *neighboring room was never
# detected*. Measured on a real vector-layer floor plan (36472-1, 12 rooms
# for 182 walls -- weak room recall): of 75 disagreements between topology
# and the old bbox-margin signal, ALL 75 were topology claiming "exterior"
# where bbox-margin said "interior" -- a one-directional bias, not the mixed
# disagreement pattern a genuine signal improvement would produce. Median
# edge-closeness of those disagreements was 0.635, with values as low as
# 0.231 (dead center of the envelope) -- not remotely close to a real
# perimeter wall. Only 11 of the 75 sat at >=0.85, consistent with genuine
# footprint-edge walls bbox-margin's narrow 3% proximity band was missing.
# 0.7 was chosen by sweeping 0.6/0.7/0.8 against that same data: all three
# preserve every one of the 11 genuine near-edge cases (0 lost), so the
# choice isn't a separability question -- it's how much margin to leave
# below the observed genuine cluster (min 0.85) before the untested 0.8-0.85
# band, where these 75 disagreements provide zero ground truth either way.
EXTERIOR_TOPOLOGY_EDGE_CLOSENESS_THRESHOLD = 0.7


def snap_coord(value: float, grid: float = NODE_SNAP_PX) -> float:
    return round(value / grid) * grid


def segment_nodes(seg: Segment) -> tuple[tuple[float, float], tuple[float, float]]:
    return (
        (snap_coord(seg.x1), snap_coord(seg.y1)),
        (snap_coord(seg.x2), snap_coord(seg.y2)),
    )


def build_wall_graph(segments: list[Segment]) -> nx.Graph:
    graph = nx.Graph()
    for seg in segments:
        n1, n2 = segment_nodes(seg)
        if n1 == n2:
            continue
        graph.add_node(n1)
        graph.add_node(n2)
        graph.add_edge(n1, n2, length=seg.length, segment=seg)
    return graph


def segment_is_connected(graph: nx.Graph, seg: Segment) -> bool:
    """True if either endpoint of `seg` meets another wall segment in the
    graph — i.e. this segment is part of a real wall chain/corner rather
    than an isolated line the Hough transform happened to pick up.
    """
    n1, n2 = segment_nodes(seg)
    return graph.degree(n1) >= 2 or graph.degree(n2) >= 2


def connected_wall_clusters(graph: nx.Graph) -> list[list[Segment]]:
    """Group wall segments by connected component — useful for isolating
    independent structures (e.g. separate buildings) on one sheet.
    """
    clusters: list[list[Segment]] = []
    for component in nx.connected_components(graph):
        subgraph = graph.subgraph(component)
        clusters.append([data["segment"] for _, _, data in subgraph.edges(data=True)])
    return clusters


def wall_confidence(length_ft: float, is_connected: bool, linked_room_index: int | None, exterior: bool) -> float:
    """Deterministic plausibility score for a detected wall segment — not a
    fixed placeholder. This is the closest thing to a "wall validator" the
    geometry engine can offer without a construction-specific object model
    (generic COCO-pretrained YOLO has no "wall" class to check against, so
    AI validation can't do this): a wall that connects to the rest of the
    wall graph at at least one endpoint, borders a detected room or the
    page's outer edge, and has a plausible length is trustworthy; an
    isolated, short, unlinked segment is far more likely dimension-witness
    lines, hatching, or furniture caught by the Hough transform.
    """
    score = 0.95
    if length_ft < 2.0:
        score -= 0.35
    elif length_ft < 4.0:
        score -= 0.15
    if not is_connected:
        score -= 0.30
    if linked_room_index is None and not exterior:
        score -= 0.25
    return round(max(0.15, min(0.98, score)), 2)


def wall_segments_bbox(segments: list[Segment]) -> tuple[float, float, float, float] | None:
    """Bounding box (min_x, min_y, max_x, max_y) of every wall segment —
    the actual building footprint's extent, as opposed to the full page's
    pixel dimensions (which include title blocks, dimension strings, and
    whatever margin the drafter left around the plan). See
    is_exterior_segment for why this distinction matters.
    """
    if not segments:
        return None
    xs = [x for seg in segments for x in (seg.x1, seg.x2)]
    ys = [y for seg in segments for y in (seg.y1, seg.y2)]
    return min(xs), min(ys), max(xs), max(ys)


def is_exterior_segment(
    seg: Segment,
    image_w: int,
    image_h: int,
    border_ratio: float = 0.03,
    envelope_bbox: tuple[float, float, float, float] | None = None,
) -> bool:
    """A wall is treated as an exterior wall when it runs close to and
    parallel with the outer bounding box of the building footprint — a
    solid deterministic proxy in the absence of explicit exterior-wall
    symbology.

    `envelope_bbox`, when given, should be the wall segments' own bounding
    box (see wall_segments_bbox) rather than the page's raw pixel
    dimensions. A real sheet almost never has the building footprint
    touching the page edges — there's a title block, a dimension string, or
    just drafting margin around it — so measuring the border against
    `image_w`/`image_h` directly classified every wall as interior on any
    plan with real margin, silently zeroing out the exterior-wall takeoff.
    Falls back to the page bounds when no envelope is available (e.g. a
    single-segment caller with no broader context).
    """
    if envelope_bbox is not None:
        min_x, min_y, max_x, max_y = envelope_bbox
    else:
        min_x, min_y, max_x, max_y = 0.0, 0.0, float(image_w), float(image_h)

    margin_x = (max_x - min_x) * border_ratio
    margin_y = (max_y - min_y) * border_ratio
    near_left = seg.x1 < min_x + margin_x and seg.x2 < min_x + margin_x
    near_right = seg.x1 > max_x - margin_x and seg.x2 > max_x - margin_x
    near_top = seg.y1 < min_y + margin_y and seg.y2 < min_y + margin_y
    near_bottom = seg.y1 > max_y - margin_y and seg.y2 > max_y - margin_y
    return near_left or near_right or near_top or near_bottom


def _envelope_edge_closeness(
    seg: Segment, envelope_bbox: tuple[float, float, float, float]
) -> float:
    """How close this segment's midpoint is to the building envelope's own
    edge, as a fraction of the envelope's half-width/half-height (1.0 = on
    the edge, 0.0 = dead center). Whichever axis is closer to that edge is
    used, since a wall running mostly parallel to one envelope side is
    judged against that side's proximity, not the other axis'.
    """
    min_x, min_y, max_x, max_y = envelope_bbox
    cx, cy = (seg.x1 + seg.x2) / 2.0, (seg.y1 + seg.y2) / 2.0
    half_w = max(1e-6, (max_x - min_x) / 2.0)
    half_h = max(1e-6, (max_y - min_y) / 2.0)
    env_cx, env_cy = (min_x + max_x) / 2.0, (min_y + max_y) / 2.0
    dx_frac = abs(cx - env_cx) / half_w
    dy_frac = abs(cy - env_cy) / half_h
    return max(dx_frac, dy_frac)


def classify_wall_orientation(
    seg: Segment,
    image_w: int,
    image_h: int,
    room_shapely_polys: list,
    wall_distance_px,
    envelope_bbox: tuple[float, float, float, float] | None = None,
    border_ratio: float = 0.03,
) -> tuple[bool, list[str]]:
    """Exterior/interior decision for one wall segment — signal priority
    chain: topology first, bbox-margin proximity (is_exterior_segment) as
    the fallback for whatever topology can't decide.

    Topology (wall_orientation_by_topology) wins whenever it reaches a
    definite answer, because it tests the actual room polygons on each
    side of the wall rather than proximity to the footprint's bounding
    box — the bbox proxy misclassifies on any non-rectangular footprint
    (L-shaped, courtyard) where an interior wall can sit as close to the
    bbox edge as a real exterior one does.

    Falls back to is_exterior_segment when topology is "inconclusive"
    (most commonly: room detection missed the room on one side, so
    neither side resolves to a room polygon) so a wall is never left
    unclassified just because topology couldn't decide.

    "same_room_both_sides" — the same room polygon found on both
    probed sides, which a genuine dividing wall should never produce —
    is treated as not-exterior (matches its likely origin as an interior
    partition/false-positive segment, not a footprint boundary) but the
    reason is preserved in the returned reasons list so it stays visible
    for review rather than silently folding into an ordinary "interior"
    result.

    A topology "exterior" verdict is additionally gated against the
    building envelope before being trusted (see
    EXTERIOR_TOPOLOGY_EDGE_CLOSENESS_THRESHOLD's docstring for the measured
    false-positive rate this closes) — "one side has a room, the other
    doesn't" is only real evidence of an exterior wall when that empty side
    is actually near the building's own perimeter. When it isn't, the
    verdict is downgraded to "inconclusive" and falls through to the
    bbox-margin signal below rather than being trusted at face value. The
    "interior" branch needs no such gate: it requires two *different*,
    positively-identified rooms on both sides, so it can't be fooled by a
    room simply going undetected the way the single-sided "exterior" case can.

    Layer-name (the highest-confidence signal when a clean, consistently
    labelled DWG layer like A-WALL-EXTR/A-WALL-INTR is available) and
    thickness clustering are not wired in yet — both are designed to slot
    in ahead of topology in this same chain without changing this
    function's fallback behavior for pages where they're unavailable.
    """
    orientation, reasons = wall_orientation_by_topology(seg, room_shapely_polys, wall_distance_px)

    if orientation == "exterior":
        near_edge = (
            envelope_bbox is not None
            and _envelope_edge_closeness(seg, envelope_bbox) >= EXTERIOR_TOPOLOGY_EDGE_CLOSENESS_THRESHOLD
        )
        if near_edge:
            return True, reasons
        orientation = "inconclusive"
        reasons = reasons + ["topology_exterior_rejected_not_near_envelope_edge"]

    if orientation in ("interior", "same_room_both_sides"):
        return False, reasons

    fallback_exterior = is_exterior_segment(seg, image_w, image_h, border_ratio=border_ratio, envelope_bbox=envelope_bbox)
    return fallback_exterior, reasons + ["bbox_margin_fallback"]
