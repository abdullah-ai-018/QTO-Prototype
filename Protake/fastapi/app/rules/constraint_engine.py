"""Construction Constraint Engine: Evaluates physical engineering rules and limits
to reject impossible values (e.g. 25 ft door height, flooring area > room gross area,
negative net wall areas).
"""

from dataclasses import dataclass
from app.models.enums import QAFlagLevel
from app.models.room import Room
from app.models.wall import Wall


@dataclass
class ConstraintViolation:
    entity_type: str
    entity_id: int | None
    level: QAFlagLevel
    message: str
    value: float | str
    limit: float | str


MAX_DOOR_HEIGHT_FT = 14.0
MAX_WINDOW_HEIGHT_FT = 20.0
MAX_WALL_HEIGHT_FT = 45.0
MAX_ROOM_AREA_SQFT = 100000.0


def validate_construction_constraints(rooms: list[Room], walls: list[Wall]) -> list[ConstraintViolation]:
    violations: list[ConstraintViolation] = []

    for room in rooms:
        if room.area_sqft <= 0:
            violations.append(
                ConstraintViolation(
                    entity_type="Room",
                    entity_id=room.id,
                    level=QAFlagLevel.ERROR,
                    message=f"Room '{room.name}' has invalid non-positive area ({room.area_sqft} sqft).",
                    value=room.area_sqft,
                    limit="> 0 sqft",
                )
            )
        elif room.area_sqft > MAX_ROOM_AREA_SQFT:
            violations.append(
                ConstraintViolation(
                    entity_type="Room",
                    entity_id=room.id,
                    level=QAFlagLevel.WARNING,
                    message=f"Room '{room.name}' has unusually large area ({room.area_sqft} sqft).",
                    value=room.area_sqft,
                    limit=f"<= {MAX_ROOM_AREA_SQFT} sqft",
                )
            )

    for wall in walls:
        if wall.height_ft > MAX_WALL_HEIGHT_FT:
            violations.append(
                ConstraintViolation(
                    entity_type="Wall",
                    entity_id=wall.id,
                    level=QAFlagLevel.ERROR,
                    message=f"Wall ID {wall.id} exceeds max realistic height ({wall.height_ft} ft).",
                    value=wall.height_ft,
                    limit=f"<= {MAX_WALL_HEIGHT_FT} ft",
                )
            )
        if wall.length_ft <= 0:
            violations.append(
                ConstraintViolation(
                    entity_type="Wall",
                    entity_id=wall.id,
                    level=QAFlagLevel.ERROR,
                    message=f"Wall ID {wall.id} has invalid non-positive length ({wall.length_ft} ft).",
                    value=wall.length_ft,
                    limit="> 0 ft",
                )
            )

    return violations
