"""Building Graph: Provides graph-based topological indexing and relationship queries
across canonical BIM entities.
"""
from __future__ import annotations

from typing import Optional
from app.bim.models import (
    CanonicalBIMModel,
    CanonicalOpening,
    CanonicalSpace,
    CanonicalStorey,
    CanonicalWall,
)


class BuildingGraph:
    """In-memory spatial and topological relationship graph for a Canonical BIM Model."""

    def __init__(self, model: CanonicalBIMModel):
        self.model = model
        self._walls_by_id: dict[str, CanonicalWall] = {w.id: w for w in model.walls}
        self._spaces_by_id: dict[str, CanonicalSpace] = {s.id: s for s in model.spaces}
        self._storeys_by_id: dict[str, CanonicalStorey] = {s.id: s for s in model.storeys}
        self._openings_by_id: dict[str, CanonicalOpening] = {o.id: o for o in model.openings}

        # Secondary indexes
        self._walls_by_storey: dict[str, list[CanonicalWall]] = {}
        self._spaces_by_storey: dict[str, list[CanonicalSpace]] = {}
        self._walls_by_space: dict[str, list[CanonicalWall]] = {}

        self._build_indexes()

    def _build_indexes(self) -> None:
        for wall in self.model.walls:
            self._walls_by_storey.setdefault(wall.storey_id, []).append(wall)
            for space_id in wall.adjacent_space_ids:
                self._walls_by_space.setdefault(space_id, []).append(wall)

        for space in self.model.spaces:
            self._spaces_by_storey.setdefault(space.storey_id, []).append(space)

    def get_wall(self, wall_id_or_guid: str) -> Optional[CanonicalWall]:
        return self._walls_by_id.get(wall_id_or_guid)

    def get_space(self, space_id_or_guid: str) -> Optional[CanonicalSpace]:
        return self._spaces_by_id.get(space_id_or_guid)

    def get_storey(self, storey_id_or_guid: str) -> Optional[CanonicalStorey]:
        return self._storeys_by_id.get(storey_id_or_guid)

    def get_walls_in_storey(self, storey_id: str) -> list[CanonicalWall]:
        return self._walls_by_storey.get(storey_id, [])

    def get_spaces_in_storey(self, storey_id: str) -> list[CanonicalSpace]:
        return self._spaces_by_storey.get(storey_id, [])

    def get_walls_bounding_space(self, space_id: str) -> list[CanonicalWall]:
        return self._walls_by_space.get(space_id, [])

    def get_openings_for_wall(self, wall_id: str) -> list[CanonicalOpening]:
        wall = self.get_wall(wall_id)
        return wall.openings if wall else []
