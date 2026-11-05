"""IFC Property Sets and Quantity Sets Extraction:
Extracts material layers, Psets (Pset_WallCommon), and QTO base quantities (Qto_WallBaseQuantities).
"""
from __future__ import annotations

from typing import Any, Optional


def extract_property_sets(element: Any) -> dict[str, dict[str, Any]]:
    """Extracts all defined property sets (Psets) attached to an IFC element."""
    psets: dict[str, dict[str, Any]] = {}

    # Check IsDefinedBy relationships
    for rel in getattr(element, "IsDefinedBy", []):
        if rel.is_a("IfcRelDefinesByProperties"):
            prop_def = getattr(rel, "RelatingPropertyDefinition", None)
            if not prop_def:
                continue

            if prop_def.is_a("IfcPropertySet"):
                pset_name = getattr(prop_def, "Name", "UnknownPset")
                psets[pset_name] = {}
                for prop in getattr(prop_def, "HasProperties", []):
                    prop_name = getattr(prop, "Name", None)
                    if not prop_name:
                        continue
                    # SingleValue property
                    if prop.is_a("IfcPropertySingleValue"):
                        nominal_val = getattr(prop, "NominalValue", None)
                        if nominal_val is not None:
                            psets[pset_name][prop_name] = getattr(nominal_val, "wrappedValue", None)
                    elif prop.is_a("IfcPropertyEnumeratedValue"):
                        enum_vals = getattr(prop, "EnumerationValues", [])
                        psets[pset_name][prop_name] = [getattr(v, "wrappedValue", str(v)) for v in enum_vals]

            elif prop_def.is_a("IfcElementQuantity"):
                qset_name = getattr(prop_def, "Name", "UnknownQuantitySet")
                psets[qset_name] = {}
                for quantity in getattr(prop_def, "Quantities", []):
                    q_name = getattr(quantity, "Name", None)
                    if not q_name:
                        continue
                    if quantity.is_a("IfcQuantityLength"):
                        psets[qset_name][q_name] = getattr(quantity, "LengthValue", None)
                    elif quantity.is_a("IfcQuantityArea"):
                        psets[qset_name][q_name] = getattr(quantity, "AreaValue", None)
                    elif quantity.is_a("IfcQuantityVolume"):
                        psets[qset_name][q_name] = getattr(quantity, "VolumeValue", None)
                    elif quantity.is_a("IfcQuantityCount"):
                        psets[qset_name][q_name] = getattr(quantity, "CountValue", None)

    return psets


def extract_material_layers(element: Any, unit_scale: float = 1.0) -> list[dict[str, Any]]:
    """Extracts composite material layer definition (IfcMaterialLayerSet / IfcMaterialLayerSetUsage)."""
    layers: list[dict[str, Any]] = []

    # 1. Direct association
    for rel in getattr(element, "HasAssociations", []):
        if rel.is_a("IfcRelAssociatesMaterial"):
            mat_select = getattr(rel, "RelatingMaterial", None)
            if not mat_select:
                continue

            # Layer Set Usage
            layer_set = None
            if mat_select.is_a("IfcMaterialLayerSetUsage"):
                layer_set = getattr(mat_select, "ForLayerSet", None)
            elif mat_select.is_a("IfcMaterialLayerSet"):
                layer_set = mat_select

            if layer_set:
                for idx, layer in enumerate(getattr(layer_set, "MaterialLayers", [])):
                    mat = getattr(layer, "Material", None)
                    mat_name = getattr(mat, "Name", "Unknown Material") if mat else "Unknown Material"
                    thickness = float(getattr(layer, "LayerThickness", 0.0)) * unit_scale
                    is_ventilated = bool(getattr(layer, "IsVentilated", False))
                    layers.append(
                        {
                            "layer_index": idx,
                            "material_name": mat_name,
                            "thickness": thickness,
                            "is_ventilated": is_ventilated,
                        }
                    )
            elif mat_select.is_a("IfcMaterial"):
                layers.append(
                    {
                        "layer_index": 0,
                        "material_name": getattr(mat_select, "Name", "Generic Material"),
                        "thickness": 0.0,
                        "is_ventilated": False,
                    }
                )

    return layers


def extract_common_wall_attributes(psets: dict[str, dict[str, Any]], unit_scale: float = 1.0) -> dict[str, Any]:
    """Extracts standard wall parameters from Pset_WallCommon and Qto_WallBaseQuantities."""
    wall_common = psets.get("Pset_WallCommon", {})
    base_qto = psets.get("Qto_WallBaseQuantities", {})

    is_external = bool(wall_common.get("IsExternal", False))
    load_bearing = bool(wall_common.get("LoadBearing", False))
    fire_rating = wall_common.get("FireRating")
    acoustic_rating = wall_common.get("AcousticRating")
    combustible = wall_common.get("Combustible")

    # Qto quantities
    qto_length = base_qto.get("Length")
    qto_width = base_qto.get("Width")  # thickness
    qto_height = base_qto.get("Height")
    qto_gross_area = base_qto.get("GrossSideArea")
    qto_net_area = base_qto.get("NetSideArea")

    return {
        "is_external": is_external,
        "is_load_bearing": load_bearing,
        "fire_rating": str(fire_rating) if fire_rating is not None else None,
        "acoustic_rating": str(acoustic_rating) if acoustic_rating is not None else None,
        "combustible": combustible,
        "qto_length": float(qto_length) * unit_scale if qto_length is not None else None,
        "qto_thickness": float(qto_width) * unit_scale if qto_width is not None else None,
        "qto_height": float(qto_height) * unit_scale if qto_height is not None else None,
        "qto_gross_area": float(qto_gross_area) * (unit_scale**2) if qto_gross_area is not None else None,
        "qto_net_area": float(qto_net_area) * (unit_scale**2) if qto_net_area is not None else None,
    }
