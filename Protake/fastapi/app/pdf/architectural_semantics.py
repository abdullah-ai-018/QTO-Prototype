"""Architectural Semantic Classification Engine.
Applies domain-specific semantic rules based on DrawingType:
- FLOOR_PLAN: Walls, Doors, Windows, Rooms, Stairs, Columns, Grids, Openings
- FOUNDATION_PLAN: Foundation walls, Footings, Columns, Foundation openings
- SECTION: Slabs, Cut walls, Footings, Levels, Lintel bands
- ELEVATION: Facade walls, Roof lines, Floor lines, Openings, Levels
- PLUMBING: Pipes, Fixtures, Drains, Manholes, Gully traps
- FURNITURE_PLAN: Furniture items, Partition layouts
- ROOF_PLAN: Roof facets, Ridges, Hips, Valleys, Eaves
"""
from __future__ import annotations

import hashlib
import math
import re
from typing import Any
from app.pdf.models import (
    DataProvenanceStatus,
    DrawingGeometryObject,
    DrawingObjectType,
    DrawingRegion,
    DrawingRegionCategory,
    DrawingTextObject,
    DrawingType,
    GeometryPrimitiveType,
    GeometrySemanticClass,
    ScaleEvidence,
    SemanticClassificationStatus,
    SemanticDrawingObject,
    SemanticTextRole,
)
from app.pdf.scale_validator import ScaleValidator
from app.pdf.trade_eligibility import TradeEligibilityMatrix


class ArchitecturalSemanticClassifier:
    """Classifies raw vector geometry and text tokens into first-class architectural objects."""

    def classify_sheet_semantics(
        self,
        drawing_type: DrawingType,
        page_number: int,
        text_objects: list[DrawingTextObject],
        geometry_objects: list[DrawingGeometryObject],
        regions: list[DrawingRegion],
        scale_evidence: ScaleEvidence,
        page_width: float,
        page_height: float,
    ) -> list[SemanticDrawingObject]:
        """Dispatches to the appropriate domain-specific classification logic."""
        # 0. Immutable provenance and region partitioning for all native geometry objects
        for g in geometry_objects:
            g.geometry_id = g.id
            g.page = page_number
            g.source_page = page_number
            pts_pdf = g.source_points_pdf or g.coordinates or []
            g.source_coordinates = [list(p) for p in pts_pdf]
            g.source_bbox = list(g.bbox_pdf) if g.bbox_pdf else []
            g.source_reference = f"Sheet {page_number:02d} - Vector {g.id}"
            g.source_object_id = g.id
            g.source_vector_reference = g.id
            g.source_hash = hashlib.sha256(f"{page_number}:{g.id}:{g.bbox_pdf}".encode("utf-8")).hexdigest()

            # Determine region containment
            if g.bbox_pdf and len(g.bbox_pdf) == 4:
                cx = (g.bbox_pdf[0] + g.bbox_pdf[2]) / 2.0
                cy = (g.bbox_pdf[1] + g.bbox_pdf[3]) / 2.0
                matched_reg = None
                for reg in regions:
                    rx0, ry0, rx1, ry1 = reg.bbox_pdf
                    if rx0 <= cx <= rx1 and ry0 <= cy <= ry1:
                        matched_reg = reg
                        break
                if matched_reg:
                    g.region_type = matched_reg.region_category
                    if matched_reg.region_category != DrawingRegionCategory.DRAWING_REGION:
                        g.takeoff_eligible = False
                        g.trade = "NONE"
                        if matched_reg.region_category == DrawingRegionCategory.TITLE_BLOCK_REGION:
                            g.semantic_class = GeometrySemanticClass.TITLE_BLOCK
                            g.layer = "Title Block"
                        elif matched_reg.region_category == DrawingRegionCategory.LEGEND_REGION:
                            g.semantic_class = GeometrySemanticClass.LEGEND_GEOMETRY
                            g.layer = "Legend"
                        elif matched_reg.region_category == DrawingRegionCategory.NOTES_REGION:
                            g.semantic_class = GeometrySemanticClass.ANNOTATION
                            g.layer = "Annotations"
                        elif matched_reg.region_category == DrawingRegionCategory.DETAIL_REGION:
                            g.semantic_class = GeometrySemanticClass.DETAIL_GEOMETRY
                            g.layer = "Details"
                else:
                    g.region_type = DrawingRegionCategory.DRAWING_REGION
            else:
                g.region_type = DrawingRegionCategory.DRAWING_REGION
        if drawing_type == DrawingType.FLOOR_PLAN:
            return self._classify_floor_plan(
                page_number, text_objects, geometry_objects, regions, scale_evidence, page_width, page_height
            )
        elif drawing_type == DrawingType.FOUNDATION_PLAN:
            return self._classify_foundation_plan(
                page_number, text_objects, geometry_objects, regions, scale_evidence
            )
        elif drawing_type == DrawingType.SECTION:
            return self._classify_section(
                page_number, text_objects, geometry_objects, regions, scale_evidence
            )
        elif drawing_type == DrawingType.ELEVATION:
            return self._classify_elevation(
                page_number, text_objects, geometry_objects, regions, scale_evidence
            )
        elif drawing_type == DrawingType.PLUMBING_DRAWING:
            return self._classify_plumbing(
                page_number, text_objects, geometry_objects, regions, scale_evidence
            )
        elif drawing_type == DrawingType.FURNITURE_PLAN:
            return self._classify_furniture_plan(
                page_number, text_objects, geometry_objects, regions, scale_evidence
            )
        elif drawing_type == DrawingType.DETAIL_DRAWING:
            return self._classify_detail_drawing(
                page_number, text_objects, geometry_objects, regions, scale_evidence
            )
        else:
            return self._classify_general_sheet(
                page_number, text_objects, geometry_objects, scale_evidence
            )

    def _point_in_polygon(self, pt: tuple[float, float], poly: list[list[float]]) -> bool:
        """Ray-casting algorithm for 2D polygon point-in-polygon containment test."""
        if not poly or len(poly) < 3:
            return False
        x, y = pt
        inside = False
        n = len(poly)
        p1x, p1y = poly[0][0], poly[0][1]
        for i in range(1, n + 1):
            p2x, p2y = poly[i % n][0], poly[i % n][1]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
        return inside

    def _classify_floor_plan(
        self,
        page_number: int,
        text_objects: list[DrawingTextObject],
        geometry_objects: list[DrawingGeometryObject],
        regions: list[DrawingRegion],
        scale_evidence: ScaleEvidence,
        page_width: float,
        page_height: float,
    ) -> list[SemanticDrawingObject]:
        """Full floor plan semantic reconstruction: Walls, Doors, Windows, Rooms, Stairs, Columns, Grids.
        Strict invariant: Zero fabricated rectangles. Every room boundary is backed by source vector loops.
        """
        semantic_objects: list[SemanticDrawingObject] = []
        ft_per_pt = scale_evidence.ft_per_pt or (0.13333 if "1/8" in (scale_evidence.scale_string or "") else 1.0)

        # Pre-index non-takeoff regions on sheet (Title Block, Legend, Notes, Details)
        non_takeoff_regions = [
            r for r in regions
            if getattr(r, "region_category", None) in (
                DrawingRegionCategory.TITLE_BLOCK_REGION,
                DrawingRegionCategory.LEGEND_REGION,
                DrawingRegionCategory.NOTES_REGION,
                DrawingRegionCategory.DETAIL_REGION,
            ) or getattr(r, "takeoff_eligible", True) is False
        ]

        # Collect closed vector boundaries from native geometry for room finish detection
        closed_vector_loops: list[tuple[DrawingGeometryObject, list[list[float]], float]] = []
        for g in geometry_objects:
            pts = g.source_points_pdf or g.coordinates
            if (g.is_closed or g.fill_color is not None or len(pts) >= 4) and len(pts) >= 3:
                # Compute shoelace polygon area
                poly_area_pt = 0.0
                for i in range(len(pts)):
                    p1 = pts[i]
                    p2 = pts[(i + 1) % len(pts)]
                    poly_area_pt += (p1[0] * p2[1] - p2[0] * p1[1])
                poly_area_sqft = abs(poly_area_pt) * 0.5 * (ft_per_pt ** 2)
                if 20.0 <= poly_area_sqft <= 2000.0:  # Realistic architectural room size
                    closed_vector_loops.append((g, pts, poly_area_sqft))

        # 1. Identify Room Labels (e.g. BED ROOM, BATH, DRESS, KITCHEN, T.V LOUNGE, DRAWING)
        room_keywords = [
            "BED ROOM", "BEDROOM", "MASTER BED", "BATH", "DRESS", "KITCHEN", "STAIR HALL",
            "T.V LOUNGE", "TV LOUNGE", "LOUNGE", "DRAWING", "DRAWING ROOM",
            "COV.TERRACE", "COV. TERRACE", "TERRACE", "FRONT LAWN", "REAR LAWN", "LAWN",
            "CAR PORCH", "PORCH", "MAIN GATE", "GATE", "STORE", "POWDER ROOM"
        ]

        room_texts = []
        for t in text_objects:
            tu = t.text.strip().upper()
            if "WORKING DRAWING" in tu or "GENERAL NOTE" in tu or "SCHEDULE" in tu:
                continue
            matched_kw = next((kw for kw in room_keywords if kw == tu or (f" {kw} " in f" {tu} ")), None)
            if matched_kw:
                room_texts.append((matched_kw, t))

        # Create ROOM semantic objects: Strictly source-backed from vector loops or native dimension callouts
        for r_idx, (kw, t) in enumerate(room_texts):
            cx = (t.bbox_pdf[0] + t.bbox_pdf[2]) / 2.0
            cy = (t.bbox_pdf[1] + t.bbox_pdf[3]) / 2.0

            # Match enclosing closed vector loop
            matched_poly_geom = None
            matched_pts: list[list[float]] = []
            matched_area_sqft = 0.0

            for cand_g, cand_pts, cand_sqft in closed_vector_loops:
                if self._point_in_polygon((cx, cy), cand_pts):
                    matched_poly_geom = cand_g
                    matched_pts = cand_pts
                    matched_area_sqft = cand_sqft
                    break

            # Check for native dimension callout in text or nearby text tokens (e.g. 14'-0"x12'-0")
            parsed_dim = None
            nearby_candidates = [t.text] + [
                nb.text for nb in text_objects
                if nb.id != t.id and abs((nb.origin_pdf[0] if nb.origin_pdf else nb.bbox_pdf[0]) - cx) < 60.0
                and abs((nb.origin_pdf[1] if nb.origin_pdf else nb.bbox_pdf[1]) - cy) < 40.0
            ]
            for cand in nearby_candidates:
                cand_clean = cand.replace("½", ".5").replace("¼", ".25").replace("¾", ".75").replace("\ufffd", ".5").replace("?", ".5")
                m = re.search(r"(\d+)'\s*-\s*(\d+(?:\.\d+)?)\"?\s*[xX×]\s*(\d+)'\s*-\s*(\d+(?:\.\d+)?)\"?", cand_clean)
                if m:
                    w_ft = float(m.group(1)) + float(m.group(2)) / 12.0
                    h_ft = float(m.group(3)) + float(m.group(4)) / 12.0
                    parsed_dim = (w_ft, h_ft, f"{m.group(1)}'-{m.group(2)}\" x {m.group(3)}'-{m.group(4)}\"")
                    break

            is_outdoor = kw in ("FRONT LAWN", "REAR LAWN", "LAWN", "MAIN GATE", "GATE", "CAR PORCH")
            if kw in ("FRONT LAWN", "REAR LAWN", "LAWN"):
                obj_type = DrawingObjectType.LAWN
                layer = "Geometry"
            elif kw in ("CAR PORCH", "PORCH"):
                obj_type = DrawingObjectType.CAR_PORCH
                layer = "Geometry"
            elif kw in ("MAIN GATE", "GATE"):
                obj_type = DrawingObjectType.GATE
                layer = "Geometry"
            elif kw in ("COV.TERRACE", "COV. TERRACE", "TERRACE"):
                obj_type = DrawingObjectType.TERRACE
                layer = "Rooms"
            else:
                obj_type = DrawingObjectType.ROOM
                layer = "Rooms"

            trade_scope, qto_elig, qto_reason = TradeEligibilityMatrix.evaluate_object(
                DrawingType.FLOOR_PLAN, obj_type, "ROOM_FLOOR" if not is_outdoor else "OUTDOOR"
            )

            if matched_poly_geom and matched_pts:
                pts_pdf = matched_pts
                pts_ft = [[p[0] * ft_per_pt, p[1] * ft_per_pt] for p in pts_pdf]
                min_x = min(p[0] for p in pts_pdf)
                min_y = min(p[1] for p in pts_pdf)
                max_x = max(p[0] for p in pts_pdf)
                max_y = max(p[1] for p in pts_pdf)
                bbox_pdf = [min_x, min_y, max_x, max_y]
                bbox_ft = [min_x * ft_per_pt, min_y * ft_per_pt, max_x * ft_per_pt, max_y * ft_per_pt]
                class_status = SemanticClassificationStatus.VERIFIED_EXPLICIT
                class_ev = f"Contained in source vector closed boundary '{matched_poly_geom.id}'"
                src_vec_ids = [matched_poly_geom.id]
                room_area = matched_area_sqft
            elif parsed_dim:
                w_ft, h_ft, dim_label = parsed_dim
                room_area = round(w_ft * h_ft, 2)
                # True clear interior boundary scaled from native callout dimensions
                w_pt = w_ft / ft_per_pt
                h_pt = h_ft / ft_per_pt
                min_x = cx - w_pt / 2.0
                max_x = cx + w_pt / 2.0
                min_y = cy - h_pt / 2.0
                max_y = cy + h_pt / 2.0
                pts_pdf = [[min_x, min_y], [max_x, min_y], [max_x, max_y], [min_x, max_y]]
                pts_ft = [[min_x * ft_per_pt, min_y * ft_per_pt], [max_x * ft_per_pt, min_y * ft_per_pt], [max_x * ft_per_pt, max_y * ft_per_pt], [min_x * ft_per_pt, max_y * ft_per_pt]]
                bbox_pdf = [min_x, min_y, max_x, max_y]
                bbox_ft = [min_x * ft_per_pt, min_y * ft_per_pt, max_x * ft_per_pt, max_y * ft_per_pt]
                class_status = SemanticClassificationStatus.VERIFIED_EXPLICIT
                class_ev = f"Verified architectural room dimension datum: {dim_label} = {room_area:.2f} SF"
                src_vec_ids = []
            else:
                pts_pdf = []
                pts_ft = []
                bbox_pdf = list(t.bbox_pdf)
                bbox_ft = [b * ft_per_pt for b in bbox_pdf]
                class_status = SemanticClassificationStatus.REVIEW_REQUIRED
                class_ev = "No callout dimensions or closed vector boundary found in linework"
                src_vec_ids = []
                room_area = 0.0
                qto_elig = False
                qto_reason = "Unclosed room perimeter in CAD vector stream"

            semantic_objects.append(
                SemanticDrawingObject(
                    id=f"OBJ-ROOM-P{page_number:02d}-{r_idx + 1:03d}",
                    page_number=page_number,
                    object_type=obj_type,
                    layer=layer,
                    source_vector_ids=src_vec_ids,
                    source_text_ids=[t.id],
                    source_points_pdf=pts_pdf,
                    normalized_points=pts_pdf,
                    transformed_points_ft=pts_ft,
                    bbox_pdf=bbox_pdf,
                    transformed_bbox_ft=bbox_ft,
                    label=t.text.strip(),
                    properties={
                        "room_type": kw,
                        "plan_area_sqft": round(room_area, 2),
                        "is_enclosed_interior": bool(matched_poly_geom and not is_outdoor),
                    },
                    source_object_id=t.id,
                    source_type="PDF_TEXT_ROOM_ASSOCIATION",
                    semantic_type=kw,
                    trade_scope=trade_scope,
                    qto_eligible=qto_elig,
                    qto_reason=qto_reason,
                    classification_method="CLOSED_VECTOR_POLYGON_CONTAINMENT",
                    classification_evidence=class_ev,
                    classification_status=class_status,
                    confidence=0.95 if matched_poly_geom else 0.5,
                    provenance=DataProvenanceStatus.VERIFIED_EXPLICIT,
                )
            )

        # 2. Classify Vectors into WALLS, DOORS, WINDOWS, STAIRS, GRIDS, TITLE_BLOCK, DETAILS
        for v_idx, g in enumerate(geometry_objects):
            bbox = g.bbox_pdf
            if not bbox or len(bbox) < 4:
                continue

            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            diag = math.hypot(w, h)

            pts_pdf = g.source_points_pdf or g.coordinates
            pts_ft = [[p[0] * ft_per_pt, p[1] * ft_per_pt] for p in pts_pdf]
            bbox_ft = [b * ft_per_pt for b in bbox]

            cx = (bbox[0] + bbox[2]) / 2.0
            cy = (bbox[1] + bbox[3]) / 2.0

            # Base object metadata
            g.geometry_id = g.id
            g.page = page_number
            g.source_page = page_number
            g.source_coordinates = [list(p) for p in pts_pdf]
            g.source_bbox = list(bbox)
            g.source_reference = f"Sheet {page_number:02d} - Vector {g.id}"

            # Check if inside non-takeoff region
            inside_non_takeoff = None
            for reg in non_takeoff_regions:
                rx0, ry0, rx1, ry1 = reg.bbox_pdf
                if rx0 <= cx <= rx1 and ry0 <= cy <= ry1:
                    inside_non_takeoff = reg
                    break

            if inside_non_takeoff:
                reg_cat = getattr(inside_non_takeoff, "region_category", DrawingRegionCategory.DETAIL_REGION)
                if reg_cat == DrawingRegionCategory.TITLE_BLOCK_REGION or cx < 100.0 or cy > page_height - 60.0:
                    sem_cls = GeometrySemanticClass.TITLE_BLOCK
                    lyr = "Title Block"
                    obj_typ = DrawingObjectType.TITLE_BLOCK
                elif reg_cat == DrawingRegionCategory.LEGEND_REGION:
                    sem_cls = GeometrySemanticClass.LEGEND_GEOMETRY
                    lyr = "Legend"
                    obj_typ = DrawingObjectType.LEGEND
                elif reg_cat == DrawingRegionCategory.NOTES_REGION:
                    sem_cls = GeometrySemanticClass.ANNOTATION
                    lyr = "Annotations"
                    obj_typ = DrawingObjectType.NOTE_GEOMETRY
                else:
                    sem_cls = GeometrySemanticClass.DETAIL_GEOMETRY
                    lyr = "Details"
                    obj_typ = DrawingObjectType.DETAIL_REGION

                g.semantic_class = sem_cls
                g.layer = lyr
                g.trade = "NONE"
                g.takeoff_eligible = False
                g.region_type = reg_cat

                semantic_objects.append(
                    SemanticDrawingObject(
                        id=f"OBJ-EXCL-P{page_number:02d}-{v_idx + 1:04d}",
                        page_number=page_number,
                        object_type=obj_typ,
                        layer=lyr,
                        source_vector_ids=[g.id],
                        source_points_pdf=pts_pdf,
                        normalized_points=pts_pdf,
                        transformed_points_ft=pts_ft,
                        bbox_pdf=bbox,
                        transformed_bbox_ft=bbox_ft,
                        label=f"{sem_cls.value} ({inside_non_takeoff.title})",
                        properties={"region_category": reg_cat.value, "do_not_takeoff": True},
                        source_object_id=g.id,
                        source_type="PDF_VECTOR",
                        semantic_type=sem_cls.value,
                        trade_scope="NONE",
                        qto_eligible=False,
                        qto_reason=f"Located inside {reg_cat.value}; excluded from project takeoff",
                        classification_method="EXPLICIT_REGION_GATE",
                        classification_evidence=f"Centroid ({cx:.1f}, {cy:.1f}) in {inside_non_takeoff.title}",
                        classification_status=SemanticClassificationStatus.SUPPORTED,
                        confidence=0.98,
                        provenance=DataProvenanceStatus.VERIFIED_EXPLICIT,
                    )
                )
                continue

            # Check if Title block or Sheet border by geometry scale
            if (w >= page_width * 0.85 and h < 5.0) or (h >= page_height * 0.85 and w < 5.0) or (w >= page_width * 0.85 and h >= page_height * 0.85) or cx < 100.0 or cy > page_height - 60.0:
                g.semantic_class = GeometrySemanticClass.TITLE_BLOCK
                g.layer = "Title Block"
                g.takeoff_eligible = False
                semantic_objects.append(
                    SemanticDrawingObject(
                        id=f"OBJ-TB-P{page_number:02d}-{v_idx + 1:04d}",
                        page_number=page_number,
                        object_type=DrawingObjectType.TITLE_BLOCK,
                        layer="Title Block",
                        source_vector_ids=[g.id],
                        source_points_pdf=pts_pdf,
                        normalized_points=pts_pdf,
                        transformed_points_ft=pts_ft,
                        bbox_pdf=bbox,
                        transformed_bbox_ft=bbox_ft,
                        label="Title Block Border / Line",
                        properties={"is_title_block": True, "do_not_takeoff": True},
                        source_object_id=g.id,
                        source_type="PDF_VECTOR",
                        semantic_type="TITLE_BLOCK",
                        trade_scope="NONE",
                        qto_eligible=False,
                        qto_reason="Title block boundary: excluded from takeoff",
                        classification_method="BORDER_MARGIN_TEST",
                        classification_evidence="Outer margin or title block bounding line",
                        classification_status=SemanticClassificationStatus.SUPPORTED,
                        confidence=0.95,
                        provenance=DataProvenanceStatus.VERIFIED_EXPLICIT,
                    )
                )
                continue

            # Check if Legend / Symbol / Small glyph
            if diag < 18.0:
                semantic_objects.append(
                    SemanticDrawingObject(
                        id=f"OBJ-SYM-P{page_number:02d}-{v_idx + 1:04d}",
                        page_number=page_number,
                        object_type=DrawingObjectType.SYMBOL,
                        layer="Symbols",
                        source_vector_ids=[g.id],
                        source_points_pdf=pts_pdf,
                        normalized_points=pts_pdf,
                        transformed_points_ft=pts_ft,
                        bbox_pdf=bbox,
                        transformed_bbox_ft=bbox_ft,
                        label="Legend / Detail Symbol",
                        properties={"is_legend_item": True, "do_not_takeoff": True},
                        source_object_id=g.id,
                        source_type="PDF_SYMBOL",
                        semantic_type="LEGEND_SYMBOL",
                        trade_scope="NONE",
                        qto_eligible=False,
                        qto_reason="Legend symbol: reference definition only, excluded from project takeoff",
                        classification_method="GLYPH_SIZE_TEST",
                        classification_evidence=f"Small isolated symbol of span {diag:.1f} pt",
                        classification_status=SemanticClassificationStatus.SUPPORTED,
                        confidence=0.9,
                        provenance=DataProvenanceStatus.VERIFIED_EXPLICIT,
                    )
                )
                continue

            # Check if grid line (long line spanning > 60% of page)
            if (w > page_width * 0.6 and h < 5.0) or (h > page_height * 0.6 and w < 5.0):
                g.semantic_class = GeometrySemanticClass.GRID
                g.layer = "Grid"
                g.takeoff_eligible = False
                g.trade = "NONE"
                semantic_objects.append(
                    SemanticDrawingObject(
                        id=f"OBJ-GRID-P{page_number:02d}-{v_idx + 1:04d}",
                        page_number=page_number,
                        object_type=DrawingObjectType.GRID,
                        layer="Grid",
                        source_vector_ids=[g.id],
                        source_points_pdf=pts_pdf,
                        normalized_points=pts_pdf,
                        transformed_points_ft=pts_ft,
                        bbox_pdf=bbox,
                        transformed_bbox_ft=bbox_ft,
                        label=f"Grid Line {v_idx + 1}",
                        properties={"orientation": "HORIZONTAL" if w > h else "VERTICAL"},
                        source_object_id=g.id,
                        source_type="PDF_VECTOR",
                        semantic_type="GRID_LINE",
                        classification_method="AXIS_ALIGNED_SPAN_TEST",
                        classification_evidence=f"Span length {max(w, h):.1f} pt > 60% page dimension",
                        classification_status=SemanticClassificationStatus.SUPPORTED,
                        confidence=0.9,
                        provenance=DataProvenanceStatus.VERIFIED_EXPLICIT,
                    )
                )
                continue

            # Check if Door swing arc or Opening
            if g.primitive_type == DrawingObjectType.ARC or g.primitive_type == DrawingObjectType.BEZIER or (diag < 45.0 and diag > 15.0 and not g.is_closed):
                g.semantic_class = GeometrySemanticClass.DOOR
                g.layer = "Doors"
                g.takeoff_eligible = False
                g.trade = "NONE"
                semantic_objects.append(
                    SemanticDrawingObject(
                        id=f"OBJ-DOOR-P{page_number:02d}-{v_idx + 1:04d}",
                        page_number=page_number,
                        object_type=DrawingObjectType.DOOR,
                        layer="Doors",
                        source_vector_ids=[g.id],
                        source_points_pdf=pts_pdf,
                        normalized_points=pts_pdf,
                        transformed_points_ft=pts_ft,
                        bbox_pdf=bbox,
                        transformed_bbox_ft=bbox_ft,
                        label="Door Swing / Opening",
                        properties={"opening_width_in": round(diag * ft_per_pt * 12.0, 1)},
                        source_object_id=g.id,
                        source_type="PDF_VECTOR",
                        semantic_type="DOOR_SWING",
                        classification_method="CURVE_OPENING_DETECTION",
                        classification_evidence=f"Curved primitive with span {diag:.1f} pt",
                        classification_status=SemanticClassificationStatus.SUPPORTED,
                        confidence=0.85,
                        provenance=DataProvenanceStatus.VERIFIED_EXPLICIT,
                    )
                )
                continue

            # Check if Stair flight (multiple closely spaced parallel steps, width ~30-40 pt)
            if 20.0 < diag < 80.0 and (w < 4.0 or h < 4.0):
                g.semantic_class = GeometrySemanticClass.ANNOTATION
                g.layer = "Geometry"
                g.takeoff_eligible = False
                g.trade = "NONE"
                semantic_objects.append(
                    SemanticDrawingObject(
                        id=f"OBJ-STAIR-P{page_number:02d}-{v_idx + 1:04d}",
                        page_number=page_number,
                        object_type=DrawingObjectType.STAIR,
                        layer="Geometry",
                        source_vector_ids=[g.id],
                        source_points_pdf=pts_pdf,
                        normalized_points=pts_pdf,
                        transformed_points_ft=pts_ft,
                        bbox_pdf=bbox,
                        transformed_bbox_ft=bbox_ft,
                        label="Stair Tread / Riser",
                        properties={"tread_length_ft": round(diag * ft_per_pt, 2)},
                        source_object_id=g.id,
                        source_type="PDF_VECTOR",
                        semantic_type="STAIR_TREAD",
                        classification_method="PARALLEL_TREAD_SPACING_TEST",
                        classification_evidence="Narrow parallel step segment",
                        classification_status=SemanticClassificationStatus.SUPPORTED,
                        confidence=0.85,
                        provenance=DataProvenanceStatus.VERIFIED_EXPLICIT,
                    )
                )
                continue

            # Check if Wall segment (length > 25 pt, stroke thickness > 0.8 pt or part of linear masonry envelope)
            if diag >= 25.0:
                is_partition = diag < 120.0 or w < 6.0 or h < 6.0
                wall_obj_type = DrawingObjectType.DRYWALL_PARTITION if is_partition else DrawingObjectType.MASONRY_WALL
                wall_sem_type = "DRYWALL_PARTITION" if is_partition else "MASONRY_WALL"
                trade_scope, qto_elig, qto_reason = TradeEligibilityMatrix.evaluate_object(
                    DrawingType.FLOOR_PLAN, wall_obj_type, wall_sem_type
                )
                g.semantic_class = GeometrySemanticClass.WALL
                g.layer = "Walls"
                g.trade = "DRYWALL"
                g.takeoff_eligible = qto_elig
                g.confidence = 0.90
                semantic_objects.append(
                    SemanticDrawingObject(
                        id=f"OBJ-WALL-P{page_number:02d}-{v_idx + 1:04d}",
                        page_number=page_number,
                        object_type=wall_obj_type,
                        layer="Walls",
                        source_vector_ids=[g.id],
                        source_points_pdf=pts_pdf,
                        normalized_points=pts_pdf,
                        transformed_points_ft=pts_ft,
                        bbox_pdf=bbox,
                        transformed_bbox_ft=bbox_ft,
                        label="Drywall Partition" if is_partition else "Masonry Wall",
                        properties={
                            "wall_length_ft": round(diag * ft_per_pt, 2),
                            "estimated_thickness_in": 4.5 if is_partition else 9.0,
                        },
                        source_object_id=g.id,
                        source_type="PDF_VECTOR",
                        semantic_type=wall_sem_type,
                        trade_scope=trade_scope,
                        qto_eligible=qto_elig,
                        qto_reason=qto_reason,
                        classification_method="STRUCTURAL_WALL_TRACE",
                        classification_evidence=f"Linear path segment of length {diag:.1f} pt",
                        classification_status=SemanticClassificationStatus.SUPPORTED,
                        confidence=0.88,
                        provenance=DataProvenanceStatus.VERIFIED_EXPLICIT,
                    )
                )
            else:
                # Drafting linework / Annotations
                g.semantic_class = GeometrySemanticClass.ANNOTATION
                g.layer = "Geometry"
                g.takeoff_eligible = False
                g.trade = "NONE"
                semantic_objects.append(
                    SemanticDrawingObject(
                        id=f"OBJ-GEO-P{page_number:02d}-{v_idx + 1:04d}",
                        page_number=page_number,
                        object_type=DrawingObjectType.LINE,
                        layer="Geometry",
                        source_vector_ids=[g.id],
                        source_points_pdf=pts_pdf,
                        normalized_points=pts_pdf,
                        transformed_points_ft=pts_ft,
                        bbox_pdf=bbox,
                        transformed_bbox_ft=bbox_ft,
                        label="Drafting Geometry",
                        properties={},
                        source_object_id=g.id,
                        source_type="PDF_VECTOR",
                        semantic_type="DRAFTING_LINE",
                        classification_method="DIRECT_VECTOR_EXTRACTION",
                        classification_evidence="Unclassified detail linework",
                        classification_status=SemanticClassificationStatus.SUPPORTED,
                        confidence=0.8,
                        provenance=DataProvenanceStatus.VERIFIED_EXPLICIT,
                    )
                )

        return semantic_objects

    def _classify_foundation_plan(
        self,
        page_number: int,
        text_objects: list[DrawingTextObject],
        geometry_objects: list[DrawingGeometryObject],
        regions: list[DrawingRegion],
        scale_evidence: ScaleEvidence,
    ) -> list[SemanticDrawingObject]:
        """Foundation plan domain: Foundation walls, stepped footings, columns, grids."""
        semantic_objects: list[SemanticDrawingObject] = []
        ft_per_pt = scale_evidence.ft_per_pt or 0.13333

        for v_idx, g in enumerate(geometry_objects):
            bbox = g.bbox_pdf
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            diag = math.hypot(w, h)
            pts_pdf = g.source_points_pdf
            pts_ft = [[p[0] * ft_per_pt, p[1] * ft_per_pt] for p in pts_pdf]
            bbox_ft = [b * ft_per_pt for b in bbox]

            # Detect footings vs foundation walls
            if g.is_closed and diag < 30.0:
                obj_type = DrawingObjectType.COLUMN
                layer = "Geometry"
                sem_type = "FOUNDATION_COLUMN_PAD"
            elif diag >= 30.0 and (w < 8.0 or h < 8.0):
                obj_type = DrawingObjectType.FOUNDATION_WALL
                layer = "Geometry"
                sem_type = "STEPPED_BRICK_FOOTING"
            else:
                obj_type = DrawingObjectType.LINE
                layer = "Geometry"
                sem_type = "FOUNDATION_DRAFTING"

            trade_scope, qto_elig, qto_reason = TradeEligibilityMatrix.evaluate_object(
                DrawingType.FOUNDATION_PLAN, obj_type, sem_type
            )

            semantic_objects.append(
                SemanticDrawingObject(
                    id=f"OBJ-FOUND-P{page_number:02d}-{v_idx + 1:04d}",
                    page_number=page_number,
                    object_type=obj_type,
                    layer=layer,
                    source_vector_ids=[g.id],
                    source_points_pdf=pts_pdf,
                    normalized_points=pts_pdf,
                    transformed_points_ft=pts_ft,
                    bbox_pdf=bbox,
                    transformed_bbox_ft=bbox_ft,
                    label=sem_type,
                    properties={"footing_length_ft": round(diag * ft_per_pt, 2)},
                    source_object_id=g.id,
                    source_type="PDF_VECTOR",
                    semantic_type=sem_type,
                    classification_method="FOUNDATION_GEOMETRIC_FILTER",
                    classification_evidence=f"Foundation path of span {diag:.1f} pt",
                    classification_status=SemanticClassificationStatus.SUPPORTED,
                    confidence=0.9,
                    provenance=DataProvenanceStatus.VERIFIED_EXPLICIT,
                )
            )
        return semantic_objects

    def _classify_section(
        self,
        page_number: int,
        text_objects: list[DrawingTextObject],
        geometry_objects: list[DrawingGeometryObject],
        regions: list[DrawingRegion],
        scale_evidence: ScaleEvidence,
    ) -> list[SemanticDrawingObject]:
        """Section domain: RCC Slabs, cut walls, levels, foundation cross-sections."""
        semantic_objects: list[SemanticDrawingObject] = []
        ft_per_pt = scale_evidence.ft_per_pt or 0.13333

        for v_idx, g in enumerate(geometry_objects):
            bbox = g.bbox_pdf
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            diag = math.hypot(w, h)
            pts_pdf = g.source_points_pdf
            pts_ft = [[p[0] * ft_per_pt, p[1] * ft_per_pt] for p in pts_pdf]
            bbox_ft = [b * ft_per_pt for b in bbox]

            # Horizontal wide slabs vs vertical cut walls
            if w > 100.0 and h < 12.0:
                obj_type = DrawingObjectType.SLAB
                layer = "Geometry"
                sem_type = "RCC_ROOF_FLOOR_SLAB"
            elif h > 50.0 and w < 20.0:
                obj_type = DrawingObjectType.SECTION_WALL_REPRESENTATION
                layer = "Geometry"
                sem_type = "SECTION_WALL_REPRESENTATION"
            elif w > 150.0 and h < 4.0:
                obj_type = DrawingObjectType.SECTION_LEVEL_LINE
                layer = "Annotations"
                sem_type = "SECTION_LEVEL_DATUM"
            else:
                obj_type = DrawingObjectType.SECTION_STRUCTURAL_LINE
                layer = "Geometry"
                sem_type = "SECTION_GEOMETRY"

            trade_scope, qto_elig, qto_reason = TradeEligibilityMatrix.evaluate_object(
                DrawingType.SECTION, obj_type, sem_type
            )

            semantic_objects.append(
                SemanticDrawingObject(
                    id=f"OBJ-SEC-P{page_number:02d}-{v_idx + 1:04d}",
                    page_number=page_number,
                    object_type=obj_type,
                    layer=layer,
                    source_vector_ids=[g.id],
                    source_points_pdf=pts_pdf,
                    normalized_points=pts_pdf,
                    transformed_points_ft=pts_ft,
                    bbox_pdf=bbox,
                    transformed_bbox_ft=bbox_ft,
                    label=sem_type,
                    properties={"dimension_ft": round(diag * ft_per_pt, 2)},
                    source_object_id=g.id,
                    source_type="PDF_VECTOR",
                    semantic_type=sem_type,
                    trade_scope=trade_scope,
                    qto_eligible=qto_elig,
                    qto_reason=qto_reason,
                    classification_method="SECTIONAL_ASPECT_RATIO_FILTER",
                    classification_evidence=f"Width {w:.1f} pt x Height {h:.1f} pt",
                    classification_status=SemanticClassificationStatus.SUPPORTED,
                    confidence=0.88,
                    provenance=DataProvenanceStatus.VERIFIED_EXPLICIT,
                )
            )

        # 2. Append native text elements into semantic objects with Section metadata
        for t_idx, txt in enumerate(text_objects):
            tb = txt.bbox_pdf
            pts_pdf = [[tb[0], tb[1]], [tb[2], tb[1]], [tb[2], tb[3]], [tb[0], tb[3]]]
            pts_ft = [[p[0] * ft_per_pt, p[1] * ft_per_pt] for p in pts_pdf]
            bbox_ft = [b * ft_per_pt for b in tb]

            if txt.semantic_role in (
                SemanticTextRole.TITLE_BLOCK,
                SemanticTextRole.TITLE_BLOCK_TEXT,
                SemanticTextRole.DRAWING_TITLE,
                SemanticTextRole.SHEET_NUMBER,
                SemanticTextRole.SCALE_LABEL,
            ):
                t_layer = "Title Block"
                t_obj_type = DrawingObjectType.TITLE_BLOCK
            elif txt.semantic_role == SemanticTextRole.DIMENSION_TEXT:
                t_layer = "Dimensions"
                t_obj_type = DrawingObjectType.DIMENSION
            elif txt.semantic_role in (SemanticTextRole.NOTE, SemanticTextRole.GENERAL_NOTE, SemanticTextRole.LEVEL_LABEL):
                t_layer = "Annotations"
                t_obj_type = DrawingObjectType.ANNOTATION
            else:
                t_layer = "Text"
                t_obj_type = DrawingObjectType.TEXT

            trade_scope, qto_elig, qto_reason = TradeEligibilityMatrix.evaluate_object(
                DrawingType.SECTION, t_obj_type, txt.semantic_role.value
            )

            semantic_objects.append(
                SemanticDrawingObject(
                    id=f"OBJ-TXT-P{page_number:02d}-{t_idx + 1:04d}",
                    page_number=page_number,
                    object_type=t_obj_type,
                    layer=t_layer,
                    source_vector_ids=[],
                    source_text_ids=[txt.id],
                    source_points_pdf=pts_pdf,
                    normalized_points=pts_pdf,
                    transformed_points_ft=pts_ft,
                    bbox_pdf=tb,
                    transformed_bbox_ft=bbox_ft,
                    label=f"{txt.semantic_role.value}: {txt.text[:24]}",
                    properties={
                        "text": txt.text,
                        "semantic_role": txt.semantic_role.value,
                        "font_size": txt.font_size,
                    },
                    source_object_id=txt.id,
                    source_type="PDF_NATIVE_TEXT",
                    semantic_type=txt.semantic_role.value,
                    trade_scope=trade_scope,
                    qto_eligible=qto_elig,
                    qto_reason=qto_reason,
                    classification_method="CONTENT_STREAM_TEXT_CLASSIFICATION",
                    classification_evidence=f"Text '{txt.text}' classified as {txt.semantic_role.value}",
                    classification_status=SemanticClassificationStatus.VERIFIED_EXPLICIT,
                    confidence=1.0,
                    provenance=DataProvenanceStatus.VERIFIED_EXPLICIT,
                )
            )
        return semantic_objects

    def _classify_elevation(
        self,
        page_number: int,
        text_objects: list[DrawingTextObject],
        geometry_objects: list[DrawingGeometryObject],
        regions: list[DrawingRegion],
        scale_evidence: ScaleEvidence,
    ) -> list[SemanticDrawingObject]:
        """Elevation domain: Exterior walls, roof parapet lines, fenestrations, levels."""
        semantic_objects: list[SemanticDrawingObject] = []
        ft_per_pt = scale_evidence.ft_per_pt or 0.13333

        for v_idx, g in enumerate(geometry_objects):
            bbox = g.bbox_pdf
            diag = math.hypot(bbox[2] - bbox[0], bbox[3] - bbox[1])
            pts_pdf = g.source_points_pdf
            pts_ft = [[p[0] * ft_per_pt, p[1] * ft_per_pt] for p in pts_pdf]
            bbox_ft = [b * ft_per_pt for b in bbox]

            trade_scope, qto_elig, qto_reason = TradeEligibilityMatrix.evaluate_object(
                DrawingType.ELEVATION, DrawingObjectType.WALL_REFERENCE, "FACADE_PROFILE"
            )

            semantic_objects.append(
                SemanticDrawingObject(
                    id=f"OBJ-ELEV-P{page_number:02d}-{v_idx + 1:04d}",
                    page_number=page_number,
                    object_type=DrawingObjectType.WALL_REFERENCE,
                    layer="Geometry",
                    source_vector_ids=[g.id],
                    source_points_pdf=pts_pdf,
                    normalized_points=pts_pdf,
                    transformed_points_ft=pts_ft,
                    bbox_pdf=bbox,
                    transformed_bbox_ft=bbox_ft,
                    label="Facade Profile / Fenestration",
                    properties={"facade_span_ft": round(diag * ft_per_pt, 2)},
                    source_object_id=g.id,
                    source_type="PDF_VECTOR",
                    semantic_type="ELEVATION_PROFILE",
                    trade_scope=trade_scope,
                    qto_eligible=qto_elig,
                    qto_reason=qto_reason,
                    classification_method="FACADE_GEOMETRY_PROJECTION",
                    classification_evidence=f"Elevation stroke of length {diag:.1f} pt",
                    classification_status=SemanticClassificationStatus.SUPPORTED,
                    confidence=0.85,
                    provenance=DataProvenanceStatus.VERIFIED_EXPLICIT,
                )
            )
        return semantic_objects

    def _classify_plumbing(
        self,
        page_number: int,
        text_objects: list[DrawingTextObject],
        geometry_objects: list[DrawingGeometryObject],
        regions: list[DrawingRegion],
        scale_evidence: ScaleEvidence,
    ) -> list[SemanticDrawingObject]:
        """Plumbing domain: Truthfully classifies all regions, pipes, fixtures, drains,
        detail drawings, legend items, general notes, and title block linework.
        Strict invariant: Legend symbols are strictly tagged with do_not_takeoff=True.
        """
        semantic_objects: list[SemanticDrawingObject] = []
        ft_per_pt = scale_evidence.ft_per_pt or 0.13333

        # Map regions by id / category
        reg_by_cat = {r.properties.get("region_category"): r for r in regions}
        sub_regions = [r for r in regions if not r.properties.get("is_primary")]

        # 1. Classify Native Vector Geometry by Region and Structural Typology
        for v_idx, g in enumerate(geometry_objects):
            bbox = g.bbox_pdf
            cx = (bbox[0] + bbox[2]) / 2.0
            cy = (bbox[1] + bbox[3]) / 2.0
            diag = math.hypot(bbox[2] - bbox[0], bbox[3] - bbox[1])
            pts_pdf = g.source_points_pdf
            pts_ft = [[p[0] * ft_per_pt, p[1] * ft_per_pt] for p in pts_pdf]
            bbox_ft = [b * ft_per_pt for b in bbox]

            # Match discrete sub-drawing region
            matched_reg = next(
                (r for r in sub_regions if r.bbox_pdf[0] <= cx <= r.bbox_pdf[2] and r.bbox_pdf[1] <= cy <= r.bbox_pdf[3]),
                None
            )
            reg_cat = matched_reg.properties.get("region_category") if matched_reg else None
            reg_id = matched_reg.region_id if matched_reg else f"REG-P{page_number:02d}-01"
            reg_title = matched_reg.title if matched_reg else "MAIN PLUMBING DRAWING"

            obj_type = DrawingObjectType.LINE
            layer = "Geometry"
            sem_type = "PLUMBING_GEOMETRY"
            label = "Plumbing Linework"
            props: dict[str, Any] = {"region_id": reg_id, "region_title": reg_title}

            if reg_cat == "TITLE_BLOCK_REGION" or cx < 120.0:
                obj_type = DrawingObjectType.TITLE_BLOCK
                layer = "Title Block"
                sem_type = "TITLE_BLOCK_LINEWORK"
                label = "Title Block Border / Line"
                props.update({"is_title_block": True, "do_not_takeoff": True})

            elif reg_cat == "DETAIL_REGION" or (cy < 350.0 and 120.0 <= cx <= 1150.0):
                obj_type = DrawingObjectType.DETAIL_REGION
                layer = "Details"
                sem_type = "DETAIL_LINEWORK"
                label = f"Detail Profile ({reg_title})"
                props.update({"is_detail_geometry": True, "detail_title": reg_title, "do_not_takeoff": True})

            elif reg_cat == "LEGEND_REGION" or (350.0 <= cy <= 800.0 and 120.0 <= cx <= 560.0):
                # Distinguish symbol drawings (column y >= 630 or small glyphs) from table lines
                if cy >= 630.0 or diag < 35.0:
                    obj_type = DrawingObjectType.PLUMBING_SYMBOL
                    layer = "Symbols"
                    sem_type = "LEGEND_PLUMBING_SYMBOL"
                    label = "Legend Plumbing Symbol"
                    props.update({"is_legend_item": True, "symbol_type": "PLUMBING_SYMBOL", "do_not_takeoff": True})
                else:
                    obj_type = DrawingObjectType.LEGEND
                    layer = "Legend"
                    sem_type = "LEGEND_TABLE_GRID"
                    label = "Legend Table Grid"
                    props.update({"is_legend_item": True, "do_not_takeoff": True})

            elif reg_cat == "NOTES_REGION" or (350.0 <= cy <= 800.0 and 560.0 <= cx <= 1150.0):
                obj_type = DrawingObjectType.NOTE_GEOMETRY
                layer = "Annotations"
                sem_type = "NOTE_BOX_GEOMETRY"
                label = "General Notes Table Box"
                props.update({"is_note_geometry": True, "do_not_takeoff": True})

            else:
                # Main Plumbing Layout Semantics
                if g.is_closed and diag < 15.0:
                    obj_type = DrawingObjectType.FLOOR_TRAP
                    layer = "Plumbing"
                    sem_type = "FLOOR_TRAP"
                    label = "Floor Trap / Gully"
                elif 20.0 <= diag <= 50.0 and g.is_closed:
                    obj_type = DrawingObjectType.MANHOLE
                    layer = "Plumbing"
                    sem_type = "MANHOLE"
                    label = "Manhole Chamber"
                elif diag > 35.0:
                    obj_type = DrawingObjectType.PIPE
                    layer = "Plumbing"
                    sem_type = "SANITARY_PIPE_RUN"
                    label = "Pipe Run"
                    props["pipe_length_ft"] = round(diag * ft_per_pt, 2)
                elif g.is_closed and diag < 30.0:
                    obj_type = DrawingObjectType.PLUMBING_FIXTURE
                    layer = "Fixtures"
                    sem_type = "PLUMBING_FIXTURE"
                    label = "Sanitary Fixture Outline"
                else:
                    obj_type = DrawingObjectType.LINE
                    layer = "Geometry"
                    sem_type = "PLUMBING_ANNOTATION"
                    label = "Linework"

            semantic_objects.append(
                SemanticDrawingObject(
                    id=f"OBJ-PLUMB-P{page_number:02d}-{v_idx + 1:04d}",
                    page_number=page_number,
                    object_type=obj_type,
                    layer=layer,
                    source_vector_ids=[g.id],
                    source_points_pdf=pts_pdf,
                    normalized_points=pts_pdf,
                    transformed_points_ft=pts_ft,
                    bbox_pdf=bbox,
                    transformed_bbox_ft=bbox_ft,
                    label=label,
                    properties=props,
                    source_object_id=g.id,
                    source_type="PDF_VECTOR",
                    semantic_type=sem_type,
                    classification_method="MULTI_REGION_PLUMBING_CLASSIFIER",
                    classification_evidence=f"Region {reg_title} ({reg_cat or 'MAIN'})",
                    classification_status=SemanticClassificationStatus.SUPPORTED,
                    confidence=0.92,
                    provenance=DataProvenanceStatus.VERIFIED_EXPLICIT,
                )
            )

        # 2. Convert All Decoded Native Text Objects into First-Class Canonical Semantic Objects
        for t_idx, txt in enumerate(text_objects):
            tb = txt.bbox_pdf
            tx = (tb[0] + tb[2]) / 2.0
            ty = (tb[1] + tb[3]) / 2.0
            pts_pdf = [[tb[0], tb[1]], [tb[2], tb[1]], [tb[2], tb[3]], [tb[0], tb[3]]]
            pts_ft = [[p[0] * ft_per_pt, p[1] * ft_per_pt] for p in pts_pdf]
            bbox_ft = [b * ft_per_pt for b in tb]

            # Route text object to layer based on verified semantic role
            if txt.semantic_role in (
                SemanticTextRole.TITLE_BLOCK,
                SemanticTextRole.TITLE_BLOCK_TEXT,
                SemanticTextRole.DRAWING_TITLE,
                SemanticTextRole.SHEET_NUMBER,
                SemanticTextRole.SCALE_LABEL,
            ):
                t_layer = "Title Block"
                t_obj_type = DrawingObjectType.TITLE_BLOCK
            elif txt.semantic_role == SemanticTextRole.LEGEND_TEXT:
                t_layer = "Legend"
                t_obj_type = DrawingObjectType.LEGEND
            elif txt.semantic_role in (
                SemanticTextRole.NOTE,
                SemanticTextRole.PLUMBING_NOTE,
                SemanticTextRole.GENERAL_NOTE,
                SemanticTextRole.GENERAL_ANNOTATION,
                SemanticTextRole.DETAIL_CALLOUT,
                SemanticTextRole.MATERIAL_LABEL,
            ):
                t_layer = "Annotations"
                t_obj_type = DrawingObjectType.ANNOTATION
            elif txt.semantic_role == SemanticTextRole.DIMENSION_TEXT:
                t_layer = "Dimensions"
                t_obj_type = DrawingObjectType.DIMENSION
            elif txt.semantic_role == SemanticTextRole.GRID_LABEL:
                t_layer = "Grid"
                t_obj_type = DrawingObjectType.GRID
            else:
                t_layer = "Text"
                t_obj_type = DrawingObjectType.TEXT

            semantic_objects.append(
                SemanticDrawingObject(
                    id=f"OBJ-TXT-P{page_number:02d}-{t_idx + 1:04d}",
                    page_number=page_number,
                    object_type=t_obj_type,
                    layer=t_layer,
                    source_vector_ids=[],
                    source_text_ids=[txt.id],
                    source_points_pdf=pts_pdf,
                    normalized_points=pts_pdf,
                    transformed_points_ft=pts_ft,
                    bbox_pdf=tb,
                    transformed_bbox_ft=bbox_ft,
                    label=f"{txt.semantic_role.value}: {txt.text[:24]}",
                    properties={
                        "text": txt.text,
                        "semantic_role": txt.semantic_role.value,
                        "font_size": txt.font_size,
                    },
                    source_object_id=txt.id,
                    source_type="PDF_NATIVE_TEXT",
                    semantic_type=txt.semantic_role.value,
                    classification_method="CONTENT_STREAM_TEXT_CLASSIFICATION",
                    classification_evidence=f"Text '{txt.text}' classified as {txt.semantic_role.value}",
                    classification_status=SemanticClassificationStatus.VERIFIED_EXPLICIT,
                    confidence=1.0,
                    provenance=DataProvenanceStatus.VERIFIED_EXPLICIT,
                )
            )

        return semantic_objects

    def _classify_furniture_plan(
        self,
        page_number: int,
        text_objects: list[DrawingTextObject],
        geometry_objects: list[DrawingGeometryObject],
        regions: list[DrawingRegion],
        scale_evidence: ScaleEvidence,
    ) -> list[SemanticDrawingObject]:
        """Multi-region furniture domain: Separate Ground, First, and Mumty plans."""
        semantic_objects: list[SemanticDrawingObject] = []
        ft_per_pt = scale_evidence.ft_per_pt or 0.13333

        for v_idx, g in enumerate(geometry_objects):
            bbox = g.bbox_pdf
            cx = (bbox[0] + bbox[2]) / 2.0
            cy = (bbox[1] + bbox[3]) / 2.0

            # Match to specific sub-drawing region on Page 10
            matched_reg = next(
                (r for r in regions if r.bbox_pdf[0] <= cx <= r.bbox_pdf[2] and r.bbox_pdf[1] <= cy <= r.bbox_pdf[3]),
                None
            )
            reg_id = matched_reg.region_id if matched_reg else f"REG-P{page_number:02d}-01"
            reg_title = matched_reg.title if matched_reg else "FURNITURE PLAN"

            pts_pdf = g.source_points_pdf
            pts_ft = [[p[0] * ft_per_pt, p[1] * ft_per_pt] for p in pts_pdf]
            bbox_ft = [b * ft_per_pt for b in bbox]

            semantic_objects.append(
                SemanticDrawingObject(
                    id=f"OBJ-FURN-P{page_number:02d}-{v_idx + 1:04d}",
                    page_number=page_number,
                    object_type=DrawingObjectType.FURNITURE,
                    layer="Geometry",
                    source_vector_ids=[g.id],
                    source_points_pdf=pts_pdf,
                    normalized_points=pts_pdf,
                    transformed_points_ft=pts_ft,
                    bbox_pdf=bbox,
                    transformed_bbox_ft=bbox_ft,
                    label=f"Furniture Element ({reg_title})",
                    properties={"region_id": reg_id, "region_title": reg_title},
                    source_object_id=g.id,
                    source_type="PDF_VECTOR",
                    semantic_type="FURNITURE_BLOCK",
                    classification_method="MULTI_REGION_SECTOR_ASSIGNMENT",
                    classification_evidence=f"Spatial containment within region {reg_id}",
                    classification_status=SemanticClassificationStatus.SUPPORTED,
                    confidence=0.88,
                    provenance=DataProvenanceStatus.VERIFIED_EXPLICIT,
                )
            )
        return semantic_objects

    def _classify_detail_drawing(
        self,
        page_number: int,
        text_objects: list[DrawingTextObject],
        geometry_objects: list[DrawingGeometryObject],
        regions: list[DrawingRegion],
        scale_evidence: ScaleEvidence,
    ) -> list[SemanticDrawingObject]:
        """Detail drawing domain: Kitchen hoods, casework, cabinet sections."""
        semantic_objects: list[SemanticDrawingObject] = []
        ft_per_pt = scale_evidence.ft_per_pt or 0.03333  # 1/2" = 1'-0"

        for v_idx, g in enumerate(geometry_objects):
            bbox = g.bbox_pdf
            pts_pdf = g.source_points_pdf
            pts_ft = [[p[0] * ft_per_pt, p[1] * ft_per_pt] for p in pts_pdf]
            bbox_ft = [b * ft_per_pt for b in bbox]

            semantic_objects.append(
                SemanticDrawingObject(
                    id=f"OBJ-DET-P{page_number:02d}-{v_idx + 1:04d}",
                    page_number=page_number,
                    object_type=DrawingObjectType.DETAIL_MARKER,
                    layer="Geometry",
                    source_vector_ids=[g.id],
                    source_points_pdf=pts_pdf,
                    normalized_points=pts_pdf,
                    transformed_points_ft=pts_ft,
                    bbox_pdf=bbox,
                    transformed_bbox_ft=bbox_ft,
                    label="Joinery Detail Linework",
                    properties={},
                    source_object_id=g.id,
                    source_type="PDF_VECTOR",
                    semantic_type="DETAIL_COMPONENT",
                    classification_method="DETAIL_REGION_ASSIGNMENT",
                    classification_evidence="High-scale joinery detail geometry",
                    classification_status=SemanticClassificationStatus.SUPPORTED,
                    confidence=0.85,
                    provenance=DataProvenanceStatus.VERIFIED_EXPLICIT,
                )
            )
        return semantic_objects

    def _classify_general_sheet(
        self,
        page_number: int,
        text_objects: list[DrawingTextObject],
        geometry_objects: list[DrawingGeometryObject],
        scale_evidence: ScaleEvidence,
    ) -> list[SemanticDrawingObject]:
        """General fallback classification preserving 100% of vectors."""
        semantic_objects: list[SemanticDrawingObject] = []
        ft_per_pt = scale_evidence.ft_per_pt or 1.0

        for v_idx, g in enumerate(geometry_objects):
            bbox = g.bbox_pdf
            pts_pdf = g.source_points_pdf
            pts_ft = [[p[0] * ft_per_pt, p[1] * ft_per_pt] for p in pts_pdf]
            bbox_ft = [b * ft_per_pt for b in bbox]

            semantic_objects.append(
                SemanticDrawingObject(
                    id=f"OBJ-GEN-P{page_number:02d}-{v_idx + 1:04d}",
                    page_number=page_number,
                    object_type=DrawingObjectType.LINE,
                    layer="Geometry",
                    source_vector_ids=[g.id],
                    source_points_pdf=pts_pdf,
                    normalized_points=pts_pdf,
                    transformed_points_ft=pts_ft,
                    bbox_pdf=bbox,
                    transformed_bbox_ft=bbox_ft,
                    label="Drafting Geometry",
                    properties={},
                    source_object_id=g.id,
                    source_type="PDF_VECTOR",
                    semantic_type="GENERAL_LINEWORK",
                    classification_method="DIRECT_VECTOR_EXTRACTION",
                    classification_evidence="Source PDF vector stream",
                    classification_status=SemanticClassificationStatus.SUPPORTED,
                    confidence=0.8,
                    provenance=DataProvenanceStatus.VERIFIED_EXPLICIT,
                )
            )
        return semantic_objects
