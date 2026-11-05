"""Cross-validates OCR text against the geometry engine's output:
room-name labels are assigned to the geometry room whose polygon
contains them; dimension labels are checked against the nearest wall's
computed length and flagged when they disagree beyond tolerance.

OCR never creates or resizes geometry here — it only labels and
flags it for human review, per the "AI validates, never calculates" rule.
"""

from dataclasses import dataclass

from shapely.geometry import Point

from app.geometry.engine import GeometryResult
from app.ocr.parsers import DimensionLabel, RoomLabel

DIMENSION_TOLERANCE_PCT = 5.0  # Ultra-strict 5% tolerance for zero-error civil estimation


@dataclass
class OcrValidationResult:
    room_name_overrides: dict[int, str]  # room index -> OCR-confirmed name
    dimension_flags: list[dict]  # mismatches between OCR text and geometry


def assign_room_names(
    rooms_px_polygons, room_labels: list[RoomLabel], distance_tolerance_px: float = 30.0
) -> dict[int, str]:
    """For each OCR room-name token, find which geometry room polygon
    contains its centroid and use that as the confirmed room name.
    Merges multi-token room labels (e.g. MASTER + BEDROOM -> Master Bedroom).

    `distance_tolerance_px` should scale with the page (see validate()) — a
    fixed 30px is generous on a small raster but tiny on a 2000px+ sheet,
    where a label sitting just outside a small room's watershed-derived
    boundary (a closet, a hall, a powder room) misses the room entirely and
    falls back to a generic "Room N" name.
    """
    labels_by_room: dict[int, list[RoomLabel]] = {}
    for label in room_labels:
        point = Point(label.centroid_px)
        for idx, polygon in enumerate(rooms_px_polygons):
            if polygon.contains(point) or polygon.distance(point) < distance_tolerance_px:
                labels_by_room.setdefault(idx, []).append(label)
                break

    overrides: dict[int, str] = {}
    for idx, labels in labels_by_room.items():
        # Sort labels by y-coordinate then x-coordinate to construct natural reading order
        sorted_labels = sorted(labels, key=lambda l: (round(l.centroid_px[1] / 20.0), l.centroid_px[0]))
        words = []
        for l in sorted_labels:
            txt = l.text.strip().title()
            if txt and txt not in words:
                words.append(txt)
        if words:
            overrides[idx] = " ".join(words)
    return overrides


def flag_dimension_mismatches(
    walls: list[dict],
    dimension_labels: list[DimensionLabel],
    scale_ft_per_px: float,
    image_w: int,
    image_h: int,
    proximity_px: float = 60.0,
) -> list[dict]:
    """Compare each OCR'd dimension string against the nearest wall's
    geometry-computed length; flag disagreements beyond tolerance for
    human review rather than silently trusting either source.
    """
    flags: list[dict] = []
    for dim in dimension_labels:
        if dim.feet is None:
            continue

        nearest_wall = None
        nearest_distance = float("inf")
        for wall in walls:
            mid_x = (wall["start_norm"]["x"] + wall["end_norm"]["x"]) / 2 * image_w
            mid_y = (wall["start_norm"]["y"] + wall["end_norm"]["y"]) / 2 * image_h
            distance = ((mid_x - dim.centroid_px[0]) ** 2 + (mid_y - dim.centroid_px[1]) ** 2) ** 0.5
            if distance < nearest_distance:
                nearest_distance = distance
                nearest_wall = wall

        if nearest_wall is None or nearest_distance > proximity_px:
            continue

        computed_length = nearest_wall["length_ft"]
        if computed_length <= 0:
            continue
        deviation_pct = abs(computed_length - dim.feet) / computed_length * 100
        if deviation_pct > DIMENSION_TOLERANCE_PCT:
            flags.append(
                {
                    "ocr_text": dim.text,
                    "ocr_feet": dim.feet,
                    "geometry_feet": computed_length,
                    "deviation_pct": round(deviation_pct, 1),
                    "location_px": dim.centroid_px,
                }
            )
    return flags


def validate(geometry: GeometryResult, classified_tokens: dict, scale_ft_per_px: float, image_w: int, image_h: int) -> OcrValidationResult:
    rooms_px_polygons = []
    for room in geometry.rooms:
        pts = [(p[0] * image_w, p[1] * image_h) for p in room.polygon_norm]
        from shapely.geometry import Polygon

        rooms_px_polygons.append(Polygon(pts))

    # ~1.5% of the page's long edge — generous enough to catch a label
    # sitting just outside a small room's boundary, small enough that it
    # still won't reach into a genuinely different, non-adjacent room.
    name_match_tolerance_px = max(30.0, max(image_w, image_h) * 0.015)
    room_overrides = assign_room_names(rooms_px_polygons, classified_tokens["rooms"], name_match_tolerance_px)

    walls_as_dicts = [
        {"start_norm": w.start_norm, "end_norm": w.end_norm, "length_ft": w.length_ft} for w in geometry.walls
    ]
    dimension_flags = flag_dimension_mismatches(
        walls_as_dicts, classified_tokens["dimensions"], scale_ft_per_px, image_w, image_h
    )

    return OcrValidationResult(room_name_overrides=room_overrides, dimension_flags=dimension_flags)
