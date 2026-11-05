"""Drawing Registration Engine: Aligns Floor Plan wall segments with Elevation sheet wall
projections using 2D coordinate transformation & bounding box projection matching.
"""

from dataclasses import dataclass
from app.models.wall import Wall


@dataclass
class WallRegistrationMatch:
    floor_wall_id: int
    elevation_wall_id: int
    alignment_score: float  # 0.0 to 1.0


def register_floor_and_elevation_walls(
    floor_walls: list[Wall], elevation_walls: list[Wall]
) -> list[WallRegistrationMatch]:
    """Matches floor plan walls to corresponding elevation walls based on x-span alignment."""
    matches: list[WallRegistrationMatch] = []

    for f_wall in floor_walls:
        f_min_x = min(f_wall.start_norm["x"], f_wall.end_norm["x"])
        f_max_x = max(f_wall.start_norm["x"], f_wall.end_norm["x"])
        f_len_x = abs(f_max_x - f_min_x)

        best_match_id = None
        best_score = 0.0

        for e_wall in elevation_walls:
            e_min_x = min(e_wall.start_norm["x"], e_wall.end_norm["x"])
            e_max_x = max(e_wall.start_norm["x"], e_wall.end_norm["x"])
            e_len_x = abs(e_max_x - e_min_x)

            # Calculate horizontal overlap score
            overlap_min = max(f_min_x, e_min_x)
            overlap_max = min(f_max_x, e_max_x)
            overlap_len = max(0.0, overlap_max - overlap_min)

            if f_len_x > 0 and e_len_x > 0:
                score = overlap_len / max(f_len_x, e_len_x)
                if score > 0.60 and score > best_score:
                    best_score = score
                    best_match_id = e_wall.id

        if best_match_id is not None:
            matches.append(
                WallRegistrationMatch(
                    floor_wall_id=f_wall.id,
                    elevation_wall_id=best_match_id,
                    alignment_score=round(best_score, 2),
                )
            )

    return matches
