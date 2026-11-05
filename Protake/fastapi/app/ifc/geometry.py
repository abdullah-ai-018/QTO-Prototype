"""IFC Geometry Resolution: Resolves local-to-world coordinate transformations,
bounding boxes, centerlines, and parametric profiles.
"""
from __future__ import annotations

import math
from typing import Any, Optional
import numpy as np


def get_local_placement_matrix(placement: Any) -> np.ndarray:
    """Recursively computes the 4x4 transformation matrix for an IfcLocalPlacement."""
    matrix = np.identity(4, dtype=float)
    if not placement:
        return matrix

    current = placement
    placement_chain = []
    while current:
        placement_chain.append(current)
        current = getattr(current, "PlacementRelTo", None)

    for plc in reversed(placement_chain):
        relative_placement = getattr(plc, "RelativePlacement", None)
        if not relative_placement:
            continue

        local_mat = axis2placement_to_matrix(relative_placement)
        matrix = matrix @ local_mat

    return matrix


def axis2placement_to_matrix(axis2placement: Any) -> np.ndarray:
    """Converts an IfcAxis2Placement3D or 2D into a 4x4 transformation matrix."""
    mat = np.identity(4, dtype=float)
    if not axis2placement:
        return mat

    location = getattr(axis2placement, "Location", None)
    if location and getattr(location, "Coordinates", None):
        coords = location.Coordinates
        if len(coords) >= 3:
            mat[0, 3] = float(coords[0])
            mat[1, 3] = float(coords[1])
            mat[2, 3] = float(coords[2])
        elif len(coords) == 2:
            mat[0, 3] = float(coords[0])
            mat[1, 3] = float(coords[1])

    # Z Axis (Axis) and X Axis (RefDirection)
    axis = getattr(axis2placement, "Axis", None)
    ref_direction = getattr(axis2placement, "RefDirection", None)

    z = np.array([0.0, 0.0, 1.0])
    if axis and getattr(axis, "DirectionRatios", None):
        ratios = [float(r) for r in axis.DirectionRatios]
        if len(ratios) == 3:
            norm = math.sqrt(sum(r * r for r in ratios))
            if norm > 1e-8:
                z = np.array(ratios) / norm

    x = np.array([1.0, 0.0, 0.0])
    if ref_direction and getattr(ref_direction, "DirectionRatios", None):
        ratios = [float(r) for r in ref_direction.DirectionRatios]
        if len(ratios) >= 2:
            r3 = [ratios[0], ratios[1], ratios[2] if len(ratios) > 2 else 0.0]
            norm = math.sqrt(sum(r * r for r in r3))
            if norm > 1e-8:
                x = np.array(r3) / norm

    # Re-orthogonalize
    x = x - np.dot(x, z) * z
    x_norm = np.linalg.norm(x)
    if x_norm > 1e-8:
        x = x / x_norm
    else:
        x = np.array([1.0, 0.0, 0.0])

    y = np.cross(z, x)
    y_norm = np.linalg.norm(y)
    if y_norm > 1e-8:
        y = y / y_norm

    mat[0:3, 0] = x
    mat[0:3, 1] = y
    mat[0:3, 2] = z

    return mat


def transform_point(point: tuple[float, ...], matrix: np.ndarray) -> tuple[float, float, float]:
    """Applies a 4x4 transformation matrix to a 2D or 3D coordinate point."""
    z_val = point[2] if len(point) > 2 else 0.0
    vec = np.array([point[0], point[1], z_val, 1.0], dtype=float)
    res = matrix @ vec
    return (float(res[0]), float(res[1]), float(res[2]))



def extract_wall_geometry_parameters(wall: Any, unit_scale: float = 1.0) -> dict[str, Any]:
    """Extracts analytical geometry (length, thickness, height, start/end centerline points)
    from an IfcWall / IfcWallStandardCase element.
    """
    length = 0.0
    thickness = 0.0
    height = 0.0
    start_local = (0.0, 0.0, 0.0)
    end_local = None

    # 1. Inspect Placement
    placement_matrix = get_local_placement_matrix(getattr(wall, "ObjectPlacement", None))

    # 2. Check representation for Axis curve (IFC standard for wall centerline)
    rep = getattr(wall, "Representation", None)
    if rep:
        # A. Priority 1: Check Axis representation for exact start, end, and length
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
                            dx = (float(p2[0]) - float(p1[0])) * unit_scale
                            dy = (float(p2[1]) - float(p1[1])) * unit_scale
                            length = (dx * dx + dy * dy) ** 0.5
                    elif item.is_a("IfcTrimmedCurve"):
                        # Basis curve (e.g. IfcLine)
                        p1 = getattr(item, "Trim1", [])
                        p2 = getattr(item, "Trim2", [])
                        if p1 and p2 and hasattr(p1[0], "Coordinates") and hasattr(p2[0], "Coordinates"):
                            pt1 = p1[0].Coordinates
                            pt2 = p2[0].Coordinates
                            start_local = (float(pt1[0]), float(pt1[1]), 0.0)
                            end_local = (float(pt2[0]), float(pt2[1]), 0.0)
                            dx = (float(pt2[0]) - float(pt1[0])) * unit_scale
                            dy = (float(pt2[1]) - float(pt1[1])) * unit_scale
                            length = (dx * dx + dy * dy) ** 0.5

        # B. Priority 2: Check Body representation (3D Extrusion Solid)
        for rep_item in getattr(rep, "Representations", []):
            for item in getattr(rep_item, "Items", []):
                if item.is_a("IfcExtrudedAreaSolid"):
                    # Extrusion depth is usually height
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

    # 3. If end_local is still not derived, project along local +X by length
    if end_local is None:
        local_len = length / unit_scale if unit_scale > 0 else length
        end_local = (start_local[0] + local_len, start_local[1], start_local[2])

    # 4. Compute start and end centerline in world coordinates
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


def extract_opening_geometry_parameters(opening: Any, unit_scale: float = 1.0) -> dict[str, Any]:
    """Extracts explicit geometric bounding dimensions and placement for an IfcOpeningElement.

    For IfcExtrudedAreaSolid: the profile (XDim × YDim) is the opening face; Depth is the
    wall-traversal thickness. We determine which profile dimension is height by checking which
    axis of the solid's coordinate system is most aligned with the world Z-up direction.
    """
    width = 0.0
    height = 0.0
    thickness = 0.0

    placement_matrix = get_local_placement_matrix(getattr(opening, "ObjectPlacement", None))

    rep = getattr(opening, "Representation", None)
    if rep:
        for rep_item in getattr(rep, "Representations", []):
            for item in getattr(rep_item, "Items", []):
                if item.is_a("IfcExtrudedAreaSolid"):
                    depth = getattr(item, "Depth", 0.0)
                    wall_traversal = float(depth) * unit_scale  # wall thickness — not opening height

                    pos = getattr(item, "Position", None)
                    solid_mat = placement_matrix @ axis2placement_to_matrix(pos) if pos else placement_matrix

                    profile = getattr(item, "SweptArea", None)
                    if profile and profile.is_a("IfcRectangleProfileDef"):
                        x_dim = float(getattr(profile, "XDim", 0.0)) * unit_scale
                        y_dim = float(getattr(profile, "YDim", 0.0)) * unit_scale

                        # Determine which profile axis is most vertical (world Z).
                        # Column 0 = profile X axis in world space; column 1 = profile Y axis.
                        world_up = np.array([0.0, 0.0, 1.0])
                        x_vert = abs(float(np.dot(solid_mat[0:3, 0], world_up)))
                        y_vert = abs(float(np.dot(solid_mat[0:3, 1], world_up)))

                        if y_vert >= x_vert:
                            # Profile Y axis is more vertical → YDim is the opening height
                            width = x_dim
                            height = y_dim
                        else:
                            # Profile X axis is more vertical → XDim is the opening height
                            width = y_dim
                            height = x_dim

                        thickness = wall_traversal

                    elif profile and profile.is_a("IfcArbitraryClosedProfileDef"):
                        curve = getattr(profile, "OuterCurve", None)
                        if curve and curve.is_a("IfcPolyline"):
                            raw_pts = getattr(curve, "Points", [])
                            if raw_pts:
                                xs = [float(p.Coordinates[0]) * unit_scale for p in raw_pts]
                                ys = [float(p.Coordinates[1]) * unit_scale for p in raw_pts]
                                span_x = max(xs) - min(xs)
                                span_y = max(ys) - min(ys)
                                world_up = np.array([0.0, 0.0, 1.0])
                                x_vert = abs(float(np.dot(solid_mat[0:3, 0], world_up)))
                                y_vert = abs(float(np.dot(solid_mat[0:3, 1], world_up)))
                                if y_vert >= x_vert:
                                    width = span_x
                                    height = span_y
                                else:
                                    width = span_y
                                    height = span_x
                                thickness = wall_traversal

                elif item.is_a("IfcBoundingBox"):
                    # BoundingBox convention: XDim=along wall, YDim=normal (thickness), ZDim=height
                    width = float(getattr(item, "XDim", 0.0)) * unit_scale
                    thickness = float(getattr(item, "YDim", 0.0)) * unit_scale
                    height = float(getattr(item, "ZDim", 0.0)) * unit_scale

    return {
        "width": width,
        "height": height,
        "thickness": thickness,
        "transform_matrix": placement_matrix.tolist(),
    }


def polygon_area_2d(pts: list[tuple[float, ...]]) -> float:
    """Computes 2D planar polygon area via the shoelace formula."""
    if len(pts) < 3:
        return 0.0
    area = 0.0
    n = len(pts)
    for i in range(n):
        j = (i + 1) % n
        area += pts[i][0] * pts[j][1] - pts[j][0] * pts[i][1]
    return abs(area) * 0.5


def polygon_intersection_area_2d(
    pts1: list[tuple[float, ...]],
    pts2: list[tuple[float, ...]],
) -> float:
    """Computes exact 2D planar intersection area between two polygon vertex sequences.
    Uses Shapely Polygon intersection for exact geometric proof.
    """
    if len(pts1) < 3 or len(pts2) < 3:
        return 0.0
    try:
        from shapely.geometry import Polygon
        poly1 = Polygon([(p[0], p[1]) for p in pts1]).buffer(0)
        poly2 = Polygon([(p[0], p[1]) for p in pts2]).buffer(0)
        if not poly1.is_valid or not poly2.is_valid or poly1.is_empty or poly2.is_empty:
            return 0.0
        inter = poly1.intersection(poly2)
        return float(inter.area) if not inter.is_empty else 0.0
    except Exception:
        return 0.0



def extract_surface_geometry_parameters(element: Any, unit_scale: float = 1.0) -> dict[str, Any]:
    """Extracts 3D bounding box, planar polygon footprint, geometric surface area, and exact face topology for an IFC element."""
    placement_matrix = get_local_placement_matrix(getattr(element, "ObjectPlacement", None))
    
    unique_verts: list[tuple[float, float, float]] = []
    vert_lookup: dict[tuple[float, float, float], int] = {}
    faces: list[list[int]] = []
    face_map: list[int] = []
    world_pts: list[tuple[float, float, float]] = []

    def add_point(pt: tuple[float, float, float]) -> int:
        pt_scaled = (pt[0] * unit_scale, pt[1] * unit_scale, pt[2] * unit_scale)
        pt_rounded = (round(pt_scaled[0], 4), round(pt_scaled[1], 4), round(pt_scaled[2], 4))
        if pt_rounded not in vert_lookup:
            vert_lookup[pt_rounded] = len(unique_verts)
            unique_verts.append(pt_rounded)
        return vert_lookup[pt_rounded]

    rep = getattr(element, "Representation", None)
    if rep:
        for rep_item in getattr(rep, "Representations", []):
            for item in getattr(rep_item, "Items", []):
                # 1. Extruded Area Solid
                if item.is_a("IfcExtrudedAreaSolid"):
                    profile = getattr(item, "SweptArea", None)
                    pos = getattr(item, "Position", None)
                    item_mat = placement_matrix @ axis2placement_to_matrix(pos) if pos else placement_matrix

                    if profile:
                        if profile.is_a("IfcRectangleProfileDef"):
                            x_d = float(profile.XDim)
                            y_d = float(profile.YDim)
                            corners = [
                                (-x_d / 2.0, -y_d / 2.0, 0.0),
                                (x_d / 2.0, -y_d / 2.0, 0.0),
                                (x_d / 2.0, y_d / 2.0, 0.0),
                                (-x_d / 2.0, y_d / 2.0, 0.0),
                            ]
                            c_pts = [transform_point(c, item_mat) for c in corners]
                            world_pts.extend(c_pts)
                            c_idx = [add_point(p) for p in c_pts]
                            if len(c_idx) >= 4:
                                faces.append([c_idx[0], c_idx[1], c_idx[2]])
                                faces.append([c_idx[0], c_idx[2], c_idx[3]])
                                face_map.extend([0, 0])
                        elif profile.is_a("IfcArbitraryClosedProfileDef") or profile.is_a("IfcArbitraryProfileDefWithVoids"):
                            curve = getattr(profile, "OuterCurve", None)
                            if curve and curve.is_a("IfcPolyline"):
                                pts = [transform_point(tuple(float(c) for c in p.Coordinates), item_mat) for p in getattr(curve, "Points", [])]
                                world_pts.extend(pts)
                                idx_list = [add_point(p) for p in pts]
                                if len(idx_list) >= 3:
                                    for i in range(1, len(idx_list) - 1):
                                        faces.append([idx_list[0], idx_list[i], idx_list[i + 1]])
                                        face_map.append(0)
                # 2. Faceted BRep
                elif item.is_a("IfcFacetedBrep"):
                    shell = getattr(item, "Outer", None)
                    if shell and hasattr(shell, "CfsFaces"):
                        for f_idx, f in enumerate(shell.CfsFaces):
                            bound = getattr(f, "Bounds", [None])[0]
                            if bound and hasattr(bound, "Bound"):
                                loop = bound.Bound
                                if hasattr(loop, "Polygon"):
                                    pts = [transform_point(tuple(float(c) for c in pt.Coordinates), placement_matrix) for pt in loop.Polygon]
                                    world_pts.extend(pts)
                                    idx_list = [add_point(p) for p in pts]
                                    if len(idx_list) >= 3:
                                        for i in range(1, len(idx_list) - 1):
                                            faces.append([idx_list[0], idx_list[i], idx_list[i + 1]])
                                            face_map.append(f_idx)
                # 3. CurveBoundedPlane
                elif item.is_a("IfcCurveBoundedPlane"):
                    basis_surface = getattr(item, "BasisSurface", None)
                    surf_pos = getattr(basis_surface, "Position", None) if basis_surface else None
                    surf_mat = placement_matrix @ axis2placement_to_matrix(surf_pos) if surf_pos else placement_matrix
                    outer_bound = getattr(item, "OuterBoundary", None)
                    if outer_bound and outer_bound.is_a("IfcPolyline"):
                        pts = [transform_point(tuple(float(c) for c in p.Coordinates), surf_mat) for p in getattr(outer_bound, "Points", [])]
                        world_pts.extend(pts)
                        idx_list = [add_point(p) for p in pts]
                        if len(idx_list) >= 3:
                            for i in range(1, len(idx_list) - 1):
                                faces.append([idx_list[0], idx_list[i], idx_list[i + 1]])
                                face_map.append(0)
                # 4. Direct Polyline / IndexedPolyCurve Footprint
                elif item.is_a("IfcPolyline"):
                    pts = [transform_point(tuple(float(c) for c in p.Coordinates), placement_matrix) for p in getattr(item, "Points", [])]
                    world_pts.extend(pts)
                    idx_list = [add_point(p) for p in pts]
                    if len(idx_list) >= 3:
                        for i in range(1, len(idx_list) - 1):
                            faces.append([idx_list[0], idx_list[i], idx_list[i + 1]])
                            face_map.append(0)
                elif item.is_a("IfcIndexedPolyCurve"):
                    coord = getattr(item, "Points", None)
                    if coord and hasattr(coord, "CoordList"):
                        pts = [transform_point(tuple(float(c) for c in p), placement_matrix) for p in coord.CoordList]
                        world_pts.extend(pts)
                        idx_list = [add_point(p) for p in pts]
                        if len(idx_list) >= 3:
                            for i in range(1, len(idx_list) - 1):
                                faces.append([idx_list[0], idx_list[i], idx_list[i + 1]])
                                face_map.append(0)
                # 5. FaceBasedSurfaceModel / ShellBasedSurfaceModel
                elif item.is_a("IfcFaceBasedSurfaceModel") or item.is_a("IfcShellBasedSurfaceModel"):
                    faces_attr = "FbsmFaces" if item.is_a("IfcFaceBasedSurfaceModel") else "SbsmFaces"
                    for fsm in getattr(item, faces_attr, []):
                        for f_idx, f in enumerate(getattr(fsm, "CfsFaces", [])):
                            for bound in getattr(f, "Bounds", []):
                                loop = getattr(bound, "Bound", None)
                                if loop and hasattr(loop, "Polygon"):
                                    pts = [transform_point(tuple(float(c) for c in pt.Coordinates), placement_matrix) for pt in loop.Polygon]
                                    world_pts.extend(pts)
                                    idx_list = [add_point(p) for p in pts]
                                    if len(idx_list) >= 3:
                                        for i in range(1, len(idx_list) - 1):
                                            faces.append([idx_list[0], idx_list[i], idx_list[i + 1]])
                                            face_map.append(f_idx)
                # 6. TriangulatedFaceSet (IFC4)
                elif item.is_a("IfcTriangulatedFaceSet"):
                    coord = getattr(item, "Coordinates", None)
                    coord_indices = getattr(item, "CoordIndex", [])
                    if coord and hasattr(coord, "CoordList"):
                        pts = [transform_point(tuple(float(c) for c in p), placement_matrix) for p in coord.CoordList]
                        world_pts.extend(pts)
                        idx_list = [add_point(p) for p in pts]
                        for c_idx, face_tuple in enumerate(coord_indices):
                            # IFC 1-based indexing check
                            f_idx = [i - 1 if min(face_tuple) > 0 else i for i in face_tuple]
                            if len(f_idx) >= 3:
                                faces.append([f_idx[0], f_idx[1], f_idx[2]])
                                face_map.append(c_idx)
                # 6b. PolygonalFaceSet (IFC4, used by ArchiCAD and Revit)
                elif item.is_a("IfcPolygonalFaceSet"):
                    coord = getattr(item, "Coordinates", None)
                    pf_faces = getattr(item, "Faces", [])
                    if coord and hasattr(coord, "CoordList"):
                        pts = [transform_point(tuple(float(c) for c in p), placement_matrix) for p in coord.CoordList]
                        world_pts.extend(pts)
                        idx_list = [add_point(p) for p in pts]
                        for f_idx, pf in enumerate(pf_faces):
                            outer = getattr(pf, "CoordIndex", [])
                            if outer:
                                raw = list(outer)
                                f = [i - 1 if min(raw) > 0 else i for i in raw]
                                if len(f) >= 3:
                                    for ti in range(1, len(f) - 1):
                                        faces.append([f[0], f[ti], f[ti + 1]])
                                        face_map.append(f_idx)
                # 7. MappedItem — recurse into all sub-items
                elif item.is_a("IfcMappedItem"):
                    mapping_source = getattr(item, "MappingSource", None)
                    target = getattr(item, "MappingTarget", None)
                    target_mat = placement_matrix @ axis2placement_to_matrix(target) if target else placement_matrix
                    if mapping_source:
                        mapped_rep = getattr(mapping_source, "MappedRepresentation", None)
                        origin = getattr(mapping_source, "MappingOrigin", None)
                        if origin:
                            target_mat = target_mat @ axis2placement_to_matrix(origin)
                        if mapped_rep:
                            for m_item in getattr(mapped_rep, "Items", []):
                                if m_item.is_a("IfcExtrudedAreaSolid"):
                                    prof = getattr(m_item, "SweptArea", None)
                                    m_pos = getattr(m_item, "Position", None)
                                    m_mat = target_mat @ axis2placement_to_matrix(m_pos) if m_pos else target_mat
                                    if prof and prof.is_a("IfcRectangleProfileDef"):
                                        xd, yd = float(prof.XDim), float(prof.YDim)
                                        corners = [(-xd/2, -yd/2, 0.0), (xd/2, -yd/2, 0.0), (xd/2, yd/2, 0.0), (-xd/2, yd/2, 0.0)]
                                        pts = [transform_point(c, m_mat) for c in corners]
                                        world_pts.extend(pts)
                                        c_idx = [add_point(p) for p in pts]
                                        if len(c_idx) >= 4:
                                            faces.append([c_idx[0], c_idx[1], c_idx[2]])
                                            faces.append([c_idx[0], c_idx[2], c_idx[3]])
                                            face_map.extend([0, 0])
                                    elif prof and prof.is_a("IfcArbitraryClosedProfileDef"):
                                        curve = getattr(prof, "OuterCurve", None)
                                        if curve and curve.is_a("IfcPolyline"):
                                            pts = [transform_point(tuple(float(c) for c in p.Coordinates), m_mat) for p in getattr(curve, "Points", [])]
                                            world_pts.extend(pts)
                                            ii = [add_point(p) for p in pts]
                                            for ti in range(1, len(ii) - 1):
                                                faces.append([ii[0], ii[ti], ii[ti + 1]])
                                                face_map.append(0)
                                elif m_item.is_a("IfcFacetedBrep"):
                                    shell = getattr(m_item, "Outer", None)
                                    if shell and hasattr(shell, "CfsFaces"):
                                        for f_idx, f in enumerate(shell.CfsFaces):
                                            bound = getattr(f, "Bounds", [None])[0]
                                            if bound and hasattr(bound, "Bound"):
                                                loop = bound.Bound
                                                if hasattr(loop, "Polygon"):
                                                    pts = [transform_point(tuple(float(c) for c in pt.Coordinates), target_mat) for pt in loop.Polygon]
                                                    world_pts.extend(pts)
                                                    ii = [add_point(p) for p in pts]
                                                    for ti in range(1, len(ii) - 1):
                                                        faces.append([ii[0], ii[ti], ii[ti + 1]])
                                                        face_map.append(f_idx)

    # Scale fallback points if unique_verts was empty
    if not unique_verts and world_pts:
        for p in world_pts:
            add_point(p)

    if unique_verts:
        xs = [p[0] for p in unique_verts]
        ys = [p[1] for p in unique_verts]
        zs = [p[2] for p in unique_verts]
        bbox = {
            "min_x": min(xs),
            "max_x": max(xs),
            "min_y": min(ys),
            "max_y": max(ys),
            "min_z": min(zs),
            "max_z": max(zs),
        }

        # True 3D surface area: sum triangle areas via cross product
        surface_area_3d = 0.0
        plan_area = 0.0
        for face in faces:
            if len(face) >= 3:
                try:
                    a = np.array(unique_verts[face[0]], dtype=float)
                    b = np.array(unique_verts[face[1]], dtype=float)
                    c = np.array(unique_verts[face[2]], dtype=float)
                    cross = np.cross(b - a, c - a)
                    tri_3d = 0.5 * float(np.linalg.norm(cross))
                    surface_area_3d += tri_3d
                    # Plan area: 2D projection (ignore Z) using cross product Z component
                    plan_area += 0.5 * abs(float(cross[2]))
                except Exception:
                    pass

        # Fallback plan area from polygon footprint if no faces
        if plan_area <= 0.0:
            plan_area = polygon_area_2d([(p[0], p[1]) for p in unique_verts])
        if plan_area <= 0.0:
            plan_area = (bbox["max_x"] - bbox["min_x"]) * (bbox["max_y"] - bbox["min_y"])

        # Fallback 3D area to plan area when no faces (flat element)
        if surface_area_3d <= 0.0:
            surface_area_3d = plan_area

        return {
            "bbox": bbox,
            "area": plan_area,
            "surface_area_3d": surface_area_3d,
            "transform_matrix": placement_matrix.tolist(),
            "vertices": unique_verts,
            "faces": faces,
            "face_map": face_map,
        }

    return {
        "bbox": None,
        "area": 0.0,
        "surface_area_3d": 0.0,
        "transform_matrix": placement_matrix.tolist(),
        "vertices": [],
        "faces": [],
        "face_map": [],
    }

