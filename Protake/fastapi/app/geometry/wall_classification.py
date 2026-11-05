"""Canonical Wall Classification Engine.

Single source of truth resolving every wall to exactly one of nine
categories: INTERIOR_PARTITION, EXTERIOR_PERIMETER, STRUCTURAL_BEARING,
STAIR_CORE, CORRIDOR, WET_CORE, DEMISING, SHAFT, NEEDS_REVIEW.

This exists because the previous pipeline computed a binary
interior/exterior classification (app/trades/drywall_semantic.py) while a
*separate*, unconsumed function (app/geometry/wall_entity_reconstruction.py)
computed richer categories into an orphaned field (wall_type_code) that
nothing downstream ever read. DEMISING/SHAFT/WET_CORE/CORRIDOR had zero
writers anywhere. This module is the single place that now produces the
real, evidence-backed category — every result carries its evidence so the
UI/assistant can show exactly why a wall was classified the way it was.

Every branch below requires genuine supporting evidence (room-graph
topology, a vector-geometry signal from wall reconstruction, an actual room
name extracted from the drawing, or explicit wall-tag/schedule text) before
committing to a specific category. When the available evidence is
insufficient or ambiguous, the result is NEEDS_REVIEW — never a keyword
guess promoted to a confident category, and never a silent default to
INTERIOR_PARTITION.
"""

from dataclasses import dataclass, field
from typing import Any

CANONICAL_CATEGORIES = (
    "INTERIOR_PARTITION",
    "EXTERIOR_PERIMETER",
    "STRUCTURAL_BEARING",
    "STAIR_CORE",
    "CORRIDOR",
    "WET_CORE",
    "DEMISING",
    "SHAFT",
    "NEEDS_REVIEW",
)

# Real-evidence keyword sets. These are only ever matched against text that
# was genuinely extracted from the drawing set (a Room.name populated from
# OCR/native-text near the room polygon, or a resolved wall tag/assembly
# description) — never invented, never applied without a room/tag match.
# Real-evidence keyword sets. These are only ever matched against text that
# was genuinely extracted from the drawing set (a Room.name populated from
# OCR/native-text near the room polygon, or a resolved wall tag/assembly
# description) — never invented, never applied without a room/tag match.
_STRUCTURAL_TEXT_KEYWORDS = (
    "STRUCTURAL", "BEARING", "LOAD BEARING", "LOAD-BEARING", "CMU", "MASONRY", "CONCRETE", "REINFORCED",
)
_EXTERIOR_TEXT_KEYWORDS = (
    "EXTERIOR", "PERIMETER", "CURTAIN WALL", "FACADE", "ENVELOPE", "OUTSIDE", "EXT-", "EW-", "EW1", "EW2", "EW3", "EW4",
)
_SHAFT_TEXT_KEYWORDS = (
    "SHAFT", "CHASE", "RISER", "DUCT CHASE", "MECH CHASE", "ELEC CHASE", "ELEVATOR CHASE", "ELEVATOR SHAFT", "SHAFTWALL", "SHAFT-WALL",
)
_WET_CORE_TEXT_KEYWORDS = (
    "WET WALL", "PLUMBING WALL", "WET CHASE", "PLUMBING CHASE", "RESTROOM WALL", "BATHROOM WALL",
)
_WET_CORE_ROOM_KEYWORDS = (
    "BATH", "TOILET", "RESTROOM", "WASHROOM", "WC", "SHOWER", "JANITOR", "MOP",
    "KITCHEN", "KITCHENETTE", "LAUNDRY", "HAMMAM", "SAUNA", "STEAM",
)
_SHAFT_ROOM_KEYWORDS = (
    "SHAFT", "CHASE", "RISER", "DUCT SHAFT", "PIPE CHASE", "ELEVATOR SHAFT", "SHAFTWALL",
)
_STAIR_TEXT_KEYWORDS = (
    "STAIR ENCLOSURE", "STAIR TOWER", "STAIR SHAFT", "STAIRWELL WALL", "FIRE STAIR",
)
_STAIR_ROOM_KEYWORDS = ("STAIR", "STAIRWELL", "STAIRWAY", "STAIRCASE", "EXIT STAIR")
_CORRIDOR_TEXT_KEYWORDS = (
    "CORRIDOR WALL", "HALLWAY WALL", "CORRIDOR PARTITION", "EGRESS CORRIDOR", "PUBLIC CORRIDOR",
)
_CORRIDOR_ROOM_KEYWORDS = ("CORRIDOR", "HALLWAY", "HALL", "CIRCULATION", "PASSAGE", "AISLE", "LOBBY", "VESTIBULE", "FOYER")
_DEMISING_TEXT_KEYWORDS = (
    "DEMISING", "TENANT SEPARATION", "UNIT SEPARATION", "PARTY WALL",
    "SUITE SEPARATION", "TENANT DEMISING",
)
_UTILITY_ROOM_KEYWORDS = (
    "MECH", "ELEC", "ELECTRICAL", "MECHANICAL", "SERVER", "TELECOM", "IT CLOSET", "UTILITY", "STORAGE", "CLOSET",
)


@dataclass
class WallClassificationResult:
    category: str
    confidence: float
    reasons: list[str] = field(default_factory=list)
    source_sheet: str | None = None
    source_text: str | None = None
    method: str = "topology"

    def __post_init__(self) -> None:
        if self.category not in CANONICAL_CATEGORIES:
            raise ValueError(f"Invalid canonical wall category: {self.category!r}")


def _room_names(room_graph: Any, room_ids: list[int]) -> list[str]:
    names: list[str] = []
    graph = getattr(room_graph, "graph", None)
    if graph is None:
        return names
    for rid in room_ids:
        node = graph.nodes.get(rid) if hasattr(graph, "nodes") else None
        nm = node.get("name") if node else None
        if nm:
            names.append(str(nm).upper())
    return names


def _match_any(names: list[str], keywords: tuple[str, ...]) -> str | None:
    for nm in names:
        for kw in keywords:
            if kw in nm:
                return nm
    return None


def classify_wall_canonical(
    *,
    classification_str: str,
    class_reason: str,
    room_ids: list[int],
    adjacent_room_ids: list[int],
    room_graph: Any,
    wall_type_code: str | None,
    wall_tag: str | None,
    tag_description: str | None,
    source_sheet: str | None,
) -> WallClassificationResult:
    """Resolves a wall's canonical category from real, already-computed
    evidence — never re-derives geometry or invents a signal.
    """
    reasons: list[str] = [f"topology:{class_reason}"]
    all_room_names = _room_names(room_graph, list(room_ids) + list(adjacent_room_ids))
    tag_text = f"{wall_tag or ''} {tag_description or ''}".upper()

    # 1. Structural / Bearing — CAD layer-name or explicit schedule/tag notation
    if wall_type_code == "STRUCTURAL_BEARING_WALL":
        return WallClassificationResult(
            "STRUCTURAL_BEARING", 0.85,
            reasons + ["cad_layer_name_matches_structural_or_bearing"],
            source_sheet, None, "vector_layer_name",
        )
    if any(kw in tag_text for kw in _STRUCTURAL_TEXT_KEYWORDS):
        return WallClassificationResult(
            "STRUCTURAL_BEARING", 0.85,
            reasons + [f"wall_tag_or_schedule_text_indicates_structural:{wall_tag or tag_description}"],
            source_sheet, tag_description, "wall_tag_schedule_text",
        )

    # 2. Exterior Perimeter — envelope bounding, CAD layer, or explicit exterior tag
    if classification_str == "exterior":
        conf = 0.90
        reasons.append("wall_bounds_conditioned_room_on_outer_building_envelope")
        if wall_type_code == "EXTERIOR_PERIMETER_WALL":
            conf = 0.95
            reasons.append("vector_reconstruction_confirms_exterior_perimeter")
        return WallClassificationResult(
            "EXTERIOR_PERIMETER", conf, reasons, source_sheet, None, "topology+vector_evidence",
        )
    if wall_type_code == "EXTERIOR_PERIMETER_WALL":
        return WallClassificationResult(
            "EXTERIOR_PERIMETER", 0.85,
            reasons + ["cad_layer_or_vector_reconstruction_indicates_exterior_perimeter"],
            source_sheet, None, "vector_reconstruction",
        )
    if any(kw in tag_text for kw in _EXTERIOR_TEXT_KEYWORDS):
        return WallClassificationResult(
            "EXTERIOR_PERIMETER", 0.85,
            reasons + [f"wall_tag_or_schedule_text_indicates_exterior:{wall_tag or tag_description}"],
            source_sheet, tag_description, "wall_tag_schedule_text",
        )

    # 3. Shaft — schedule/tag text or explicit chase/shaft/riser/elevator room polygon
    if any(kw in tag_text for kw in _SHAFT_TEXT_KEYWORDS):
        return WallClassificationResult(
            "SHAFT", 0.85,
            reasons + [f"wall_tag_or_schedule_text_indicates_shaft:{wall_tag or tag_description}"],
            source_sheet, tag_description, "wall_tag_schedule_text",
        )
    shaft_room = _match_any(all_room_names, _SHAFT_ROOM_KEYWORDS)
    if shaft_room and len(room_ids) >= 1 and class_reason in ("separates_two_interior_rooms", "bounds_single_interior_room"):
        return WallClassificationResult(
            "SHAFT", 0.80,
            reasons + [f"adjacent_vertical_shaft_or_chase:{shaft_room}"],
            source_sheet, shaft_room, "room_topology+room_name",
        )

    # 4. Demising — explicit tenant/unit-separation language in tag or schedule
    if any(kw in tag_text for kw in _DEMISING_TEXT_KEYWORDS):
        return WallClassificationResult(
            "DEMISING", 0.85,
            reasons + [f"wall_tag_or_schedule_text_indicates_demising:{wall_tag or tag_description}"],
            source_sheet, tag_description, "wall_tag_schedule_text",
        )

    # 5. Stair Core — stair-cavity vector geometry, tag text, or adjacent stair room boundary
    stair_room = _match_any(all_room_names, _STAIR_ROOM_KEYWORDS)
    if wall_type_code == "STAIR_CORE_WALL" and stair_room:
        return WallClassificationResult(
            "STAIR_CORE", 0.92,
            reasons + ["stair_cavity_vector_geometry", f"adjacent_room_named:{stair_room}"],
            source_sheet, stair_room, "vector_geometry+room_name",
        )
    if any(kw in tag_text for kw in _STAIR_TEXT_KEYWORDS):
        return WallClassificationResult(
            "STAIR_CORE", 0.88,
            reasons + [f"wall_tag_or_schedule_text_indicates_stair:{wall_tag or tag_description}"],
            source_sheet, tag_description, "wall_tag_schedule_text",
        )
    if wall_type_code == "STAIR_CORE_WALL":
        return WallClassificationResult(
            "STAIR_CORE", 0.75,
            reasons + ["stair_cavity_vector_geometry"],
            source_sheet, None, "vector_geometry",
        )
    if stair_room and len(room_ids) >= 1 and class_reason in ("separates_two_interior_rooms", "bounds_single_interior_room"):
        return WallClassificationResult(
            "STAIR_CORE", 0.75,
            reasons + [f"adjacent_room_named:{stair_room}"],
            source_sheet, stair_room, "room_topology+room_name",
        )

    # 6. Wet Core — schedule/tag text or adjacent room explicitly named a plumbing/wet space
    if any(kw in tag_text for kw in _WET_CORE_TEXT_KEYWORDS):
        return WallClassificationResult(
            "WET_CORE", 0.85,
            reasons + [f"wall_tag_or_schedule_text_indicates_wet_core:{wall_tag or tag_description}"],
            source_sheet, tag_description, "wall_tag_schedule_text",
        )
    wet_room = _match_any(all_room_names, _WET_CORE_ROOM_KEYWORDS)
    if wet_room and len(room_ids) >= 1 and class_reason in ("separates_two_interior_rooms", "bounds_single_interior_room"):
        return WallClassificationResult(
            "WET_CORE", 0.80,
            reasons + [f"adjacent_room_named:{wet_room}"],
            source_sheet, wet_room, "room_topology+room_name",
        )

    # 7. Corridor — schedule/tag text or adjacent corridor room
    if any(kw in tag_text for kw in _CORRIDOR_TEXT_KEYWORDS):
        return WallClassificationResult(
            "CORRIDOR", 0.85,
            reasons + [f"wall_tag_or_schedule_text_indicates_corridor:{wall_tag or tag_description}"],
            source_sheet, tag_description, "wall_tag_schedule_text",
        )
    corridor_room = _match_any(all_room_names, _CORRIDOR_ROOM_KEYWORDS)
    if class_reason in ("interior_corridor_or_room_partition", "internal_circulation_partition", "separates_two_interior_rooms") and corridor_room:
        return WallClassificationResult(
            "CORRIDOR", 0.75,
            reasons + [f"adjacent_room_named:{corridor_room}"],
            source_sheet, corridor_room, "topology+room_name",
        )

    # 8. Plain interior partition / Utility space partition — separating offices, suites,
    #    utility/mech/elec rooms, or internal circulation partition inside the floor plan.
    if classification_str == "interior":
        if len(room_ids) >= 2 or class_reason == "separates_two_interior_rooms":
            conf = 0.85 if wall_type_code in ("INTERIOR_PARTITION", None) else 0.80
            return WallClassificationResult(
                "INTERIOR_PARTITION", conf,
                reasons + ["separates_two_distinct_interior_rooms"],
                source_sheet, None, "topology",
            )
        elif len(room_ids) == 1 or class_reason == "interior_corridor_or_room_partition":
            return WallClassificationResult(
                "INTERIOR_PARTITION", 0.75,
                reasons + ["bounds_single_interior_room_no_more_specific_evidence"],
                source_sheet, None, "topology",
            )
        elif class_reason == "internal_circulation_partition":
            return WallClassificationResult(
                "INTERIOR_PARTITION", 0.75,
                reasons + ["internal_circulation_partition_inside_conditioned_envelope"],
                source_sheet, None, "topology",
            )



    # 9. Everything else (unconditioned/ambiguous topology, zero resolved
    #    room boundary, no tag/CAD-layer signal) — genuinely insufficient
    #    evidence to commit to a category.
    return WallClassificationResult(
        "NEEDS_REVIEW", 0.40,
        reasons + ["insufficient_room_boundary_or_tag_evidence_for_confident_classification"],
        source_sheet, None, "insufficient_evidence",
    )
