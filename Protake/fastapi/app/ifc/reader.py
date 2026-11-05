"""IFC Reader: Parses raw IFC documents and extracts entities, geometric properties,
materials, and relationships into structured data structures.
"""
from __future__ import annotations

import os
from typing import Any, Optional

import ifcopenshell
import numpy as np

from app.ifc.geometry import (
    extract_opening_geometry_parameters,
    extract_surface_geometry_parameters,
    extract_wall_geometry_parameters,
    get_local_placement_matrix,
    transform_point,
)
from app.ifc.properties import (
    extract_common_wall_attributes,
    extract_material_layers,
    extract_property_sets,
)
from app.ifc.relationships import IFCRelationshipResolver
from app.ifc.validator import IFCValidator, ValidationReport


class IFCReader:
    """High-performance reader for IFC2X3, IFC4, and IFC4X3 building data."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.validator = IFCValidator()
        self.validation_report: Optional[ValidationReport] = None
        self.ifc_file: Optional[ifcopenshell.file] = None
        self.rel_resolver: Optional[IFCRelationshipResolver] = None
        self.unit_scale: float = 1.0

    def parse(self) -> dict[str, Any]:
        """Validates and parses the IFC file into raw structured dictionaries."""
        self.validation_report, self.ifc_file = self.validator.validate_file(self.file_path)
        if not self.validation_report.is_valid or not self.ifc_file:
            raise ValueError(
                f"Cannot parse invalid IFC file: {self.validation_report.status.value}. "
                f"Errors: {[i.message for i in self.validation_report.issues if i.severity.value == 'ERROR']}"
            )

        self.unit_scale = self.validation_report.unit_scale_to_meters
        self.rel_resolver = IFCRelationshipResolver(self.ifc_file)

        project_data = self._extract_project()
        storeys_data = self._extract_storeys()
        spaces_data = self._extract_spaces()
        openings_dict = self._extract_openings_and_fillings()
        walls_data = self._extract_walls(openings_dict)
        slabs_data = self._extract_slabs()
        roofs_data = self._extract_roofs()
        coverings_data = self._extract_coverings()
        columns_data = self._extract_columns()

        return {
            "validation_report": self.validation_report,
            "project": project_data,
            "storeys": storeys_data,
            "spaces": spaces_data,
            "openings": list(openings_dict.values()),
            "walls": walls_data,
            "slabs": slabs_data,
            "roofs": roofs_data,
            "coverings": coverings_data,
            "columns": columns_data,
        }

    def _extract_project(self) -> dict[str, Any]:
        projects = self.ifc_file.by_type("IfcProject")
        project = projects[0] if projects else None
        return {
            "guid": getattr(project, "GlobalId", "PROJECT-ROOT") if project else "PROJECT-ROOT",
            "name": getattr(project, "Name", "Project") if project else "Project",
            "description": getattr(project, "Description", None) if project else None,
            "schema": self.ifc_file.schema,
            "unit_scale_to_meters": self.unit_scale,
            "length_unit": self.validation_report.length_unit,
        }

    def _extract_storeys(self) -> list[dict[str, Any]]:
        storeys: list[dict[str, Any]] = []
        for storey in self.ifc_file.by_type("IfcBuildingStorey"):
            guid = getattr(storey, "GlobalId", "")
            name = getattr(storey, "Name", "Storey")
            elev_val = getattr(storey, "Elevation", None)
            elevation = float(elev_val) * self.unit_scale if elev_val is not None else 0.0
            storeys.append(
                {
                    "guid": guid,
                    "name": name,
                    "elevation": elevation,
                    "description": getattr(storey, "Description", None),
                }
            )

        # If no storeys exist in IFC, provide a default fallback
        if not storeys:
            storeys.append(
                {
                    "guid": "DEFAULT-STOREY-001",
                    "name": "Level 01",
                    "elevation": 0.0,
                    "description": "Default generated storey",
                }
            )
        return storeys

    def _extract_spaces(self) -> list[dict[str, Any]]:
        spaces: list[dict[str, Any]] = []
        for space in self.ifc_file.by_type("IfcSpace"):
            guid = getattr(space, "GlobalId", "")
            name = getattr(space, "Name", "Space")
            long_name = getattr(space, "LongName", None)
            storey_guid = self.rel_resolver.get_storey_for_element(guid)

            psets = extract_property_sets(space)
            
            # Check standard and custom QTO psets
            net_floor_area = None
            gross_floor_area = None
            height = None
            perimeter = None

            for pset_name, props in psets.items():
                p_lower = pset_name.lower()
                if "basequantities" in p_lower or "qto" in p_lower or "dimension" in p_lower or "data" in p_lower or "common" in p_lower:
                    if net_floor_area is None:
                        net_floor_area = props.get("NetFloorArea") or props.get("Net Area") or props.get("NetArea") or props.get("Area") or props.get("FloorArea")
                    if gross_floor_area is None:
                        gross_floor_area = props.get("GrossFloorArea") or props.get("Gross Area") or props.get("GrossArea")
                    if height is None:
                        height = props.get("Height") or props.get("CeilingHeight") or props.get("ClearHeight")
                    if perimeter is None:
                        perimeter = props.get("Perimeter") or props.get("GrossPerimeter")

            # Extract surface geometry parameters
            geo = extract_surface_geometry_parameters(space, self.unit_scale)
            bounded_elems = self.rel_resolver.get_boundaries_for_space(guid)

            def _scale_area(val: Optional[Any]) -> float:
                if val is None:
                    return geo["area"]
                fval = float(val)
                if self.unit_scale < 0.01 and fval > 10000:
                    return fval * (self.unit_scale**2)
                return fval

            spaces.append(
                {
                    "guid": guid,
                    "name": name,
                    "long_name": long_name,
                    "storey_guid": storey_guid,
                    "net_floor_area": _scale_area(net_floor_area),
                    "gross_floor_area": _scale_area(gross_floor_area),
                    "height": float(height) * self.unit_scale if height is not None else 0.0,
                    "perimeter": float(perimeter) * self.unit_scale if (perimeter is not None and float(perimeter) > 1000 and self.unit_scale < 0.01) else (float(perimeter) if perimeter is not None else 0.0),
                    "bbox": geo["bbox"],
                    "geometry_area": geo["area"],
                    "vertices": geo["vertices"],
                    "transform_matrix": geo["transform_matrix"],
                    "bounded_element_guids": bounded_elems,
                    "psets": psets,
                }
            )
        return spaces

    def _extract_openings_and_fillings(self) -> dict[str, dict[str, Any]]:
        openings: dict[str, dict[str, Any]] = {}

        # 1. Openings with Geometry and QTO extraction
        for opening in self.ifc_file.by_type("IfcOpeningElement"):
            guid = getattr(opening, "GlobalId", "")
            name = getattr(opening, "Name", None) or "Opening"
            filling_guid = self.rel_resolver.get_filling_for_opening(guid)

            geo_params = extract_opening_geometry_parameters(opening, self.unit_scale)
            psets = extract_property_sets(opening)
            base_qto = psets.get("Qto_OpeningElementBaseQuantities", {})
            
            qto_w = float(base_qto["Width"]) * self.unit_scale if "Width" in base_qto else None
            qto_h = float(base_qto["Height"]) * self.unit_scale if "Height" in base_qto else None
            qto_a = float(base_qto["Area"]) * (self.unit_scale**2) if "Area" in base_qto else None

            geo_w = geo_params["width"] if geo_params["width"] > 0 else None
            geo_h = geo_params["height"] if geo_params["height"] > 0 else None

            effective_w = geo_w or qto_w or 0.0
            effective_h = geo_h or qto_h or 0.0
            effective_a = qto_a or (effective_w * effective_h)

            openings[guid] = {
                "guid": guid,
                "name": name,
                "opening_type": "GENERIC_VOID",
                "filling_guid": filling_guid,
                "width": effective_w,
                "height": effective_h,
                "area": effective_a,
                "geometry_width": geo_w,
                "geometry_height": geo_h,
                "qto_width": qto_w,
                "qto_height": qto_h,
                "filling_width": None,
                "filling_height": None,
                "transform_matrix": geo_params["transform_matrix"],
                "psets": psets,
            }

        # 2. Enrich with Doors
        for door in self.ifc_file.by_type("IfcDoor"):
            door_guid = getattr(door, "GlobalId", "")
            name = getattr(door, "Name", None) or "Door"
            overall_height = getattr(door, "OverallHeight", None)
            overall_width = getattr(door, "OverallWidth", None)

            h = float(overall_height) * self.unit_scale if overall_height else 2.1336  # default 7ft
            w = float(overall_width) * self.unit_scale if overall_width else 0.9144   # default 3ft

            matched_opening_guid = None
            for o_guid, o_data in openings.items():
                if o_data.get("filling_guid") == door_guid:
                    matched_opening_guid = o_guid
                    break

            if matched_opening_guid:
                openings[matched_opening_guid]["opening_type"] = "DOOR"
                openings[matched_opening_guid]["door_name"] = name
                openings[matched_opening_guid]["filling_width"] = w
                openings[matched_opening_guid]["filling_height"] = h
                if openings[matched_opening_guid]["width"] == 0:
                    openings[matched_opening_guid]["width"] = w
                if openings[matched_opening_guid]["height"] == 0:
                    openings[matched_opening_guid]["height"] = h
                if openings[matched_opening_guid]["area"] == 0:
                    openings[matched_opening_guid]["area"] = openings[matched_opening_guid]["width"] * openings[matched_opening_guid]["height"]
            else:
                openings[door_guid] = {
                    "guid": door_guid,
                    "name": name,
                    "opening_type": "DOOR",
                    "filling_guid": door_guid,
                    "width": w,
                    "height": h,
                    "area": w * h,
                    "geometry_width": None,
                    "geometry_height": None,
                    "qto_width": None,
                    "qto_height": None,
                    "filling_width": w,
                    "filling_height": h,
                    "psets": extract_property_sets(door),
                }

        # 3. Enrich with Windows
        for window in self.ifc_file.by_type("IfcWindow"):
            win_guid = getattr(window, "GlobalId", "")
            name = getattr(window, "Name", None) or "Window"
            overall_height = getattr(window, "OverallHeight", None)
            overall_width = getattr(window, "OverallWidth", None)

            h = float(overall_height) * self.unit_scale if overall_height else 1.2192  # default 4ft
            w = float(overall_width) * self.unit_scale if overall_width else 1.2192   # default 4ft

            matched_opening_guid = None
            for o_guid, o_data in openings.items():
                if o_data.get("filling_guid") == win_guid:
                    matched_opening_guid = o_guid
                    break

            if matched_opening_guid:
                openings[matched_opening_guid]["opening_type"] = "WINDOW"
                openings[matched_opening_guid]["window_name"] = name
                openings[matched_opening_guid]["filling_width"] = w
                openings[matched_opening_guid]["filling_height"] = h
                if openings[matched_opening_guid]["width"] == 0:
                    openings[matched_opening_guid]["width"] = w
                if openings[matched_opening_guid]["height"] == 0:
                    openings[matched_opening_guid]["height"] = h
                if openings[matched_opening_guid]["area"] == 0:
                    openings[matched_opening_guid]["area"] = openings[matched_opening_guid]["width"] * openings[matched_opening_guid]["height"]
            else:
                openings[win_guid] = {
                    "guid": win_guid,
                    "name": name,
                    "opening_type": "WINDOW",
                    "filling_guid": win_guid,
                    "width": w,
                    "height": h,
                    "area": w * h,
                    "geometry_width": None,
                    "geometry_height": None,
                    "qto_width": None,
                    "qto_height": None,
                    "filling_width": w,
                    "filling_height": h,
                    "psets": extract_property_sets(window),
                }

        # Keep openings that have area, filling, or a valid wall relationship
        # GENERIC_VOID with area=0 and no filling is dropped only if it has no wall relationship
        walled_opening_guids: set[str] = set()
        for rel in self.ifc_file.by_type("IfcRelVoidsElement"):
            oe = getattr(rel, "RelatedOpeningElement", None)
            if oe:
                walled_opening_guids.add(getattr(oe, "GlobalId", ""))
        valid_openings = {
            og: odata
            for og, odata in openings.items()
            if (
                odata.get("area", 0) > 0.0
                or odata.get("opening_type") in ["DOOR", "WINDOW"]
                or og in walled_opening_guids
            )
        }
        return valid_openings

    def _extract_walls(self, openings_dict: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        walls: list[dict[str, Any]] = []

        for wall in self.ifc_file.by_type("IfcWall"):
            guid = getattr(wall, "GlobalId", "")
            name = getattr(wall, "Name", None) or "Wall"
            tag = getattr(wall, "Tag", None)
            storey_guid = self.rel_resolver.get_storey_for_element(guid) or "DEFAULT-STOREY-001"

            # Geometry & Parameters
            geo = extract_wall_geometry_parameters(wall, self.unit_scale)
            psets = extract_property_sets(wall)
            attrs = extract_common_wall_attributes(psets, self.unit_scale)
            mat_layers = extract_material_layers(wall, self.unit_scale)

            # Reconcile geometry with Qto quantities (fallback priority)
            length = attrs["qto_length"] or geo["length"] or 0.0
            thickness = attrs["qto_thickness"] or geo["thickness"] or 0.1524  # default 6 in
            height = attrs["qto_height"] or geo["height"] or 3.048  # default 10 ft

            start_point = geo["start_point"]
            end_point = geo["end_point"]

            # If Qto_WallBaseQuantities provided length but geo was zero-length, re-project end_point
            if length > 0 and (geo["length"] == 0 or start_point == end_point):
                placement_matrix = np.array(geo["transform_matrix"])
                start_local = (0.0, 0.0, 0.0)
                local_len = length / self.unit_scale if self.unit_scale > 0 else length
                end_local = (local_len, 0.0, 0.0)
                start_world = transform_point(start_local, placement_matrix)
                start_point = (start_world[0] * self.unit_scale, start_world[1] * self.unit_scale, start_world[2] * self.unit_scale)
                end_world = transform_point(end_local, placement_matrix)
                end_point = (end_world[0] * self.unit_scale, end_world[1] * self.unit_scale, end_world[2] * self.unit_scale)

            # Openings hosted by this wall (only valid openings), with position derived from IFC placement
            opening_guids = self.rel_resolver.get_openings_for_wall(guid)
            raw_wall_openings: list[dict[str, Any]] = []
            for og in opening_guids:
                if og not in openings_dict:
                    continue
                raw_op = dict(openings_dict[og])  # shallow copy
                # Derive position along wall from opening's IFC placement matrix
                tm = raw_op.get("transform_matrix")
                if tm is not None and start_point != end_point:
                    try:
                        mat = np.array(tm)
                        op_world = mat[0:3, 3] * self.unit_scale  # world pos in meters
                        ws = np.array(start_point)
                        we = np.array(end_point)
                        wall_vec = we - ws
                        wall_len = float(np.linalg.norm(wall_vec))
                        if wall_len > 1e-6:
                            proj = float(np.dot(op_world - ws, wall_vec) / wall_len)
                            raw_op["position_along_wall"] = max(0.0, min(proj, wall_len))
                            raw_op["sill_height"] = float(op_world[2])
                    except Exception:
                        pass
                raw_wall_openings.append(raw_op)
            wall_openings = raw_wall_openings

            # Adjacent rooms
            adjacent_spaces = self.rel_resolver.get_adjacent_spaces_for_wall(guid)

            walls.append(
                {
                    "guid": guid,
                    "name": name,
                    "tag": tag,
                    "storey_guid": storey_guid,
                    "length": length,
                    "thickness": thickness,
                    "height": height,
                    "start_point": start_point,
                    "end_point": end_point,
                    "transform_matrix": geo["transform_matrix"],
                    "is_external": attrs["is_external"],
                    "is_load_bearing": attrs["is_load_bearing"],
                    "fire_rating": attrs["fire_rating"],
                    "acoustic_rating": attrs["acoustic_rating"],
                    "qto_gross_area": attrs["qto_gross_area"],
                    "qto_net_area": attrs["qto_net_area"],
                    "material_layers": mat_layers,
                    "openings": wall_openings,
                    "adjacent_spaces": adjacent_spaces,
                    "psets": psets,
                }
            )

        return walls

    def _extract_slabs(self) -> list[dict[str, Any]]:
        slabs: list[dict[str, Any]] = []
        for slab in self.ifc_file.by_type("IfcSlab"):
            guid = getattr(slab, "GlobalId", "")
            name = getattr(slab, "Name", "Slab")
            predefined_type = getattr(slab, "PredefinedType", "FLOOR")
            storey_guid = self.rel_resolver.get_storey_for_element(guid) or "DEFAULT-STOREY-001"
            psets = extract_property_sets(slab)
            base_qto = psets.get("Qto_SlabBaseQuantities", {}) or psets.get("BaseQuantities", {})
            mat_layers = extract_material_layers(slab, self.unit_scale)
            
            is_roof = str(predefined_type).upper() == "ROOF" or "roof" in name.lower()
            geo = extract_surface_geometry_parameters(slab, self.unit_scale)
            bounded_spaces = self.rel_resolver.get_bounded_spaces_for_element(guid)

            slab_gross_area = base_qto.get("GrossArea") or base_qto.get("NetArea")
            if slab_gross_area is not None and float(slab_gross_area) > 0:
                raw_slab_area = float(slab_gross_area)
                slab_area = raw_slab_area * (self.unit_scale**2) if (self.unit_scale < 0.01 and raw_slab_area > 10000) else raw_slab_area
            else:
                slab_area = geo["area"]

            slabs.append(
                {
                    "guid": guid,
                    "name": name,
                    "storey_guid": storey_guid,
                    "predefined_type": str(predefined_type),
                    "is_roof": is_roof,
                    "area": slab_area,
                    "perimeter": float(base_qto.get("Perimeter", 0.0)) * self.unit_scale if base_qto.get("Perimeter") else 0.0,
                    "thickness": float(base_qto.get("Thickness", 0.0)) * self.unit_scale if base_qto.get("Thickness") else 0.1524,
                    "material_layers": mat_layers,
                    "bbox": geo["bbox"],
                    "geometry_area": geo["area"],
                    "geometry_surface_area_3d": geo.get("surface_area_3d", 0.0),
                    "vertices": geo["vertices"],
                    "faces": geo.get("faces", []),
                    "transform_matrix": geo["transform_matrix"],
                    "bounded_space_guids": bounded_spaces,
                    "psets": psets,
                }
            )
        return slabs

    def _extract_roofs(self) -> list[dict[str, Any]]:
        roofs: list[dict[str, Any]] = []
        seen_guids: set[str] = set()
        for roof in self.ifc_file.by_type("IfcRoof"):
            if getattr(roof, "GlobalId", "") in seen_guids:
                continue
            seen_guids.add(getattr(roof, "GlobalId", ""))
            guid = getattr(roof, "GlobalId", "")
            name = getattr(roof, "Name", "Roof")
            predefined_type = getattr(roof, "PredefinedType", "GABLE_ROOF")
            storey_guid = self.rel_resolver.get_storey_for_element(guid) or "DEFAULT-STOREY-001"
            psets = extract_property_sets(roof)
            base_qto = psets.get("Qto_RoofBaseQuantities", {})
            mat_layers = extract_material_layers(roof, self.unit_scale)
            geo = extract_surface_geometry_parameters(roof, self.unit_scale)
            # Aggregate geometry from ALL decomposed children (ArchiCAD uses IfcSlab children)
            if hasattr(roof, "IsDecomposedBy"):
                for rel in getattr(roof, "IsDecomposedBy", []):
                    for child in getattr(rel, "RelatedObjects", []):
                        child_geo = extract_surface_geometry_parameters(child, self.unit_scale)
                        if child_geo.get("vertices"):
                            if not geo.get("vertices"):
                                geo = child_geo
                            else:
                                # Merge: accumulate vertices/faces and sum areas
                                vert_offset = len(geo["vertices"])
                                geo["vertices"] = geo.get("vertices", []) + child_geo.get("vertices", [])
                                geo["faces"] = geo.get("faces", []) + [
                                    [f[0] + vert_offset, f[1] + vert_offset, f[2] + vert_offset]
                                    for f in child_geo.get("faces", [])
                                ]
                                geo["area"] = geo.get("area", 0.0) + child_geo.get("area", 0.0)
                                geo["surface_area_3d"] = geo.get("surface_area_3d", 0.0) + child_geo.get("surface_area_3d", 0.0)

            roofs.append(
                {
                    "guid": guid,
                    "name": name,
                    "storey_guid": storey_guid,
                    "predefined_type": str(predefined_type) if predefined_type else "UNKNOWN",
                    "gross_area": float(base_qto.get("GrossArea", 0.0)) * (self.unit_scale**2) if base_qto.get("GrossArea") else geo["area"],
                    "projected_area": float(base_qto.get("ProjectedArea", 0.0)) * (self.unit_scale**2) if base_qto.get("ProjectedArea") else geo["area"],
                    "geometry_surface_area_3d": geo.get("surface_area_3d", 0.0),
                    "material_layers": mat_layers,
                    "bbox": geo["bbox"],
                    "geometry_area": geo["area"],
                    "vertices": geo["vertices"],
                    "faces": geo.get("faces", []),
                    "transform_matrix": geo["transform_matrix"],
                    "psets": psets,
                }
            )
        return roofs

    def _extract_coverings(self) -> list[dict[str, Any]]:
        coverings: list[dict[str, Any]] = []
        for cov in self.ifc_file.by_type("IfcCovering"):
            guid = getattr(cov, "GlobalId", "")
            name = getattr(cov, "Name", "Covering")
            predefined_type = getattr(cov, "PredefinedType", "FLOORING")
            storey_guid = self.rel_resolver.get_storey_for_element(guid) or "DEFAULT-STOREY-001"
            psets = extract_property_sets(cov)
            base_qto = psets.get("Qto_CoveringBaseQuantities", {}) or psets.get("BaseQuantities", {})
            mat_layers = extract_material_layers(cov, self.unit_scale)
            geo = extract_surface_geometry_parameters(cov, self.unit_scale)
            bounded_spaces = self.rel_resolver.get_bounded_spaces_for_element(guid)

            cov_gross_area = base_qto.get("GrossArea") or base_qto.get("NetArea")
            if cov_gross_area is not None and float(cov_gross_area) > 0:
                raw_cov_area = float(cov_gross_area)
                cov_area = raw_cov_area * (self.unit_scale**2) if (self.unit_scale < 0.01 and raw_cov_area > 10000) else raw_cov_area
            else:
                cov_area = geo["area"]

            coverings.append(
                {
                    "guid": guid,
                    "name": name,
                    "storey_guid": storey_guid,
                    "predefined_type": str(predefined_type),
                    "area": cov_area,
                    "material_layers": mat_layers,
                    "bbox": geo["bbox"],
                    "geometry_area": geo["area"],
                    "vertices": geo["vertices"],
                    "transform_matrix": geo["transform_matrix"],
                    "bounded_space_guids": bounded_spaces,
                    "psets": psets,
                }
            )
        return coverings

    def _extract_columns(self) -> list[dict[str, Any]]:
        columns: list[dict[str, Any]] = []
        for col in self.ifc_file.by_type("IfcColumn"):
            guid = getattr(col, "GlobalId", "")
            name = getattr(col, "Name", "Column")
            storey_guid = self.rel_resolver.get_storey_for_element(guid) or "DEFAULT-STOREY-001"
            columns.append(
                {
                    "guid": guid,
                    "name": name,
                    "storey_guid": storey_guid,
                    "psets": extract_property_sets(col),
                }
            )
        return columns
