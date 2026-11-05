"""Flooring Normalizer: Standardizes multi-source IFC flooring evidence into canonical flooring elements
with strict precedence, physical vs spatial distinction, and deterministic scope gating.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from app.bim.models import (
    CanonicalFlooringElement,
    DataProvenanceStatus,
    FlooringCategory,
    FlooringEligibilityStatus,
    FlooringEvidenceType,
)
from app.bim.normalizer import METERS_TO_FEET, METERS_TO_INCHES, SQ_METERS_TO_SQFT
from app.ifc.geometry import polygon_intersection_area_2d


class FlooringNormalizer:
    """Normalizes raw IFC coverings, slabs, and spaces into CanonicalFlooringElements."""

    def normalize(
        self,
        raw_data: dict[str, Any],
        space_lookup: Optional[dict[str, Any]] = None,
        storey_lookup: Optional[dict[str, Any]] = None,
        unit_scale_to_meters: float = 1.0,
    ) -> list[CanonicalFlooringElement]:
        raw_coverings = raw_data.get("coverings", [])
        raw_slabs = raw_data.get("slabs", [])
        raw_spaces = raw_data.get("spaces", [])
        
        project = raw_data.get("project", {})
        unit_scale = project.get("unit_scale_to_meters", unit_scale_to_meters) or 1.0

        space_lookup = space_lookup or {s.get("guid") or s.get("ifc_guid") or s.get("id"): s for s in raw_spaces if (s.get("guid") or s.get("ifc_guid") or s.get("id"))}
        storey_lookup = storey_lookup or {st.get("guid") or st.get("ifc_guid") or st.get("id"): st for st in raw_data.get("storeys", []) if (st.get("guid") or st.get("ifc_guid") or st.get("id"))}

        elements: list[CanonicalFlooringElement] = []
        eligible_physical_elements: list[tuple[CanonicalFlooringElement, dict[str, Any]]] = []

        # =========================================================================
        # 1. PRIORITY 1: Physical IfcCovering (PredefinedType == FLOORING)
        # =========================================================================
        for cov in raw_coverings:
            predef = str(cov.get("predefined_type", "")).upper()
            cov_name = str(cov.get("name", "")).lower()
            
            is_flooring = predef == "FLOORING" or ("floor" in cov_name and "ceiling" not in cov_name)
            if not is_flooring:
                continue

            guid = cov.get("guid") or cov.get("ifc_guid") or cov.get("id", "")
            st_guid = cov.get("storey_guid", "")
            st_name = storey_lookup.get(st_guid, {}).get("name", "Level 01")
            psets = cov.get("psets", {})

            # Geometry & Area
            area_m2 = self._extract_area_from_psets(psets, unit_scale)
            if area_m2 <= 0.0:
                area_m2 = float(cov.get("gross_area") or cov.get("net_area") or cov.get("area") or cov.get("geometry_area") or 0.0)
            area_sqft = round(area_m2 * SQ_METERS_TO_SQFT, 2)

            mat_layers = cov.get("material_layers", [])
            mat_name, category, thick_in = self._classify_material(cov.get("name", ""), mat_layers, psets)

            reasons = []
            eligibility = FlooringEligibilityStatus.ELIGIBLE
            if area_sqft <= 0.0:
                eligibility = FlooringEligibilityStatus.REVIEW_REQUIRED
                reasons.append("Zero or unextracted physical covering area from IFC geometry/properties.")

            elem = CanonicalFlooringElement(
                id=guid,
                ifc_guid=guid,
                source_entity_type="IFC_COVERING",
                evidence_type=FlooringEvidenceType.PHYSICAL_COVERING,
                source_name=cov.get("name", "Flooring Covering"),
                storey_id=st_guid,
                storey_name=st_name,
                flooring_category=category,
                finish_material_name=mat_name,
                thickness_in=thick_in,
                has_physical_solid_geometry=True,
                gross_area_sqft=area_sqft,
                void_deductions_sqft=0.0,
                net_area_sqft=area_sqft,
                perimeter_ft=0.0,
                vertices=[list(p) for p in cov.get("vertices", [])],
                bbox=cov.get("bbox"),
                qto_eligibility=eligibility,
                provenance_status=DataProvenanceStatus.VERIFIED_EXPLICIT if mat_name else DataProvenanceStatus.DERIVED_GEOMETRIC,
                eligibility_reasons=reasons,
                source_psets=psets,
            )
            elements.append(elem)
            if eligibility == FlooringEligibilityStatus.ELIGIBLE:
                eligible_physical_elements.append((elem, cov))

        # =========================================================================
        # 2. PRIORITY 2: Physical IfcSlab with explicit finish material layers
        # =========================================================================
        for sl in raw_slabs:
            guid = sl.get("guid") or sl.get("ifc_guid") or sl.get("id", "")
            sl_name = sl.get("name", "Slab")
            st_guid = sl.get("storey_guid", "")
            st_name = storey_lookup.get(st_guid, {}).get("name", "Level 01")
            is_roof = sl.get("is_roof", False) or "roof" in sl_name.lower() or "roof" in st_name.lower()
            predef = str(sl.get("predefined_type", "")).upper()
            psets = sl.get("psets", {})

            # Area & Perimeter
            area_m2 = self._extract_area_from_psets(psets, unit_scale)
            if area_m2 <= 0.0 and sl.get("area"):
                area_m2 = float(sl.get("area", 0.0))
            if area_m2 <= 0.0 and sl.get("geometry_area"):
                area_m2 = float(sl.get("geometry_area", 0.0))
            area_sqft = round(area_m2 * SQ_METERS_TO_SQFT, 2)

            perim_m = self._extract_perimeter_from_psets(psets, unit_scale)
            if perim_m <= 0.0 and sl.get("perimeter"):
                perim_m = float(sl.get("perimeter", 0.0))
            perim_ft = round(perim_m * METERS_TO_FEET, 2)

            mat_layers = sl.get("material_layers", [])
            has_finish_layer, finish_layer_name, finish_thick_in = self._extract_slab_finish_layer(mat_layers)
            mat_name, category, _ = self._classify_material(sl_name, mat_layers, psets, explicit_name=finish_layer_name)

            reasons = []
            if is_roof or predef == "ROOF":
                eligibility = FlooringEligibilityStatus.INELIGIBLE_ROOF_SLAB
                reasons.append("Roof slab / deck excluded from interior flooring scope.")
            elif self._is_ceiling_assembly(sl_name, mat_layers):
                eligibility = FlooringEligibilityStatus.INELIGIBLE_STRUCTURAL_SLAB
                reasons.append("Ceiling / soffit slab assembly excluded from flooring scope.")
            elif not has_finish_layer:
                if self._is_structural_subfloor(mat_layers):
                    eligibility = FlooringEligibilityStatus.INELIGIBLE_STRUCTURAL_SLAB
                    reasons.append("Structural slab core / subfloor screed without explicit finished flooring layer.")
                else:
                    eligibility = FlooringEligibilityStatus.REVIEW_REQUIRED
                    reasons.append("Slab lacks explicit finished flooring material layer in IFC layer sets.")
            elif area_sqft <= 0.0:
                eligibility = FlooringEligibilityStatus.REVIEW_REQUIRED
                reasons.append("Zero geometric area extracted for slab.")
            else:
                eligibility = FlooringEligibilityStatus.ELIGIBLE

            elem = CanonicalFlooringElement(
                id=guid,
                ifc_guid=guid,
                source_entity_type="IFC_SLAB",
                evidence_type=FlooringEvidenceType.PHYSICAL_SLAB_FINISH,
                source_name=sl_name,
                storey_id=st_guid,
                storey_name=st_name,
                flooring_category=category,
                finish_material_name=finish_layer_name or mat_name,
                thickness_in=finish_thick_in or round(float(sl.get("thickness", 0.1524)) * METERS_TO_INCHES, 2),
                has_physical_solid_geometry=True,
                gross_area_sqft=area_sqft,
                void_deductions_sqft=0.0,
                net_area_sqft=area_sqft,
                perimeter_ft=perim_ft,
                vertices=[list(p) for p in sl.get("vertices", [])],
                bbox=sl.get("bbox"),
                qto_eligibility=eligibility,
                provenance_status=DataProvenanceStatus.VERIFIED_EXPLICIT if has_finish_layer else DataProvenanceStatus.DERIVED_GEOMETRIC,
                eligibility_reasons=reasons,
                source_psets=psets,
            )
            elements.append(elem)
            if eligibility == FlooringEligibilityStatus.ELIGIBLE:
                eligible_physical_elements.append((elem, sl))

        # =========================================================================
        # 3. PRIORITY 3: Spatial IfcSpace with Deterministic Deduplication
        # =========================================================================
        for sp in raw_spaces:
            guid = sp.get("guid") or sp.get("ifc_guid") or sp.get("id", "")
            sp_name = sp.get("name", "Space")
            st_guid = sp.get("storey_guid") or sp.get("storey_id", "")
            st_name = storey_lookup.get(st_guid, {}).get("name") or sp.get("storey_name", "Level 01")
            psets = sp.get("psets") or sp.get("source_psets") or {}

            area_m2 = self._extract_area_from_psets(psets, unit_scale)
            if area_m2 <= 0.0:
                area_m2 = float(sp.get("net_floor_area") or sp.get("gross_floor_area") or sp.get("area", 0.0))
            if area_m2 <= 0.0 and sp.get("geometry_area"):
                area_m2 = float(sp.get("geometry_area", 0.0))
            area_sqft = round(area_m2 * SQ_METERS_TO_SQFT, 2) if area_m2 > 0 else float(sp.get("net_floor_area_sqft") or sp.get("gross_floor_area_sqft", 0.0))

            perim_m = self._extract_perimeter_from_psets(psets, unit_scale)
            if perim_m <= 0.0 and sp.get("perimeter"):
                perim_m = float(sp.get("perimeter", 0.0))
            perim_ft = round(perim_m * METERS_TO_FEET, 2) if perim_m > 0 else float(sp.get("perimeter_ft", 0.0))

            # Extract floor finish from Psets
            finish_str = self._extract_space_floor_finish(psets)
            mat_name, category, _ = self._classify_material(finish_str or sp_name, [], psets)

            reasons = []
            eligibility = FlooringEligibilityStatus.ELIGIBLE
            prov_status = DataProvenanceStatus.VERIFIED_EXPLICIT if finish_str else DataProvenanceStatus.UNKNOWN_UNRESOLVED
            superseded_by_guid = None

            # Deduplication against eligible physical flooring elements:
            # IfcRelSpaceBoundary provides candidate association, requiring geometric confirmation.
            matched_phys_guid = None
            mapping_method = None
            sp_bbox = sp.get("bbox")
            sp_verts = sp.get("vertices", [])
            sp_bounded_elems = set(sp.get("bounded_element_guids", []))

            for phys_elem, phys_raw in eligible_physical_elements:
                p_guid = phys_elem.ifc_guid
                p_bbox = phys_raw.get("bbox")
                p_verts = phys_raw.get("vertices", [])
                p_bounded_spaces = set(phys_raw.get("bounded_space_guids", []))
                has_rel = p_guid in sp_bounded_elems or guid in p_bounded_spaces

                # 1. Narrow-phase geometric verification: Exact 2D Planar Overlap
                if p_verts and sp_verts:
                    inter_area_m2 = polygon_intersection_area_2d(p_verts, sp_verts)
                    if inter_area_m2 > 0.001:  # Positive geometric 2D intersection
                        matched_phys_guid = p_guid
                        mapping_method = "EXPLICIT_SPACE_BOUNDARY_WITH_EXACT_2D_PLANAR_OVERLAP" if has_rel else "EXACT_2D_PLANAR_OVERLAP"
                        break
                elif has_rel and (st_guid and st_guid == phys_elem.storey_id):
                    # Authoritative space boundary with verified storey coexistence
                    matched_phys_guid = p_guid
                    mapping_method = "EXPLICIT_SPACE_BOUNDARY_WITH_STOREY_COEXISTENCE"
                    break
                elif p_bbox and sp_bbox and self._bboxes_overlap_3d(p_bbox, sp_bbox) and (st_guid and st_guid == phys_elem.storey_id):
                    # Storey and 3D bounding box match when planar vertices could not be extracted
                    matched_phys_guid = p_guid
                    mapping_method = "STOREY_3D_BOUNDING_OVERLAP"
                    break

            if matched_phys_guid:
                eligibility = FlooringEligibilityStatus.SUPERSEDED_BY_PHYSICAL_ELEMENT
                superseded_by_guid = matched_phys_guid
                reasons.append(f"Spatial floor finish superseded by physical flooring element [{matched_phys_guid}] via {mapping_method}.")
            elif not finish_str:
                eligibility = FlooringEligibilityStatus.REVIEW_REQUIRED
                reasons.append("Space lacks explicit FloorFinish property in IFC property sets.")
            elif area_sqft <= 0.0:
                eligibility = FlooringEligibilityStatus.REVIEW_REQUIRED
                reasons.append("Zero net floor area extracted for space boundary.")

            elements.append(
                CanonicalFlooringElement(
                    id=guid,
                    ifc_guid=guid,
                    source_entity_type="IFC_SPACE",
                    evidence_type=FlooringEvidenceType.SPATIAL_SPACE_FINISH,
                    source_name=f"{sp_name} (Spatial Finish)",
                    storey_id=st_guid,
                    storey_name=st_name,
                    flooring_category=category,
                    finish_material_name=finish_str or "Unassigned Finish",
                    thickness_in=None,
                    has_physical_solid_geometry=False,
                    gross_area_sqft=area_sqft,
                    void_deductions_sqft=0.0,
                    net_area_sqft=area_sqft,
                    perimeter_ft=perim_ft,
                    vertices=[list(p) for p in sp.get("vertices", [])],
                    bbox=sp.get("bbox"),
                    qto_eligibility=eligibility,
                    provenance_status=prov_status,
                    eligibility_reasons=reasons,
                    superseded_by_guid=superseded_by_guid,
                    source_psets=psets,
                )
            )

        return elements

    def _bboxes_overlap_2d(self, b1: Optional[dict[str, float]], b2: Optional[dict[str, float]], tol: float = 0.05) -> bool:
        if not b1 or not b2:
            return False
        return not (
            b1["max_x"] < b2["min_x"] - tol or
            b1["min_x"] > b2["max_x"] + tol or
            b1["max_y"] < b2["min_y"] - tol or
            b1["min_y"] > b2["max_y"] + tol
        )

    def _bboxes_overlap_3d(self, b1: Optional[dict[str, float]], b2: Optional[dict[str, float]], z_tol: float = 1.5) -> bool:
        if not b1 or not b2:
            return False
        if not self._bboxes_overlap_2d(b1, b2):
            return False
        z_diff = abs(b1["max_z"] - b2["min_z"])
        return z_diff <= z_tol or (b1["min_z"] <= b2["max_z"] and b1["max_z"] >= b2["min_z"])

    def _extract_area_from_psets(self, psets: dict[str, Any], unit_scale: float) -> float:
        """Extracts area in square meters from any standard or vendor property set."""
        for pset_name, props in psets.items():
            for k, v in props.items():
                k_lower = k.lower()
                if isinstance(v, (int, float)) and v > 0:
                    if k_lower in ["netfloorarea", "grossfloorarea", "grossarea", "netarea", "area", "gsabimarea", "spaceusablefloorareaboma", "spacenfloorareaboma"]:
                        val = float(v)
                        # In IFC, IfcQuantityArea is stored in project area units (m² or sqft).
                        # If a model has length in millimeters (unit_scale < 0.01):
                        # - If val is extraordinarily large (> 10000), it is expressed in mm² (e.g. 100,000,000 mm² = 100 m²).
                        # - If val is a realistic architectural room/slab area (<= 10000), it is ALREADY in m²!
                        if unit_scale < 0.01:
                            if val > 10000:
                                return val * (unit_scale**2)
                            return val
                        return val
        return 0.0

    def _extract_perimeter_from_psets(self, psets: dict[str, Any], unit_scale: float) -> float:
        for pset_name, props in psets.items():
            for k, v in props.items():
                if "perimeter" in k.lower() and isinstance(v, (int, float)) and v > 0:
                    return float(v) * unit_scale
        return 0.0

    def _classify_material(
        self,
        name: str,
        layers: list[dict[str, Any]],
        psets: dict[str, Any],
        explicit_name: Optional[str] = None,
    ) -> tuple[str, FlooringCategory, Optional[float]]:
        combined_text = (name or "").lower()
        if explicit_name:
            combined_text += f" {explicit_name.lower()}"
        
        for l in layers:
            m_name = str(l.get("material_name", "")).lower()
            combined_text += f" {m_name}"

        # Match categories by keyword
        if any(k in combined_text for k in ["timberlaminate", "laminate"]):
            return explicit_name or "Timber Laminate", FlooringCategory.LAMINATE_FLOORING, 0.75
        if any(k in combined_text for k in ["hardwood", "timberboard", "timber", "wood", "oak", "parquet"]):
            return explicit_name or "Hardwood Timber", FlooringCategory.HARDWOOD_FLOORING, 0.75
        if any(k in combined_text for k in ["ceramictile", "ceramic", "porcelain", "terrazzo", "granite", "marble"]) or ("tile" in combined_text and not any(c in combined_text for c in ["ceiling", "mineral", "metal", "plaster", "pvc"])):
            return explicit_name or "Ceramic / Porcelain Tile", FlooringCategory.TILE_CERAMIC_PORCELAIN, 0.375
        if any(k in combined_text for k in ["carpet tile", "modular carpet"]):
            return explicit_name or "Carpet Tile", FlooringCategory.CARPET_TILE, 0.25
        if any(k in combined_text for k in ["carpet", "broadloom", "textile"]):
            return explicit_name or "Broadloom Carpet", FlooringCategory.CARPET_BROADLOOM, 0.50
        if any(k in combined_text for k in ["tilespvc", "vinyl", "lvt", "vct", "linoleum", "rubber"]):
            return explicit_name or "Resilient Vinyl (LVT)", FlooringCategory.RESILIENT_VINYL_LVT, 0.125
        if any(k in combined_text for k in ["sealed concrete", "polished concrete", "epoxy"]):
            return explicit_name or "Polished Concrete / Epoxy Finish", FlooringCategory.CONCRETE_POLISHED_SEALED, 2.0

        return explicit_name or "Unassigned Finish", FlooringCategory.UNASSIGNED_FINISH, None

    def _extract_slab_finish_layer(self, layers: list[dict[str, Any]]) -> tuple[bool, Optional[str], Optional[float]]:
        """Identifies architectural finish material layer in multi-layer composite slabs."""
        finish_keywords = [
            "timberboard", "timberboards", "timberlaminate", "laminate",
            "ceramictile", "porcelain", "carpet", "vinyl", "tilespvc",
            "parquet", "hardwood", "terrazzo", "granite", "marble", "linoleum", "rubber"
        ]
        excluded_keywords = [
            "cast in situ", "insituconcrete", "concrete", "structural concrete",
            "screed", "paving", "plywood", "insulation", "polystyrene", "mineralwool",
            "plasterboard", "plaster", "gypsum", "ceiling", "framemetal", "concept", "acoustic", "membrane"
        ]
        for l in layers:
            m_name = str(l.get("material_name", ""))
            m_lower = m_name.lower()
            
            # Skip ceiling and structural subfloor materials
            if any(ex in m_lower for ex in excluded_keywords):
                continue
            
            is_match = any(k in m_lower for k in finish_keywords) or (
                "tile" in m_lower and not any(c in m_lower for c in ["ceiling", "mineral", "plaster", "metal", "gypsum"])
            )
            if is_match:
                thick_ft = float(l.get("thickness", 0.0))
                thick_in = round(thick_ft * 12.0, 2) if thick_ft < 1.0 else round(thick_ft * METERS_TO_INCHES, 2)
                return True, m_name, thick_in
        return False, None, None

    def _is_ceiling_assembly(self, name: str, layers: list[dict[str, Any]]) -> bool:
        combined = (name or "").lower() + " " + " ".join(str(l.get("material_name", "")).lower() for l in layers)
        return any(k in combined for k in ["ceiling", "conceptceiling", "framemetal", "plasterboardgypsum", "mineralwoolbatts"]) and not any(
            fk in combined for fk in ["timberboard", "timberlaminate", "ceramictile", "tilespvc", "carpet"]
        )

    def _is_structural_subfloor(self, layers: list[dict[str, Any]]) -> bool:
        if not layers:
            return True
        structural_keywords = ["concrete", "insitu", "screed", "polystyrene", "insulation", "paving", "membrane", "plywood", "gravel", "sand"]
        return all(any(k in str(l.get("material_name", "")).lower() for k in structural_keywords) for l in layers)

    def _extract_space_floor_finish(self, psets: dict[str, Any]) -> Optional[str]:
        for pset_name, props in psets.items():
            for k, v in props.items():
                if ("finish" in k.lower() or "floor" in k.lower()) and v and not isinstance(v, (int, float, bool)):
                    val_str = str(v).strip()
                    if val_str and val_str.lower() not in ["none", "false", "0", "n/a"]:
                        return val_str
        return None
