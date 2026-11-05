"""IFC Relationship Resolution:
Resolves spatial hierarchy, wall-to-opening voids, opening-to-door/window fillings,
and space boundary connections.
"""
from __future__ import annotations

from typing import Any, Optional
import ifcopenshell


class IFCRelationshipResolver:
    """Extracts and indexes graph relationships between IFC elements."""

    def __init__(self, ifc_file: ifcopenshell.file):
        self.ifc_file = ifc_file
        self._element_to_storey: dict[str, str] = {}  # element_guid -> storey_guid
        self._wall_to_openings: dict[str, list[str]] = {}  # wall_guid -> [opening_guid, ...]
        self._opening_to_filling: dict[str, str] = {}  # opening_guid -> door/window_guid
        self._space_to_bounding_walls: dict[str, list[str]] = {}  # space_guid -> [wall_guid, ...]
        self._wall_to_adjacent_spaces: dict[str, list[str]] = {}  # wall_guid -> [space_guid, ...]

        self._build_indexes()

    def _build_indexes(self) -> None:
        """Parses relational entities from the IFC model."""
        # 1. Spatial Containment (IfcRelContainedInSpatialStructure & IfcRelAggregates)
        for rel in self.ifc_file.by_type("IfcRelContainedInSpatialStructure"):
            spatial_elem = getattr(rel, "RelatingStructure", None)
            if not spatial_elem:
                continue
            spatial_guid = getattr(spatial_elem, "GlobalId", None)
            for elem in getattr(rel, "RelatedElements", []):
                elem_guid = getattr(elem, "GlobalId", None)
                if elem_guid and spatial_guid:
                    self._element_to_storey[elem_guid] = spatial_guid

        for rel in self.ifc_file.by_type("IfcRelAggregates"):
            relating_obj = getattr(rel, "RelatingObject", None)
            if not relating_obj:
                continue
            relating_guid = getattr(relating_obj, "GlobalId", None)
            for obj in getattr(rel, "RelatedObjects", []):
                obj_guid = getattr(obj, "GlobalId", None)
                if obj_guid and relating_guid:
                    self._element_to_storey[obj_guid] = relating_guid

        # 2. Voids Elements (IfcRelVoidsElement: Wall -> Opening)
        for rel in self.ifc_file.by_type("IfcRelVoidsElement"):
            building_elem = getattr(rel, "RelatingBuildingElement", None)
            opening_elem = getattr(rel, "RelatedOpeningElement", None)
            if building_elem and opening_elem:
                b_guid = getattr(building_elem, "GlobalId", None)
                o_guid = getattr(opening_elem, "GlobalId", None)
                if b_guid and o_guid:
                    self._wall_to_openings.setdefault(b_guid, []).append(o_guid)

        # 2b. Inverse fallback: scan IfcOpeningElement.VoidsElements for exporters
        # that write inverse attributes but may omit IfcRelVoidsElement in the forward scan
        for opening in self.ifc_file.by_type("IfcOpeningElement"):
            o_guid = getattr(opening, "GlobalId", None)
            if not o_guid:
                continue
            voids_rels = getattr(opening, "VoidsElements", None) or []
            for rel in voids_rels:
                building_elem = getattr(rel, "RelatingBuildingElement", None)
                if building_elem:
                    b_guid = getattr(building_elem, "GlobalId", None)
                    if b_guid and o_guid not in self._wall_to_openings.get(b_guid, []):
                        self._wall_to_openings.setdefault(b_guid, []).append(o_guid)

        # 3. Fills Elements (IfcRelFillsElement: Opening -> Door / Window)
        for rel in self.ifc_file.by_type("IfcRelFillsElement"):
            opening_elem = getattr(rel, "RelatingOpeningElement", None)
            filling_elem = getattr(rel, "RelatedBuildingElement", None)
            if opening_elem and filling_elem:
                o_guid = getattr(opening_elem, "GlobalId", None)
                f_guid = getattr(filling_elem, "GlobalId", None)
                if o_guid and f_guid:
                    self._opening_to_filling[o_guid] = f_guid

        # 4. Space Boundaries (IfcRelSpaceBoundary: Space <-> Wall / Slab)
        for rel in self.ifc_file.by_type("IfcRelSpaceBoundary"):
            space = getattr(rel, "RelatingSpace", None)
            boundary_elem = getattr(rel, "RelatedBuildingElement", None)
            if space and boundary_elem:
                s_guid = getattr(space, "GlobalId", None)
                b_guid = getattr(boundary_elem, "GlobalId", None)
                if s_guid and b_guid:
                    self._space_to_bounding_walls.setdefault(s_guid, []).append(b_guid)
                    self._wall_to_adjacent_spaces.setdefault(b_guid, []).append(s_guid)

    def get_storey_for_element(self, element_guid: str) -> Optional[str]:
        """Returns the GUID of the storey containing the element."""
        return self._element_to_storey.get(element_guid)

    def get_openings_for_wall(self, wall_guid: str) -> list[str]:
        """Returns the list of opening GUIDs hosted by this wall."""
        return self._wall_to_openings.get(wall_guid, [])

    def get_filling_for_opening(self, opening_guid: str) -> Optional[str]:
        """Returns the GUID of the door or window filling the opening."""
        return self._opening_to_filling.get(opening_guid)

    def get_adjacent_spaces_for_wall(self, wall_guid: str) -> list[str]:
        """Returns the list of space GUIDs adjacent to this wall."""
        return list(set(self._wall_to_adjacent_spaces.get(wall_guid, [])))

    def get_boundaries_for_space(self, space_guid: str) -> list[str]:
        """Returns the list of building element GUIDs bounding this space."""
        return list(set(self._space_to_bounding_walls.get(space_guid, [])))

    def get_bounded_spaces_for_element(self, element_guid: str) -> list[str]:
        """Returns the list of space GUIDs bounded by this element."""
        return list(set(self._wall_to_adjacent_spaces.get(element_guid, [])))

