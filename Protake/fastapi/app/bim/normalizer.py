"""BIM Normalizer: Transforms raw extracted IFC entities into canonical, unit-normalized BIM objects
with strict Model Health Cards and QTO Eligibility Gates.
"""
from __future__ import annotations

import math
import re
import numpy as np
from typing import Any, Optional

from app.bim.models import (
    CanonicalBIMModel,
    CanonicalBuilding,
    CanonicalColumn,
    CanonicalOpening,
    CanonicalProject,
    CanonicalRoof,
    CanonicalSlab,
    CanonicalSpace,
    CanonicalStorey,
    CanonicalWall,
    DataProvenanceStatus,
    FlooringAssembly,
    FlooringType,
    MaterialLayer,
    ModelHealthCard,
    QTOEligibilityStatus,
    QTOReadiness,
    WallAssembly,
)

METERS_TO_FEET = 3.280839895013123
METERS_TO_INCHES = 39.37007874015748
SQ_METERS_TO_SQFT = 10.763910416709722


class BIMNormalizer:
    """Normalizes raw IFC data structures into strongly-typed Canonical BIM domain models."""

    def normalize(self, raw_data: dict[str, Any]) -> CanonicalBIMModel:
        """Executes full normalization on raw parsed IFC dictionary."""
        raw_project = raw_data.get("project", {})
        raw_storeys = raw_data.get("storeys", [])
        raw_spaces = raw_data.get("spaces", [])
        raw_openings = raw_data.get("openings", [])
        raw_walls = raw_data.get("walls", [])
        raw_slabs = raw_data.get("slabs", [])
        raw_columns = raw_data.get("columns", [])

        storey_lookup: dict[str, dict[str, Any]] = {s["guid"]: s for s in raw_storeys}
        space_lookup: dict[str, dict[str, Any]] = {s["guid"]: s for s in raw_spaces}

        # 1. Normalize Storeys
        canonical_storeys: list[CanonicalStorey] = []
        for s in raw_storeys:
            canonical_storeys.append(
                CanonicalStorey(
                    id=s["guid"],
                    ifc_guid=s["guid"],
                    name=s["name"],
                    elevation_ft=s["elevation"] * METERS_TO_FEET,
                    height_ft=10.0,
                )
            )

        # 2. Normalize Spaces / Rooms
        canonical_spaces: list[CanonicalSpace] = []
        for idx, sp in enumerate(raw_spaces):
            raw_net = sp.get("net_floor_area", 0.0)
            raw_gross = sp.get("gross_floor_area", 0.0)
            raw_perim = sp.get("perimeter", 0.0)
            raw_height = sp.get("height", 0.0)

            net_area = round(raw_net * SQ_METERS_TO_SQFT, 2) if raw_net > 0 else 0.0
            gross_area = round(raw_gross * SQ_METERS_TO_SQFT, 2) if raw_gross > 0 else (net_area if net_area > 0 else 0.0)
            perim = round(raw_perim * METERS_TO_FEET, 2) if raw_perim > 0 else 0.0
            height_ft = round(raw_height * METERS_TO_FEET, 2) if raw_height > 0 else 10.0

            sp_name = sp.get("name", f"Space {idx + 1}")
            
            # Provenance determination: strict verification
            if net_area > 0:
                prov_status = DataProvenanceStatus.VERIFIED_EXPLICIT
            else:
                prov_status = DataProvenanceStatus.UNKNOWN_UNRESOLVED

            flooring_asm = self._resolve_flooring_assembly(sp_name, [])

            canonical_spaces.append(
                CanonicalSpace(
                    id=sp["guid"],
                    ifc_guid=sp["guid"],
                    name=sp_name,
                    long_name=sp.get("long_name"),
                    storey_id=sp.get("storey_guid") or (canonical_storeys[0].id if canonical_storeys else "DEFAULT-STOREY"),
                    net_floor_area_sqft=net_area,
                    gross_floor_area_sqft=gross_area,
                    ceiling_height_ft=height_ft,
                    perimeter_ft=perim,
                    flooring_assembly=flooring_asm,
                    provenance_status=prov_status,
                    source_psets=sp.get("psets", {}),
                )
            )

        # 3. Normalize Openings
        canonical_openings: list[CanonicalOpening] = []
        openings_by_guid: dict[str, CanonicalOpening] = {}
        for op in raw_openings:
            w_ft = op.get("width", 0.0) * METERS_TO_FEET
            h_ft = op.get("height", 0.0) * METERS_TO_FEET
            area_sqft = op.get("area", 0.0) * SQ_METERS_TO_SQFT
            if area_sqft == 0.0 and w_ft > 0 and h_ft > 0:
                area_sqft = w_ft * h_ft

            geo_w = op.get("geometry_width")
            geo_h = op.get("geometry_height")
            qto_w = op.get("qto_width")
            qto_h = op.get("qto_height")
            fill_w = op.get("filling_width")
            fill_h = op.get("filling_height")

            pos_m = op.get("position_along_wall")
            sill_m = op.get("sill_height")
            c_opening = CanonicalOpening(
                id=op["guid"],
                ifc_guid=op["guid"],
                name=op.get("name") or "Opening",
                opening_type=op.get("opening_type", "GENERIC_VOID"),
                width_ft=round(w_ft, 4),
                height_ft=round(h_ft, 4),
                area_sqft=round(area_sqft, 4),
                filling_guid=op.get("filling_guid"),
                geometry_width_ft=round(geo_w * METERS_TO_FEET, 4) if geo_w is not None else None,
                geometry_height_ft=round(geo_h * METERS_TO_FEET, 4) if geo_h is not None else None,
                qto_width_ft=round(qto_w * METERS_TO_FEET, 4) if qto_w is not None else None,
                qto_height_ft=round(qto_h * METERS_TO_FEET, 4) if qto_h is not None else None,
                filling_width_ft=round(fill_w * METERS_TO_FEET, 4) if fill_w is not None else None,
                filling_height_ft=round(fill_h * METERS_TO_FEET, 4) if fill_h is not None else None,
                intersection_area_sqft=round(area_sqft, 4),
                position_along_wall_ft=round(pos_m * METERS_TO_FEET, 4) if pos_m is not None else None,
                sill_height_ft=round(sill_m * METERS_TO_FEET, 4) if sill_m is not None else None,
                provenance_status=DataProvenanceStatus.VERIFIED_EXPLICIT if pos_m is not None else DataProvenanceStatus.UNKNOWN_UNRESOLVED,
                source_properties=op.get("psets", {}),
            )
            canonical_openings.append(c_opening)
            openings_by_guid[op["guid"]] = c_opening

        # 4. Normalize Walls with QTO Eligibility Gate
        canonical_walls: list[CanonicalWall] = []
        walls_with_materials = 0
        walls_with_assemblies = 0

        for w in raw_walls:
            storey_guid = w.get("storey_guid") or (canonical_storeys[0].id if canonical_storeys else "DEFAULT-STOREY")
            storey_name = storey_lookup.get(storey_guid, {}).get("name", "Level 01")

            length_ft = w.get("length", 0.0) * METERS_TO_FEET
            thickness_in = w.get("thickness", 0.1524) * METERS_TO_INCHES
            height_ft = w.get("height", 3.048) * METERS_TO_FEET

            start_m = w.get("start_point", (0.0, 0.0, 0.0))
            end_m = w.get("end_point", (0.0, 0.0, 0.0))
            start_ft = (start_m[0] * METERS_TO_FEET, start_m[1] * METERS_TO_FEET, start_m[2] * METERS_TO_FEET)
            end_ft = (end_m[0] * METERS_TO_FEET, end_m[1] * METERS_TO_FEET, end_m[2] * METERS_TO_FEET)

            # Robust Geometric Length Fallback if raw property is missing
            if length_ft <= 0.001 and (start_m != end_m):
                dx = end_m[0] - start_m[0]
                dy = end_m[1] - start_m[1]
                geom_len = math.sqrt(dx * dx + dy * dy) * METERS_TO_FEET
                if geom_len > 0.0:
                    length_ft = geom_len

            # Check Psets fallback for length if still 0
            if length_ft <= 0.001:
                psets = w.get("psets", {})
                pset_len = (
                    psets.get("Qto_WallBaseQuantities", {}).get("Length")
                    or psets.get("BaseQuantities", {}).get("Length")
                    or psets.get("Dimensions", {}).get("Length")
                )
                if pset_len:
                    length_ft = float(pset_len) * METERS_TO_FEET

            # Material layers
            material_layers: list[MaterialLayer] = []
            for l_raw in w.get("material_layers", []):
                mat_name = (l_raw.get("material_name") or "Unknown Material").strip()
                mat_lower = mat_name.lower()
                is_drywall = any(k in mat_lower for k in ["gypsum", "drywall", "sheetrock", "plasterboard", "gwb"])
                is_stud = any(k in mat_lower for k in ["stud", "metal", "wood stud", "framing", "air", "cavity"])
                is_insul = any(k in mat_lower for k in ["insulation", "batt", "mineral wool", "fiberglass", "sound"])
                is_masonry = any(k in mat_lower for k in ["concrete", "cmu", "brick", "masonry", "block"])

                material_layers.append(
                    MaterialLayer(
                        layer_index=l_raw.get("layer_index", 0),
                        material_name=mat_name,
                        thickness_ft=l_raw.get("thickness", 0.0) * METERS_TO_FEET,
                        is_drywall=is_drywall,
                        is_stud_cavity=is_stud,
                        is_insulation=is_insul,
                        is_masonry_or_concrete=is_masonry,
                        provenance_status=DataProvenanceStatus.VERIFIED_EXPLICIT,
                    )
                )

            if len(material_layers) > 0:
                walls_with_materials += 1

            # Openings for this wall
            wall_openings: list[CanonicalOpening] = []
            for raw_op in w.get("openings", []):
                op_guid = raw_op.get("guid")
                if op_guid in openings_by_guid:
                    base_op = openings_by_guid[op_guid]
                    # Enrich with wall-relative position computed in reader
                    pos_m = raw_op.get("position_along_wall")
                    sill_m = raw_op.get("sill_height")
                    if pos_m is not None or sill_m is not None:
                        new_prov = DataProvenanceStatus.VERIFIED_EXPLICIT if pos_m is not None else base_op.provenance_status
                        base_op = base_op.model_copy(update={
                            "position_along_wall_ft": round(pos_m * METERS_TO_FEET, 4) if pos_m is not None else base_op.position_along_wall_ft,
                            "sill_height_ft": round(sill_m * METERS_TO_FEET, 4) if sill_m is not None else base_op.sill_height_ft,
                            "provenance_status": new_prov,
                        })
                    wall_openings.append(base_op)
                else:
                    w_ft = raw_op.get("width", 0.0) * METERS_TO_FEET
                    h_ft = raw_op.get("height", 0.0) * METERS_TO_FEET
                    pos_m = raw_op.get("position_along_wall")
                    sill_m = raw_op.get("sill_height")
                    wall_openings.append(
                        CanonicalOpening(
                            id=raw_op.get("guid", ""),
                            ifc_guid=raw_op.get("guid", ""),
                            name=raw_op.get("name") or "Opening",
                            opening_type=raw_op.get("opening_type", "GENERIC_VOID"),
                            width_ft=round(w_ft, 4),
                            height_ft=round(h_ft, 4),
                            area_sqft=round(w_ft * h_ft, 4),
                            filling_guid=raw_op.get("filling_guid"),
                            position_along_wall_ft=round(pos_m * METERS_TO_FEET, 4) if pos_m is not None else None,
                            sill_height_ft=round(sill_m * METERS_TO_FEET, 4) if sill_m is not None else None,
                            provenance_status=DataProvenanceStatus.VERIFIED_EXPLICIT if pos_m is not None else DataProvenanceStatus.UNKNOWN_UNRESOLVED,
                        )
                    )

            # Wall Classification & Assembly resolution
            is_external = bool(w.get("is_external", False))
            is_load_bearing = bool(w.get("is_load_bearing", False))
            wall_name_lower = w.get("name", "").lower()

            wall_class = self._classify_wall(wall_name_lower, is_external, is_load_bearing, material_layers)
            assembly = self._resolve_assembly(wall_name_lower, thickness_in, material_layers, w.get("fire_rating"))
            if assembly.assembly_name:
                walls_with_assemblies += 1

            # QTO Eligibility Gate evaluation
            eligibility_status, eligibility_reasons = self._evaluate_eligibility(
                length_ft, height_ft, wall_class, material_layers, w.get("psets", {})
            )

            # Room names from adjacent spaces
            adjacent_space_ids = w.get("adjacent_spaces", [])
            room_a_name = space_lookup.get(adjacent_space_ids[0], {}).get("name") if len(adjacent_space_ids) > 0 else None
            room_b_name = space_lookup.get(adjacent_space_ids[1], {}).get("name") if len(adjacent_space_ids) > 1 else None

            # Provenance resolution
            length_prov = DataProvenanceStatus.VERIFIED_EXPLICIT if w.get("psets", {}).get("Qto_WallBaseQuantities", {}).get("Length") else DataProvenanceStatus.DERIVED_GEOMETRIC
            height_prov = DataProvenanceStatus.VERIFIED_EXPLICIT if w.get("psets", {}).get("Qto_WallBaseQuantities", {}).get("Height") else DataProvenanceStatus.DERIVED_GEOMETRIC

            canonical_walls.append(
                CanonicalWall(
                    id=w["guid"],
                    ifc_guid=w["guid"],
                    name=w.get("name", "Wall"),
                    tag=w.get("tag"),
                    storey_id=storey_guid,
                    storey_name=storey_name,
                    length_ft=round(length_ft, 4),
                    nominal_thickness_in=round(thickness_in, 2),
                    physical_height_ft=round(height_ft, 4),
                    start_point=start_ft,
                    end_point=end_ft,
                    length_provenance=length_prov,
                    height_provenance=height_prov,
                    is_external=is_external,
                    is_load_bearing=is_load_bearing,
                    fire_rating=w.get("fire_rating"),
                    acoustic_rating=w.get("acoustic_rating"),
                    adjacent_space_ids=adjacent_space_ids,
                    room_a_name=room_a_name,
                    room_b_name=room_b_name,
                    openings=wall_openings,
                    material_layers=material_layers,
                    assembly=assembly,
                    wall_classification=wall_class,
                    qto_eligibility=eligibility_status,
                    eligibility_reasons=eligibility_reasons,
                    drywall_scope_eligible=(eligibility_status == QTOEligibilityStatus.ELIGIBLE),
                    drywall_finish_height_ft=round(height_ft, 4),
                    drywall_side_a_scope=True,
                    drywall_side_b_scope=not is_external,
                    source_psets=w.get("psets", {}),
                )
            )

        # 5. Normalize Slabs, Roofs & Columns
        raw_roofs = raw_data.get("roofs", [])
        canonical_slabs: list[CanonicalSlab] = []
        for sl in raw_slabs:
            is_roof = sl.get("is_roof", False)
            sl_name = sl.get("name", "Slab")
            st_guid = sl.get("storey_guid", "")
            st_name = storey_lookup.get(st_guid, {}).get("name", "Level 01")
            area_sqft = round(sl.get("area", 0.0) * SQ_METERS_TO_SQFT, 2)
            perim_ft = round(sl.get("perimeter", 0.0) * METERS_TO_FEET, 2)
            thick_in = round(sl.get("thickness", 0.1524) * METERS_TO_INCHES, 2)

            flooring_asm = None if is_roof else self._resolve_flooring_assembly(sl_name, sl.get("material_layers", []))

            canonical_slabs.append(
                CanonicalSlab(
                    id=sl["guid"],
                    ifc_guid=sl["guid"],
                    name=sl_name,
                    storey_id=st_guid,
                    storey_name=st_name,
                    slab_type="ROOF_SLAB" if is_roof else "FLOOR_SLAB",
                    area_sqft=area_sqft,
                    perimeter_ft=perim_ft,
                    thickness_in=thick_in,
                    is_roof=is_roof,
                    slope_degrees=0.0,
                    pitch_multiplier=1.0,
                    flooring_eligible=not is_roof,
                    flooring_assembly=flooring_asm,
                    source_psets=sl.get("psets", {}),
                )
            )

        canonical_roofs: list[CanonicalRoof] = []

        # Priority 1: Direct IfcRoof elements
        for rf in raw_roofs:
            rf_guid = rf["guid"]
            rf_name = rf.get("name", "Roof")
            st_guid = rf.get("storey_guid", "")
            st_name = storey_lookup.get(st_guid, {}).get("name", "Roof Level")
            g_area = round(rf.get("gross_area", 0.0) * SQ_METERS_TO_SQFT, 2)
            p_area = round(rf.get("projected_area", 0.0) * SQ_METERS_TO_SQFT, 2)
            mat_layers = rf.get("material_layers", [])
            psets = rf.get("psets", {})

            # Slope, Pitch & Provenance
            slope_deg, pitch_str, pitch_mult, slope_prov, rev_reasons = self._resolve_roof_slope_and_pitch(rf)
            roof_type = self._resolve_roof_type(rf, slope_deg)
            mat_str, mat_evidence, mat_prov = self._resolve_roof_material(rf_name, mat_layers, psets)

            # Reconcile true surface area vs plan area
            # Priority 1: actual 3D triangulated surface area from geometry extraction
            geo_surface_3d = round(rf.get("geometry_surface_area_3d", 0.0) * SQ_METERS_TO_SQFT, 2)
            geo_area = round(rf.get("geometry_area", 0.0) * SQ_METERS_TO_SQFT, 2)
            has_verified_ifc_plan = (g_area > 0 or p_area > 0)
            has_verified_slope = slope_prov in (DataProvenanceStatus.VERIFIED_EXPLICIT, DataProvenanceStatus.DERIVED_GEOMETRIC) and slope_deg is not None

            if geo_surface_3d > 0:
                true_area = geo_surface_3d
                plan_area = p_area if p_area > 0 else (g_area if g_area > 0 else geo_area)
                area_prov = DataProvenanceStatus.DERIVED_GEOMETRIC
            elif has_verified_ifc_plan and has_verified_slope and pitch_mult is not None and pitch_mult >= 1.0:
                # Gated Geometric Fallback: Explicitly permitted only when verified IFC plan area AND verified slope exist
                plan_area = p_area if p_area > 0 else g_area
                true_area = round(plan_area * pitch_mult, 2)
                area_prov = DataProvenanceStatus.DERIVED_GEOMETRIC
            elif has_verified_ifc_plan and (slope_deg == 0.0 or pitch_mult == 1.0):
                # Flat roof explicit slope 0: true area == plan area
                plan_area = p_area if p_area > 0 else g_area
                true_area = plan_area
                area_prov = DataProvenanceStatus.VERIFIED_EXPLICIT
            elif geo_area > 0 and has_verified_slope and pitch_mult is not None:
                plan_area = geo_area
                true_area = round(geo_area * pitch_mult, 2)
                area_prov = DataProvenanceStatus.DERIVED_GEOMETRIC
            else:
                # Fallback strictly blocked: No fabricated roofing quantity without verified 3D geometry or verified slope
                plan_area = p_area if p_area > 0 else (g_area if g_area > 0 else geo_area)
                true_area = 0.0
                area_prov = DataProvenanceStatus.UNKNOWN_UNRESOLVED
                rev_reasons.append("TRUE_SURFACE_AREA_CANNOT_BE_DERIVED_WITHOUT_VERIFIED_SLOPE_OR_3D_GEOMETRY")

            if len(rev_reasons) > 0:
                eligibility = QTOEligibilityStatus.REVIEW_REQUIRED
            elif true_area > 0:
                eligibility = QTOEligibilityStatus.ELIGIBLE
            else:
                eligibility = QTOEligibilityStatus.INELIGIBLE_INVALID_GEOMETRY

            raw_verts = rf.get("vertices", [])
            verts_ft = [
                [
                    round(p[0] * METERS_TO_FEET, 3),
                    round(p[1] * METERS_TO_FEET, 3),
                    round(p[2] * METERS_TO_FEET, 3) if len(p) > 2 else 0.0,
                ]
                for p in raw_verts
                if isinstance(p, (list, tuple)) and len(p) >= 2
            ]
            raw_bbox = rf.get("bbox") or {}
            bbox_ft = (
                {
                    "min_x": round(raw_bbox.get("min_x", 0.0) * METERS_TO_FEET, 2),
                    "max_x": round(raw_bbox.get("max_x", 0.0) * METERS_TO_FEET, 2),
                    "min_y": round(raw_bbox.get("min_y", 0.0) * METERS_TO_FEET, 2),
                    "max_y": round(raw_bbox.get("max_y", 0.0) * METERS_TO_FEET, 2),
                    "min_z": round(raw_bbox.get("min_z", 0.0) * METERS_TO_FEET, 2),
                    "max_z": round(raw_bbox.get("max_z", 0.0) * METERS_TO_FEET, 2),
                }
                if raw_bbox
                else None
            )
            elev_ft = bbox_ft["min_z"] if bbox_ft else 20.0

            canonical_roofs.append(
                CanonicalRoof(
                    id=rf_guid,
                    ifc_guid=rf_guid,
                    name=rf_name,
                    source_type="IfcRoof",
                    storey_id=st_guid,
                    storey_name=st_name,
                    roof_type=roof_type,
                    slope_degrees=slope_deg,
                    pitch_ratio=pitch_str,
                    pitch_multiplier=pitch_mult,
                    plan_area_sqft=plan_area,
                    true_surface_area_sqft=true_area,
                    ridge_length_ft=0.0,
                    hip_length_ft=0.0,
                    valley_length_ft=0.0,
                    eave_length_ft=0.0,
                    rake_length_ft=0.0,
                    elevation_ft=elev_ft,
                    vertices=verts_ft,
                    faces=rf.get("faces", []),
                    face_map=rf.get("face_map", []),
                    bbox=bbox_ft,
                    primary_material=mat_str,
                    material_evidence=mat_evidence,
                    material_provenance=mat_prov,
                    slope_provenance=slope_prov,
                    area_provenance=area_prov,
                    qto_eligibility=eligibility,
                    review_reasons=rev_reasons,
                    source_psets=psets,
                )
            )

        # Priority 2: If no explicit IfcRoof entities, promote explicit roof-classified Slabs
        if len(canonical_roofs) == 0:
            for sl in canonical_slabs:
                if sl.is_roof:
                    sl_raw = next((r for r in raw_slabs if r["guid"] == sl.ifc_guid), {})
                    mat_layers = sl_raw.get("material_layers", [])
                    psets = sl_raw.get("psets", {})

                    slope_deg, pitch_str, pitch_mult, slope_prov, rev_reasons = self._resolve_roof_slope_and_pitch(sl_raw)
                    roof_type = self._resolve_roof_type(sl_raw, slope_deg)
                    mat_str, mat_evidence, mat_prov = self._resolve_roof_material(sl.name, mat_layers, psets)

                    geo_surface_3d_sl = round(sl_raw.get("geometry_surface_area_3d", 0.0) * SQ_METERS_TO_SQFT, 2)
                    plan_area = sl.area_sqft
                    has_verified_slope_sl = slope_prov in (DataProvenanceStatus.VERIFIED_EXPLICIT, DataProvenanceStatus.DERIVED_GEOMETRIC) and slope_deg is not None
                    if geo_surface_3d_sl > 0:
                        true_area = geo_surface_3d_sl
                        area_prov = DataProvenanceStatus.DERIVED_GEOMETRIC
                    elif plan_area > 0 and has_verified_slope_sl and pitch_mult is not None and pitch_mult >= 1.0:
                        true_area = round(plan_area * pitch_mult, 2)
                        area_prov = DataProvenanceStatus.DERIVED_GEOMETRIC
                    elif plan_area > 0 and (slope_deg == 0.0 or pitch_mult == 1.0):
                        true_area = plan_area
                        area_prov = DataProvenanceStatus.DERIVED_GEOMETRIC
                    else:
                        true_area = 0.0
                        area_prov = DataProvenanceStatus.UNKNOWN_UNRESOLVED
                        rev_reasons.append("TRUE_SURFACE_AREA_CANNOT_BE_DERIVED_WITHOUT_VERIFIED_SLOPE_OR_3D_GEOMETRY")

                    if len(rev_reasons) > 0:
                        eligibility = QTOEligibilityStatus.REVIEW_REQUIRED
                    elif true_area > 0:
                        eligibility = QTOEligibilityStatus.ELIGIBLE
                    else:
                        eligibility = QTOEligibilityStatus.INELIGIBLE_INVALID_GEOMETRY

                    raw_verts = sl_raw.get("vertices", [])
                    verts_ft = [
                        [
                            round(p[0] * METERS_TO_FEET, 3),
                            round(p[1] * METERS_TO_FEET, 3),
                            round(p[2] * METERS_TO_FEET, 3) if len(p) > 2 else 0.0,
                        ]
                        for p in raw_verts
                        if isinstance(p, (list, tuple)) and len(p) >= 2
                    ]
                    raw_bbox = sl_raw.get("bbox") or {}
                    bbox_ft = (
                        {
                            "min_x": round(raw_bbox.get("min_x", 0.0) * METERS_TO_FEET, 2),
                            "max_x": round(raw_bbox.get("max_x", 0.0) * METERS_TO_FEET, 2),
                            "min_y": round(raw_bbox.get("min_y", 0.0) * METERS_TO_FEET, 2),
                            "max_y": round(raw_bbox.get("max_y", 0.0) * METERS_TO_FEET, 2),
                            "min_z": round(raw_bbox.get("min_z", 0.0) * METERS_TO_FEET, 2),
                            "max_z": round(raw_bbox.get("max_z", 0.0) * METERS_TO_FEET, 2),
                        }
                        if raw_bbox
                        else None
                    )
                    elev_ft = bbox_ft["min_z"] if bbox_ft else 20.0

                    canonical_roofs.append(
                        CanonicalRoof(
                            id=f"ROOF-{sl.ifc_guid}",
                            ifc_guid=sl.ifc_guid,
                            name=f"Roof Assembly ({sl.name})",
                            source_type="IfcSlab",
                            storey_id=sl.storey_id,
                            storey_name=sl.storey_name,
                            roof_type=roof_type,
                            slope_degrees=slope_deg,
                            pitch_ratio=pitch_str,
                            pitch_multiplier=pitch_mult,
                            plan_area_sqft=plan_area,
                            true_surface_area_sqft=true_area,
                            ridge_length_ft=0.0,
                            hip_length_ft=0.0,
                            valley_length_ft=0.0,
                            eave_length_ft=0.0,
                            rake_length_ft=0.0,
                            elevation_ft=elev_ft,
                            vertices=verts_ft,
                            faces=sl_raw.get("faces", []),
                            face_map=sl_raw.get("face_map", []),
                            bbox=bbox_ft,
                            primary_material=mat_str,
                            material_evidence=mat_evidence,
                            material_provenance=mat_prov,
                            slope_provenance=slope_prov,
                            area_provenance=area_prov,
                            qto_eligibility=eligibility,
                            review_reasons=rev_reasons,
                            source_psets=psets,
                        )
                    )


        # 5. Columns Normalization

        canonical_columns: list[CanonicalColumn] = []
        for col in raw_columns:
            canonical_columns.append(
                CanonicalColumn(
                    id=col["guid"],
                    ifc_guid=col["guid"],
                    name=col.get("name", "Column"),
                    storey_id=col.get("storey_guid", ""),
                )
            )

        # 6. Build Canonical Building & Project
        canonical_building = CanonicalBuilding(
            id="BUILDING-001",
            ifc_guid="BUILDING-001",
            name="Main Building",
            storeys=canonical_storeys,
        )

        canonical_project = CanonicalProject(
            id=raw_project.get("guid", "PROJECT-ROOT"),
            ifc_guid=raw_project.get("guid", "PROJECT-ROOT"),
            name=raw_project.get("name", "Project"),
            schema_version=raw_project.get("schema", "IFC4"),
            length_unit=raw_project.get("length_unit", "METRE"),
            buildings=[canonical_building],
        )

        # 7. Compute Model Health Card & Completeness Assessment
        total_walls_count = len(canonical_walls)
        mat_score = (walls_with_materials / total_walls_count) if total_walls_count > 0 else 1.0
        assembly_score = (walls_with_assemblies / total_walls_count) if total_walls_count > 0 else 1.0
        opening_score = 1.0 if len(canonical_openings) > 0 else 0.5
        spatial_score = 1.0 if len(canonical_spaces) > 0 else 0.5

        readiness_notes = []
        if mat_score < 0.5:
            readiness_notes.append(f"Low material layer coverage ({mat_score:.0%}). Assemblies derived from heuristic assumptions.")
        if len(canonical_spaces) == 0:
            readiness_notes.append("No IfcSpace entities detected. Room associations unavailable.")

        eligible_count = sum(1 for w in canonical_walls if w.qto_eligibility == QTOEligibilityStatus.ELIGIBLE)
        readiness = QTOReadiness.READY_FOR_QTO if (eligible_count > 0 or len(canonical_slabs) > 0) and mat_score >= 0.3 else QTOReadiness.REVIEW_REQUIRED

        health_card = ModelHealthCard(
            schema_version=raw_project.get("schema", "IFC4"),
            length_unit=raw_project.get("length_unit", "METRE"),
            unit_scale_to_meters=raw_project.get("unit_scale_to_meters", 1.0),
            total_elements=total_walls_count + len(canonical_openings) + len(canonical_spaces) + len(canonical_slabs) + len(canonical_roofs),
            wall_count=total_walls_count,
            opening_count=len(canonical_openings),
            space_count=len(canonical_spaces),
            storey_count=len(canonical_storeys),
            geometry_coverage_score=1.0,
            material_coverage_score=round(mat_score, 2),
            assembly_coverage_score=round(assembly_score, 2),
            opening_coverage_score=round(opening_score, 2),
            spatial_coverage_score=round(spatial_score, 2),
            readiness=readiness,
            readiness_notes=readiness_notes,
        )

        # 8. Flooring Elements Normalization (Phase 3 Step 2 Canonical Pipeline)
        from app.bim.flooring_normalizer import FlooringNormalizer
        flooring_normalizer = FlooringNormalizer()
        canonical_flooring = flooring_normalizer.normalize(raw_data)

        return CanonicalBIMModel(
            project=canonical_project,
            health_card=health_card,
            storeys=canonical_storeys,
            spaces=canonical_spaces,
            walls=canonical_walls,
            openings=canonical_openings,
            slabs=canonical_slabs,
            roofs=canonical_roofs,
            columns=canonical_columns,
            flooring_elements=canonical_flooring,
        )

    def _evaluate_eligibility(
        self,
        length_ft: float,
        height_ft: float,
        wall_class: str,
        layers: list[MaterialLayer],
        psets: dict[str, Any],
    ) -> tuple[QTOEligibilityStatus, list[str]]:
        """Applies rigorous gate checks to certify whether a wall is safe for automated QTO calculation."""
        reasons: list[str] = []

        if length_ft <= 0.0 or height_ft <= 0.0:
            reasons.append("Invalid or zero analytical geometry dimensions.")
            return QTOEligibilityStatus.INELIGIBLE_INVALID_GEOMETRY, reasons

        if wall_class == "STRUCTURAL_CONCRETE":
            reasons.append("Structural concrete core — standard drywall scope excluded.")
            return QTOEligibilityStatus.INELIGIBLE_NON_DRYWALL, reasons

        if wall_class == "CURTAIN_WALL":
            reasons.append("Curtain wall / exterior glazing system — drywall excluded.")
            return QTOEligibilityStatus.INELIGIBLE_NON_DRYWALL, reasons

        if wall_class == "UNKNOWN":
            reasons.append("Ambiguous wall classification; estimator review required.")
            return QTOEligibilityStatus.REVIEW_REQUIRED, reasons

        return QTOEligibilityStatus.ELIGIBLE, ["ELIGIBLE_FOR_DRYWALL_QTO: Scope verified against classification criteria."]

    def _classify_wall(
        self,
        name: str,
        is_external: bool,
        is_load_bearing: bool,
        layers: list[MaterialLayer],
    ) -> str:
        """Classifies wall role based on geometry, material layers, and Pset attributes."""
        if "curtain" in name or "glazing" in name or "storefront" in name:
            return "CURTAIN_WALL"
        if "shaft" in name:
            return "SHAFT_WALL"
        if "demising" in name or "party" in name or "corridor" in name:
            return "DEMISING_WALL"

        has_concrete = any(
            (l.is_masonry_or_concrete if hasattr(l, "is_masonry_or_concrete") else l.get("is_masonry_or_concrete", False))
            for l in layers
        ) if layers else False
        if (has_concrete or is_load_bearing) and ("concrete" in name or "shear" in name or "structural" in name):
            return "STRUCTURAL_CONCRETE"

        if is_external or "exterior" in name:
            return "EXTERIOR_WALL"

        return "INTERIOR_PARTITION"

    def _resolve_assembly(
        self,
        wall_name: str,
        thickness_in: float,
        layers: Any,
        fire_rating: Optional[str],
    ) -> WallAssembly:
        """Resolves stud framing and drywall specifications with explicit provenance marking."""
        stud_size = '3-5/8"'
        if thickness_in >= 7.0:
            stud_size = '6"'
        elif thickness_in <= 4.0:
            stud_size = '2-1/2"'

        board_type = '5/8" Type X'
        fire_hours = None
        if fire_rating:
            m = re.search(r"(\d+)", str(fire_rating))
            if m:
                val = float(m.group(1))
                fire_hours = val if val <= 4 else val / 60.0

        side_a_layers = 1
        side_b_layers = 1
        if fire_hours and fire_hours >= 2.0:
            side_a_layers = 2
            side_b_layers = 2

        drywall_layers_count = sum(
            1 for l in layers if (l.is_drywall if hasattr(l, "is_drywall") else l.get("is_drywall", False))
        ) if layers else 0
        if drywall_layers_count >= 4:
            side_a_layers = 2
            side_b_layers = 2

        has_insul = any(
            (l.is_insulation if hasattr(l, "is_insulation") else l.get("is_insulation", False))
            for l in layers
        ) if layers else False

        prov = DataProvenanceStatus.VERIFIED_EXPLICIT if (layers and len(layers) > 0) else DataProvenanceStatus.CONFIGURED_ASSUMPTION

        return WallAssembly(
            assembly_name=wall_name or "Standard Stud Partition",
            stud_type="LIGHT_GAUGE_STEEL",
            stud_size=stud_size,
            stud_gauge="25ga",
            stud_spacing_in=16,
            board_type=board_type,
            board_thickness_in=0.625,
            side_a_layers=side_a_layers,
            side_b_layers=side_b_layers,
            has_insulation=has_insul,
            fire_rating_hours=fire_hours,
            assembly_provenance=prov,
        )

    def _resolve_flooring_assembly(
        self,
        element_name: str,
        layers: Any,
    ) -> FlooringAssembly:
        """Resolves flooring materials (Tile, Hardwood, Vinyl, Carpet) from IFC semantics."""
        name_lower = (element_name or "").lower()
        
        extracted_names = []
        if isinstance(layers, list):
            for l in layers:
                if isinstance(l, dict):
                    extracted_names.append(str(l.get("material_name") or "").lower())
                else:
                    extracted_names.append(str(getattr(l, "material_name", "") or "").lower())
        
        mat_names = " ".join(extracted_names)
        combined = f"{name_lower} {mat_names}"

        prov = DataProvenanceStatus.VERIFIED_EXPLICIT if (layers and len(layers) > 0) else DataProvenanceStatus.CONFIGURED_ASSUMPTION

        if any(k in combined for k in ["tile", "porcelain", "ceramic", "bath", "wc", "toilet", "washroom", "restroom"]):
            return FlooringAssembly(
                assembly_name="12x24 Porcelain Floor Tile with Waterproofing",
                flooring_type=FlooringType.PORCELAIN_TILE,
                tile_width_in=12.0,
                tile_length_in=24.0,
                box_coverage_sqft=16.0,
                waste_factor_pct=12.0,
                has_underlayment=False,
                has_waterproofing_membrane=True,
                grout_joint_width_in=0.125,
                baseboard_type='Tile Base Skirting (4" Height)',
                has_baseboard=True,
                adhesive_type="Thinset Mortar (Polymer Modified)",
                assembly_provenance=prov,
            )
        elif any(k in combined for k in ["carpet", "rug", "broadloom"]):
            return FlooringAssembly(
                assembly_name="Commercial Grade Cut-Pile Carpet",
                flooring_type=FlooringType.CARPET,
                box_coverage_sqft=108.0,  # 12 ft roll
                waste_factor_pct=8.0,
                has_underlayment=True,
                underlayment_type="High-Density Carpet Cushion Pad",
                has_waterproofing_membrane=False,
                baseboard_type='4" Vinyl / Rubber Wall Base',
                has_baseboard=True,
                adhesive_type="Carpet Seam Adhesive",
                assembly_provenance=prov,
            )
        elif any(k in combined for k in ["vinyl", "lvt", "plank", "resilient"]):
            return FlooringAssembly(
                assembly_name='Luxury Vinyl Plank (LVP 7"x48")',
                flooring_type=FlooringType.LUXURY_VINYL_PLANK,
                tile_width_in=7.0,
                tile_length_in=48.0,
                box_coverage_sqft=23.8,
                waste_factor_pct=8.0,
                has_underlayment=True,
                underlayment_type="Sound-Absorbing Vapor Barrier",
                has_waterproofing_membrane=False,
                baseboard_type='3-1/4" MDF Primed Baseboard',
                has_baseboard=True,
                adhesive_type="Pressure-Sensitive Adhesive",
                assembly_provenance=prov,
            )
        elif any(k in combined for k in ["epoxy", "garage", "mechanical", "plant"]):
            return FlooringAssembly(
                assembly_name="2-Part High Solids Epoxy Floor Coating",
                flooring_type=FlooringType.EPOXY,
                box_coverage_sqft=200.0,
                waste_factor_pct=5.0,
                has_underlayment=False,
                has_waterproofing_membrane=False,
                baseboard_type="Integral Epoxy Coved Base",
                has_baseboard=True,
                adhesive_type=None,
                assembly_provenance=prov,
            )
        else:
            return FlooringAssembly(
                assembly_name='Engineered White Oak Hardwood 5" Planks',
                flooring_type=FlooringType.ENGINEERED_WOOD,
                tile_width_in=5.0,
                tile_length_in=48.0,
                box_coverage_sqft=22.0,
                waste_factor_pct=10.0,
                has_underlayment=True,
                underlayment_type="2-in-1 Acoustic Moisture Vapor Underlayment",
                has_waterproofing_membrane=False,
                baseboard_type='4-1/4" Colonial MDF Baseboard',
                has_baseboard=True,
                adhesive_type="Urethane Wood Flooring Adhesive",
                assembly_provenance=prov,
            )

    def _resolve_roof_material(
        self, name: str, material_layers: list[dict[str, Any]], psets: dict[str, Any]
    ) -> tuple[str, Optional[str], DataProvenanceStatus]:
        """Resolves roofing primary material strictly from explicit IFC evidence."""
        # 1. Check material layers
        for layer in material_layers:
            mat_name = str(layer.get("material_name", "")).upper()
            if "SHINGLE" in mat_name or "ASPHALT" in mat_name:
                return "ASPHALT_SHINGLE", f"MaterialLayer: {mat_name}", DataProvenanceStatus.VERIFIED_EXPLICIT
            if "MEMBRANE" in mat_name or "EPDM" in mat_name or "TPO" in mat_name or "PVC" in mat_name:
                return "MEMBRANE", f"MaterialLayer: {mat_name}", DataProvenanceStatus.VERIFIED_EXPLICIT
            if "METAL" in mat_name or "STEEL" in mat_name or "ALUMINUM" in mat_name or "COPPER" in mat_name:
                return "METAL", f"MaterialLayer: {mat_name}", DataProvenanceStatus.VERIFIED_EXPLICIT
            if "TILE" in mat_name or "CLAY" in mat_name or "CONCRETE TILE" in mat_name:
                return "TILE", f"MaterialLayer: {mat_name}", DataProvenanceStatus.VERIFIED_EXPLICIT
            if "SLATE" in mat_name:
                return "SLATE", f"MaterialLayer: {mat_name}", DataProvenanceStatus.VERIFIED_EXPLICIT
            if "CONCRETE" in mat_name:
                return "CONCRETE", f"MaterialLayer: {mat_name}", DataProvenanceStatus.VERIFIED_EXPLICIT
            if len(mat_name) > 0:
                return mat_name, f"MaterialLayer: {mat_name}", DataProvenanceStatus.VERIFIED_EXPLICIT

        # 2. Check name / description keywords
        name_upper = str(name).upper()
        if "SHINGLE" in name_upper or "ASPHALT" in name_upper:
            return "ASPHALT_SHINGLE", f"ElementName: {name}", DataProvenanceStatus.DERIVED_GEOMETRIC
        if "MEMBRANE" in name_upper or "EPDM" in name_upper or "TPO" in name_upper or "FLAT_PVG" in name_upper or "MMBPOLY" in name_upper:
            return "MEMBRANE", f"ElementName: {name}", DataProvenanceStatus.DERIVED_GEOMETRIC
        if "METAL" in name_upper or "STEEL" in name_upper or "STANDING SEAM" in name_upper:
            return "METAL", f"ElementName: {name}", DataProvenanceStatus.DERIVED_GEOMETRIC
        if "TILE" in name_upper:
            return "TILE", f"ElementName: {name}", DataProvenanceStatus.DERIVED_GEOMETRIC
        if "SLATE" in name_upper:
            return "SLATE", f"ElementName: {name}", DataProvenanceStatus.DERIVED_GEOMETRIC
        if "CONCRETE" in name_upper:
            return "CONCRETE", f"ElementName: {name}", DataProvenanceStatus.DERIVED_GEOMETRIC

        return "UNASSIGNED", None, DataProvenanceStatus.UNKNOWN_UNRESOLVED

    def _resolve_roof_slope_and_pitch(
        self, rf_data: dict[str, Any]
    ) -> tuple[Optional[float], Optional[str], Optional[float], DataProvenanceStatus, list[str]]:
        """Resolves roof slope, pitch ratio, and pitch multiplier with zero silent defaults."""
        psets = rf_data.get("psets", {})
        review_reasons: list[str] = []

        # 1. Explicit slope in Psets (Pset_RoofCommon, Qto_RoofBaseQuantities, etc.)
        for pset_name, pset_vals in psets.items():
            if isinstance(pset_vals, dict):
                for k, v in pset_vals.items():
                    k_lower = k.lower()
                    if k_lower in ["slope", "roofslope", "pitch", "angle"] and v is not None:
                        try:
                            val = float(v)
                            if val > 0:
                                slope_deg = round(val, 2) if val < 90 else round(math.degrees(val), 2)
                                pitch_val = round(math.tan(math.radians(slope_deg)) * 12.0, 1)
                                mult = round(math.sqrt(1.0 + (pitch_val / 12.0) ** 2), 4)
                                return slope_deg, f"{pitch_val}:12", mult, DataProvenanceStatus.VERIFIED_EXPLICIT, []
                        except (ValueError, TypeError):
                            pass

        # 2. Geometric slope from 3D vertices/faces/normals if available
        verts = rf_data.get("vertices", [])
        faces = rf_data.get("faces", [])
        if faces and len(verts) >= 3:
            try:
                roof_slopes = []
                for f in faces:
                    if len(f) >= 3 and f[0] < len(verts) and f[1] < len(verts) and f[2] < len(verts):
                        p0 = np.array(verts[f[0]][:3])
                        p1 = np.array(verts[f[1]][:3])
                        p2 = np.array(verts[f[2]][:3])
                        cross = np.cross(p1 - p0, p2 - p0)
                        area = 0.5 * float(np.linalg.norm(cross))
                        if area > 1e-5:
                            nz = abs(float(cross[2])) / (2.0 * area)
                            # Exclude vertical edge faces (nz <= 0.05) to isolate the true roof plane slope
                            if nz > 0.05:
                                slope_rad = math.acos(min(1.0, max(0.0, nz)))
                                roof_slopes.append((math.degrees(slope_rad), area))
                if roof_slopes:
                    total_area = sum(s[1] for s in roof_slopes)
                    weighted_slope = sum(s[0] * s[1] for s in roof_slopes) / total_area
                    slope_deg = round(weighted_slope, 2)
                    if slope_deg <= 0.5:
                        return 0.0, "0:12", 1.0, DataProvenanceStatus.DERIVED_GEOMETRIC, []
                    else:
                        pitch_val = round(math.tan(math.radians(slope_deg)) * 12.0, 1)
                        mult = round(math.sqrt(1.0 + (pitch_val / 12.0) ** 2), 4)
                        return slope_deg, f"{pitch_val}:12", mult, DataProvenanceStatus.DERIVED_GEOMETRIC, []
            except Exception:
                pass
        elif len(verts) >= 3:
            try:
                p0 = np.array(verts[0][:3])
                p1 = np.array(verts[1][:3])
                p2 = np.array(verts[2][:3])
                v1 = p1 - p0
                v2 = p2 - p0
                normal = np.cross(v1, v2)
                norm_len = np.linalg.norm(normal)
                if norm_len > 1e-6:
                    normal = normal / norm_len
                    nz = abs(normal[2])
                    slope_rad = math.acos(min(1.0, max(0.0, nz)))
                    slope_deg = round(math.degrees(slope_rad), 2)
                    if slope_deg <= 0.5:
                        return 0.0, "0:12", 1.0, DataProvenanceStatus.DERIVED_GEOMETRIC, []
                    else:
                        pitch_val = round(math.tan(slope_rad) * 12.0, 1)
                        mult = round(math.sqrt(1.0 + (pitch_val / 12.0) ** 2), 4)
                        return slope_deg, f"{pitch_val}:12", mult, DataProvenanceStatus.DERIVED_GEOMETRIC, []
            except Exception:
                pass

        # 3. Check predefined type or name if explicit FLAT
        ptype = str(rf_data.get("predefined_type", "")).upper()
        name_str = str(rf_data.get("name", "")).upper()
        if "FLAT" in ptype or "FLAT" in name_str:
            return 0.0, "0:12", 1.0, DataProvenanceStatus.DERIVED_GEOMETRIC, []

        # 4. Unknown / Unresolved slope (NO silent default 4:12!)
        review_reasons.append("SLOPE_NOT_SPECIFIED_IN_IFC")
        return None, None, None, DataProvenanceStatus.UNKNOWN_UNRESOLVED, review_reasons

    def _resolve_roof_type(self, rf_data: dict[str, Any], slope_deg: Optional[float]) -> str:
        """Determines canonical roof type from explicit semantics or geometry."""
        ptype = str(rf_data.get("predefined_type", "")).upper()
        name_upper = str(rf_data.get("name", "")).upper()

        if "GABLE" in ptype or "GABLE" in name_upper:
            return "GABLE"
        if "HIP" in ptype or "HIP" in name_upper:
            return "HIP"
        if "FLAT" in ptype or "FLAT" in name_upper or (slope_deg is not None and slope_deg == 0.0):
            return "FLAT"
        if "SHED" in ptype or "SHED" in name_upper or "MONOPITCH" in ptype:
            return "SHED"
        if "MANSARD" in ptype or "MANSARD" in name_upper:
            return "MANSARD"
        if "COMPLEX" in ptype:
            return "COMPLEX"

        if slope_deg is not None and slope_deg > 0:
            return "GABLE"
        return "UNKNOWN"

