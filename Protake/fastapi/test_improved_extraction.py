import os
import sys
import math
import ifcopenshell
import numpy as np

FASTAPI_ROOT = os.path.abspath(os.path.dirname(__file__))
if FASTAPI_ROOT not in sys.path:
    sys.path.insert(0, FASTAPI_ROOT)

from app.ifc.geometry import get_local_placement_matrix, transform_point
from app.ifc.properties import extract_property_sets, extract_common_wall_attributes

def extract_wall_geometry_parameters_improved(wall, unit_scale=1.0):
    length = 0.0
    thickness = 0.0
    height = 0.0
    start_local = (0.0, 0.0, 0.0)
    end_local = None

    placement_matrix = get_local_placement_matrix(getattr(wall, "ObjectPlacement", None))

    rep = getattr(wall, "Representation", None)
    if rep:
        # A. Check Axis Representation first (canonical centerline in IFC standard)
        for rep_item in getattr(rep, "Representations", []):
            rep_id = getattr(rep_item, "RepresentationIdentifier", "")
            rep_type = getattr(rep_item, "RepresentationType", "")
            
            if rep_id == "Axis" or rep_type in ["Curve2D", "Segment"]:
                for item in getattr(rep_item, "Items", []):
                    if item.is_a("IfcPolyline"):
                        pts = getattr(item, "Points", [])
                        if len(pts) >= 2:
                            p1 = pts[0].Coordinates
                            p2 = pts[-1].Coordinates
                            start_local = (float(p1[0]), float(p1[1]), 0.0)
                            end_local = (float(p2[0]), float(p2[1]), 0.0)
                            dx = (p2[0] - p1[0]) * unit_scale
                            dy = (p2[1] - p1[1]) * unit_scale
                            length = math.sqrt(dx*dx + dy*dy)

        # B. Check Body Representation (3D Extrusion)
        for rep_item in getattr(rep, "Representations", []):
            for item in getattr(rep_item, "Items", []):
                if item.is_a("IfcExtrudedAreaSolid"):
                    depth = getattr(item, "Depth", 0.0)
                    if depth:
                        height = float(depth) * unit_scale

                    profile = getattr(item, "SweptArea", None)
                    if profile:
                        if profile.is_a("IfcRectangleProfileDef"):
                            x_dim = float(getattr(profile, "XDim", 0.0)) * unit_scale
                            y_dim = float(getattr(profile, "YDim", 0.0)) * unit_scale
                            if length == 0:
                                length = max(x_dim, y_dim)
                            if thickness == 0:
                                thickness = min(x_dim, y_dim)
                        elif profile.is_a("IfcArbitraryClosedProfileDef"):
                            curve = getattr(profile, "OuterCurve", None)
                            if curve and curve.is_a("IfcPolyline"):
                                c_pts = getattr(curve, "Points", [])
                                if len(c_pts) > 1:
                                    xs = [float(p.Coordinates[0]) * unit_scale for p in c_pts]
                                    ys = [float(p.Coordinates[1]) * unit_scale for p in c_pts]
                                    span_x = max(xs) - min(xs)
                                    span_y = max(ys) - min(ys)
                                    if length == 0:
                                        length = max(span_x, span_y)
                                    if thickness == 0:
                                        thickness = min(span_x, span_y)

    # If end_local wasn't set from Axis curve, extend along +X by length
    if end_local is None:
        local_len = length / unit_scale if unit_scale > 0 else length
        end_local = (start_local[0] + local_len, start_local[1], start_local[2])

    start_world = transform_point(start_local, placement_matrix)
    start_world = (start_world[0] * unit_scale, start_world[1] * unit_scale, start_world[2] * unit_scale)
    
    end_world = transform_point(end_local, placement_matrix)
    end_world = (end_world[0] * unit_scale, end_world[1] * unit_scale, end_world[2] * unit_scale)

    return {
        "length": length,
        "thickness": thickness,
        "height": height,
        "start_point": start_world,
        "end_point": end_world,
        "transform_matrix": placement_matrix.tolist(),
    }

def test_on_all_models():
    ifc_files = [
        "aff33ef9-85e6-4b04-ad0e-9d1b6527ae66_NBS_LakesideRVT01_Arch.ifc",
        "1345b46a-329a-47b4-ad5c-6256dfd5b7a8_NBS_LakesideRVT10_Arch.ifc",
        "294dc25e-2d1e-4705-9b56-ed6e4eae4308_NBS_LakesideVW00_Arch.ifc",
        "9471c5f8-ac1f-47e2-a00f-e450f32edfb2_NBS_LakesideAC10_Arch.ifc",
    ]

    for fname in ifc_files:
        fpath = os.path.join(FASTAPI_ROOT, "storage", "ifc", fname)
        if not os.path.exists(fpath):
            continue
        
        ifc_file = ifcopenshell.open(fpath)
        # Get unit scale
        unit_scale = 1.0
        for unit in ifc_file.by_type("IfcSIUnit"):
            if getattr(unit, "UnitType", None) == "LENGTHUNIT":
                prefix = getattr(unit, "Prefix", None)
                if prefix == "MILLI":
                    unit_scale = 0.001
                elif prefix == "CENTI":
                    unit_scale = 0.01

        walls = ifc_file.by_type("IfcWall")
        print(f"\n========================================================")
        print(f"Testing {fname} ({len(walls)} walls, unit_scale={unit_scale})")
        print(f"========================================================")

        zero_len_count = 0
        for w in walls:
            res = extract_wall_geometry_parameters_improved(w, unit_scale)
            l_ft = res["length"] / 0.3048
            h_ft = res["height"] / 0.3048
            sx, sy, sz = [c / 0.3048 for c in res["start_point"]]
            ex, ey, ez = [c / 0.3048 for c in res["end_point"]]
            
            if l_ft <= 0.001:
                zero_len_count += 1
                print(f"  ZERO LENGTH: GUID={w.GlobalId}, Name={w.Name}")

        print(f"Total zero-length walls with improved extractor: {zero_len_count} / {len(walls)}")

if __name__ == "__main__":
    test_on_all_models()
