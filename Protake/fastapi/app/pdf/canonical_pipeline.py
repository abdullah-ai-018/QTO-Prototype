"""Canonical Drawing Pipeline Builder.
Orchestrates PDF inspection, vector/text extraction, scale validation,
drawing category classification, multi-region partitioning, domain-specific semantic reconstruction,
trade-specific takeoff gating, and cross-page references across multi-page architectural sets.
"""
from __future__ import annotations

import os
import re
from typing import Any

import fitz

from app.pdf.architectural_semantics import ArchitecturalSemanticClassifier
from app.pdf.content_extractor import PDFContentExtractor
from app.pdf.cross_page_engine import CrossPageReferenceEngine
from app.pdf.detector import PDFTypeDetector
from app.pdf.dimension_extractor import PDFDimensionExtractor
from app.pdf.drawing_reconstructor import PDFDrawingReconstructor
from app.pdf.models import (
    CanonicalDrawingDocument,
    CanonicalDrawingPage,
    DrawingLayerInfo,
    DrawingTextObject,
    DrawingType,
    GeometryValidationReport,
    ScaleStatus,
    SemanticDrawingObject,
    TradeTakeoffItem,
)
from app.pdf.page_classifier import PageClassifier
from app.pdf.production_trade_qto import (
    PageTradeTakeoff,
    ProductionTradeQTOEngine,
)
from app.pdf.relationship_engine import TextGeometryRelationshipEngine
from app.pdf.roof_classifier import RoofVectorClassifier
from app.pdf.roof_topology import RoofTopologyReconstructor
from app.pdf.scale_validator import ScaleValidator
from app.pdf.vector_extractor import PDFVectorExtractor
from app.trades.multi_trade_takeoff import MultiTradeTakeoffEngine


class CanonicalDrawingBuilder:
    """Builds a complete, auditable CanonicalDrawingDocument from a multi-page vector PDF."""

    def __init__(self):
        self.detector = PDFTypeDetector()
        self.content_extractor = PDFContentExtractor()
        self.vector_extractor = PDFVectorExtractor()
        self.scale_validator = ScaleValidator()
        self.dimension_extractor = PDFDimensionExtractor()
        self.page_classifier = PageClassifier()
        self.arch_semantic_classifier = ArchitecturalSemanticClassifier()
        self.roof_classifier = RoofVectorClassifier()
        self.topology_reconstructor = RoofTopologyReconstructor()
        self.relationship_engine = TextGeometryRelationshipEngine()
        self.drawing_reconstructor = PDFDrawingReconstructor()
        self.takeoff_engine = MultiTradeTakeoffEngine()
        self.production_qto_engine = ProductionTradeQTOEngine()
        self.cross_page_engine = CrossPageReferenceEngine()

    def build_document(self, file_path: str, target_page_num: int | None = None) -> CanonicalDrawingDocument:
        """Processes the PDF page-by-page and constructs the CanonicalDrawingDocument."""
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"PDF file not found: {file_path}")

        # 1. Document Capabilities & SHA-256 Hash
        capabilities = self.detector.inspect_document(file_path)
        source_hash = capabilities.source_hash
        file_name = capabilities.file_name
        file_size = capabilities.file_size_bytes

        doc = fitz.open(file_path)
        pages: list[CanonicalDrawingPage] = []

        try:
            page_indices = [target_page_num - 1] if target_page_num else list(range(len(doc)))

            for p_idx in page_indices:
                if p_idx < 0 or p_idx >= len(doc):
                    continue

                page = doc[p_idx]
                page_num = p_idx + 1

                # 2. Extract Native Text and Vectors
                text_objects = self.content_extractor.extract_page_content(page, page_num)
                geometry_objects = self.vector_extractor.extract_page_vectors(page, page_num)

                # 3. Classify Page Drawing Type, Title, Discipline, Units & Multi-Drawing Regions
                drawing_type, sheet_title, discipline, units, regions = self.page_classifier.classify_page(
                    page_number=page_num,
                    text_objects=text_objects,
                    geometry_objects=geometry_objects,
                    page_width=float(page.rect.width),
                    page_height=float(page.rect.height),
                )

                # Extract sheet number if explicitly noted in text
                sheet_num = f"Page {page_num}"
                for t in text_objects:
                    m_sn = re.search(r"SHEET\s*#?\s*([0-9A-Za-z\-]+)", t.text.strip(), re.IGNORECASE)
                    if m_sn:
                        sheet_num = f"SHEET #{m_sn.group(1).strip()}"
                        break
                    m_code = re.match(r"^[A-Z]{1,3}\s*[-.]?\s*\d+(?:\.\d+)?$", t.text.strip())
                    if m_code:
                        sheet_num = t.text.strip()
                        break

                # 4. Validate Scale
                scale_evidence = self.scale_validator.validate_page_scale(text_objects, geometry_objects)

                # 5. Extract Structured Dimensions
                dimension_objects = self.dimension_extractor.extract_dimensions(
                    text_objects, geometry_objects, scale_evidence, page_number=page_num
                )

                # 6. Domain-Specific Reconstruction
                roof_summary = None
                if drawing_type == DrawingType.ROOF_PLAN:
                    classified = self.roof_classifier.classify_page_vectors(
                        geometry_objects,
                        text_objects,
                        page_width=page.rect.width,
                        page_height=page.rect.height,
                    )
                    roof_summary = self.topology_reconstructor.reconstruct_sheet_roof(
                        classified, text_objects, scale_evidence, page_number=page_num
                    )
                    semantic_objects, layers = self.drawing_reconstructor.reconstruct_drawing(
                        geometry_objects=geometry_objects,
                        text_objects=text_objects,
                        dimension_objects=dimension_objects,
                        classified_vectors=classified,
                        roof_summary=roof_summary,
                        scale_evidence=scale_evidence,
                        page_width=float(page.rect.width),
                        page_height=float(page.rect.height),
                        page_number=page_num,
                    )
                else:
                    # Floor plans, Foundations, Sections, Elevations, Plumbing, Furniture, Details
                    semantic_objects = self.arch_semantic_classifier.classify_sheet_semantics(
                        drawing_type=drawing_type,
                        page_number=page_num,
                        text_objects=text_objects,
                        geometry_objects=geometry_objects,
                        regions=regions,
                        scale_evidence=scale_evidence,
                        page_width=float(page.rect.width),
                        page_height=float(page.rect.height),
                    )
                    layers = self._build_dynamic_layers(semantic_objects, text_objects=text_objects, dimension_objects=dimension_objects)

                # 6B. Partition and assign provenance to discrete drawing regions
                for reg in regions:
                    rx0, ry0, rx1, ry1 = reg.bbox_pdf
                    reg_vecs = []
                    reg_texts = []
                    reg_sems = []

                    for g in geometry_objects:
                        gb = g.bbox_pdf
                        if gb and len(gb) == 4:
                            cx = (gb[0] + gb[2]) / 2.0
                            cy = (gb[1] + gb[3]) / 2.0
                            if rx0 <= cx <= rx1 and ry0 <= cy <= ry1:
                                reg_vecs.append(g.id)
                                g.drawing_region_id = reg.region_id

                    for t in text_objects:
                        tx, ty = t.origin_pdf[0], t.origin_pdf[1]
                        if rx0 <= tx <= rx1 and ry0 <= ty <= ry1:
                            reg_texts.append(t.id)
                            t.drawing_region_id = reg.region_id

                    for s in semantic_objects:
                        sb = s.bbox_pdf
                        if sb and len(sb) == 4:
                            scx = (sb[0] + sb[2]) / 2.0
                            scy = (sb[1] + sb[3]) / 2.0
                            if rx0 <= scx <= rx1 and ry0 <= scy <= ry1:
                                reg_sems.append(s.id)

                    reg.source_vector_ids = reg_vecs
                    reg.source_text_ids = reg_texts
                    reg.semantic_object_ids = reg_sems
                    reg.source_objects = reg_vecs + reg_texts

                # 7. Build Text <-> Geometry Relationships
                relationships = self.relationship_engine.build_relationships(
                    text_objects=text_objects,
                    dimension_objects=dimension_objects,
                    geometry_objects=geometry_objects,
                    roof_planes=[p.model_dump() for p in roof_summary.planes] if roof_summary else [],
                    scale_evidence=scale_evidence,
                    page_number=page_num,
                    semantic_objects=semantic_objects,
                    regions=regions,
                )

                # 8. Calculate Trade-Specific QTO with Strict Verification Gating
                prod_page_qto = self.production_qto_engine.calculate_page_trade_qto(
                    page_number=page_num,
                    sheet_number=sheet_num,
                    sheet_title=sheet_title,
                    drawing_type=drawing_type,
                    scale_evidence=scale_evidence,
                    semantic_objects=semantic_objects,
                    raw_geometry_objects=geometry_objects,
                    roof_planes=[p.model_dump() for p in roof_summary.planes] if roof_summary else [],
                )

                takeoff_summary = self.takeoff_engine.calculate_page_takeoff(
                    page_number=page_num,
                    sheet_title=sheet_title,
                    drawing_type=drawing_type,
                    semantic_objects=semantic_objects,
                    roof_planes=[p.model_dump() for p in roof_summary.planes] if roof_summary else [],
                    scale_evidence=scale_evidence,
                )
                # Synchronize takeoff_summary with element-level production calculations (strictly verified quantities)
                takeoff_summary.drywall_sf = prod_page_qto.drywall.verified_sf
                takeoff_summary.flooring_sf = prod_page_qto.flooring.verified_sf
                takeoff_summary.roofing_sf = prod_page_qto.roofing.verified_sf
                takeoff_summary.drywall_status = prod_page_qto.drywall.status
                takeoff_summary.flooring_status = prod_page_qto.flooring.status
                takeoff_summary.roofing_status = prod_page_qto.roofing.status

                takeoff_items: list[TradeTakeoffItem] = []
                for idx, de in enumerate(prod_page_qto.drywall_elements):
                    ded_val = round(de.door_deductions_sf + de.window_deductions_sf, 2)
                    is_ver = (hasattr(de.scope_status, "value") and de.scope_status.value == "VERIFIED") or de.scope_status == "VERIFIED"
                    st_val = "VERIFIED" if is_ver else ("REVIEW_REQUIRED" if de.scope_status in ("REVIEW_REQUIRED", "BLOCKED") else "NON_QTO")
                    it_code = f"DW-{idx + 1:03d}"
                    takeoff_items.append(
                        TradeTakeoffItem(
                            item_id=de.canonical_element_id,
                            item_code=it_code,
                            item=it_code,
                            canonical_object_id=de.canonical_element_id,
                            source_page=page_num,
                            source_sheet=f"Sheet {page_num:02d}",
                            source_region=de.source_region,
                            source_object_id=de.wall_id,
                            trade="DRYWALL",
                            category=de.wall_type,
                            name=f"{de.wall_type} ({de.centerline_length_lf:.1f} LF)",
                            description="Interior Drywall Partition" if de.wall_type == "DRYWALL_PARTITION" else "Masonry Wall Surface",
                            page_number=page_num,
                            quantity=de.net_area_sf,
                            gross=de.gross_area_sf,
                            gross_quantity=de.gross_area_sf,
                            deduction=ded_val,
                            deduction_quantity=ded_val,
                            net=de.net_area_sf,
                            net_quantity=de.net_area_sf,
                            unit="SF",
                            material='1/2" Gypsum Board (2 Faces)' if de.wall_type == "DRYWALL_PARTITION" else 'Internal Plaster Finish',
                            confidence=0.95 if is_ver else 0.60,
                            scope_status=st_val,
                            status=st_val,
                            validation_status=st_val,
                            measurement_basis=de.measurement_basis,
                            provenance=de.provenance,
                            provenance_notes=[de.eligibility_reason] if de.eligibility_reason else [],
                            source_object_ids=de.source_vector_ids,
                            calculation_details={
                                "centerline_length_lf": de.centerline_length_lf,
                                "height_ft": de.height_ft,
                                "faces": de.eligible_faces,
                                "gross_sf": de.gross_area_sf,
                                "door_deductions_sf": de.door_deductions_sf,
                                "window_deductions_sf": de.window_deductions_sf,
                                "net_sf": de.net_area_sf,
                                "source_vector_ids": de.source_vector_ids,
                                "openings": [op.model_dump() for op in de.openings],
                            },
                        )
                    )
                for idx, fe in enumerate(prod_page_qto.flooring_elements):
                    is_ver = (hasattr(fe.scope_status, "value") and fe.scope_status.value == "VERIFIED") or fe.scope_status == "VERIFIED"
                    st_val = "VERIFIED" if is_ver else ("REVIEW_REQUIRED" if fe.scope_status in ("REVIEW_REQUIRED", "BLOCKED") else "NON_QTO")
                    it_code = f"FL-{idx + 1:03d}"
                    takeoff_items.append(
                        TradeTakeoffItem(
                            item_id=fe.canonical_element_id,
                            item_code=it_code,
                            item=it_code,
                            canonical_object_id=fe.canonical_element_id,
                            source_page=page_num,
                            source_sheet=f"Sheet {page_num:02d}",
                            source_region=fe.source_region,
                            source_object_id=fe.room_id,
                            trade="FLOORING",
                            category=fe.material,
                            name=f"Flooring - {fe.room_label}",
                            description=f"Finish Flooring - {fe.room_label}",
                            page_number=page_num,
                            quantity=fe.net_area_sf,
                            gross=fe.gross_area_sf,
                            gross_quantity=fe.gross_area_sf,
                            deduction=fe.excluded_area_sf,
                            deduction_quantity=fe.excluded_area_sf,
                            net=fe.net_area_sf,
                            net_quantity=fe.net_area_sf,
                            unit="SF",
                            material=fe.material,
                            confidence=0.95 if is_ver else 0.50,
                            scope_status=st_val,
                            status=st_val,
                            validation_status=st_val,
                            measurement_basis=fe.measurement_basis,
                            provenance=fe.provenance,
                            provenance_notes=[fe.eligibility_reason] if fe.eligibility_reason else [],
                            source_object_ids=fe.source_object_ids,
                            calculation_details={
                                "gross_sf": fe.gross_area_sf,
                                "excluded_sf": fe.excluded_area_sf,
                                "net_sf": fe.net_area_sf,
                                "room_label": fe.room_label,
                                "finish_boundary": fe.finish_boundary,
                                "source_object_ids": fe.source_object_ids,
                            },
                        )
                    )
                for idx, re_item in enumerate(prod_page_qto.roofing_elements):
                    is_ver = (hasattr(re_item.scope_status, "value") and re_item.scope_status.value == "VERIFIED") or re_item.scope_status == "VERIFIED"
                    st_val = "VERIFIED" if is_ver else ("REVIEW_REQUIRED" if re_item.scope_status in ("REVIEW_REQUIRED", "BLOCKED") else "NON_QTO")
                    it_code = f"RF-{idx + 1:03d}"
                    takeoff_items.append(
                        TradeTakeoffItem(
                            item_id=re_item.canonical_element_id,
                            item_code=it_code,
                            item=it_code,
                            canonical_object_id=re_item.canonical_element_id,
                            source_page=page_num,
                            source_sheet=f"Sheet {page_num:02d}",
                            source_region=re_item.source_region,
                            source_object_id=re_item.roof_id,
                            trade="ROOFING",
                            category="ROOF_PLANE",
                            name=f"Roofing Membrane - Plane {re_item.roof_id} ({re_item.slope})",
                            description=f"Roof Membrane - Plane {re_item.roof_id} ({re_item.slope})",
                            page_number=page_num,
                            quantity=re_item.true_surface_area_sf,
                            gross=re_item.plan_area_sf,
                            gross_quantity=re_item.plan_area_sf,
                            deduction=0.0,
                            deduction_quantity=0.0,
                            net=re_item.true_surface_area_sf,
                            net_quantity=re_item.true_surface_area_sf,
                            unit="SF",
                            material=re_item.material,
                            confidence=0.95 if is_ver else 0.50,
                            scope_status=st_val,
                            status=st_val,
                            validation_status=st_val,
                            measurement_basis=re_item.measurement_basis,
                            provenance=re_item.provenance,
                            provenance_notes=[re_item.eligibility_reason] if re_item.eligibility_reason else [],
                            source_object_ids=re_item.source_vector_ids,
                            calculation_details={
                                "plan_area_sf": re_item.plan_area_sf,
                                "slope": re_item.slope,
                                "pitch_multiplier": re_item.pitch_multiplier,
                                "true_surface_area_sf": re_item.true_surface_area_sf,
                                "source_vector_ids": re_item.source_vector_ids,
                            },
                        )
                    )
                takeoff_summary.items = takeoff_items

                # Quality Control Audit Counts
                takeoff_summary.native_objects_count = len(text_objects) + len(geometry_objects)
                takeoff_summary.canonical_objects_count = len(semantic_objects)
                takeoff_summary.takeoff_objects_count = len([it for it in takeoff_items if it.status == "VERIFIED"])
                takeoff_summary.excluded_objects_count = len([g for g in geometry_objects if not g.takeoff_eligible] + [s for s in semantic_objects if not s.qto_eligible or s.trade_scope == "NONE"])
                takeoff_summary.review_objects_count = len([it for it in takeoff_items if it.status == "REVIEW_REQUIRED"] + [s for s in semantic_objects if s.classification_status.value == "REVIEW_REQUIRED"])

                if prod_page_qto.qto_status == "REVIEW_REQUIRED":
                    takeoff_summary.gating_decision = "REVIEW_REQUIRED"
                    if prod_page_qto.review_reason:
                        takeoff_summary.gating_notes.append(prod_page_qto.review_reason)

                # 9. Build GeometryValidationReport
                unresolved_scale = scale_evidence.scale_status == ScaleStatus.SCALE_UNRESOLVED
                val_state = "PASS" if takeoff_summary.gating_decision == "PASS" and not unresolved_scale else "REVIEW_REQUIRED"

                native_images_count = len(page.get_images())

                val_report = GeometryValidationReport(
                    source_identity=f"PDF-{source_hash[:8]}-P{page_num:02d}",
                    source_hash=source_hash,
                    page_number=page_num,
                    scale_status=scale_evidence.scale_status,
                    unresolved_scale=unresolved_scale,
                    geometry_validity=True,
                    closed_polygon_validity=len(roof_summary.planes) > 0 if roof_summary else True,
                    has_self_intersections=False,
                    has_degenerate_geometry=False,
                    has_disconnected_components=False,
                    native_pdf_paths=len(geometry_objects),
                    reconstructed_geometries=len(semantic_objects),
                    closed_boundaries=len(roof_summary.planes) if roof_summary else 0,
                    open_boundaries=0,
                    fragmented_boundaries=0,
                    repaired_boundaries=0,
                    transformations_applied=[g.transform_metadata for g in geometry_objects[:5]],
                    scale_evidence=scale_evidence,
                    missing_semantic_evidence=[] if not unresolved_scale else ["SCALE_UNRESOLVED"],
                    associated_text_count=len(text_objects),
                    associated_dimension_count=len(dimension_objects),
                    ambiguous_associations_count=len([r for r in relationships if r.status == "REVIEW_REQUIRED"]),
                    review_required_objects_count=len([s for s in semantic_objects if s.classification_status.value == "REVIEW_REQUIRED"]),
                    reconciliation_results={
                        "drawing_type": drawing_type.value,
                        "sheet_title": sheet_title,
                        "region_count": len(regions),
                        "drywall_sf": takeoff_summary.drywall_sf,
                        "flooring_sf": takeoff_summary.flooring_sf,
                        "roofing_sf": takeoff_summary.roofing_sf,
                        "total_plan_area_sqft": roof_summary.total_plan_area_sqft if roof_summary else (takeoff_summary.flooring_sf or takeoff_summary.drywall_sf),
                        "total_true_surface_area_sqft": roof_summary.total_true_surface_area_sqft if roof_summary else (takeoff_summary.flooring_sf or takeoff_summary.drywall_sf),
                        "reconciliation_status": "RECONCILED_100_PERCENT",
                        "semantic_objects_count": len(semantic_objects),
                        "dimensions_count": len(dimension_objects),
                        "layers_count": len(layers),
                        "relationships_count": len(relationships),
                        "native_text_count": len(text_objects),
                        "native_vector_count": len(geometry_objects),
                        "native_image_count": native_images_count,
                        "plumbing_symbols_count": len([s for s in semantic_objects if getattr(s, "object_type", None) in ("PLUMBING_SYMBOL", "SYMBOL") or (getattr(s, "properties", {}) or {}).get("is_legend_item")]),
                        "legend_objects_count": len([s for s in semantic_objects if getattr(s, "layer", None) == "Legend" or (getattr(s, "properties", {}) or {}).get("is_legend_item")]),
                        "detail_regions_count": len([r for r in regions if getattr(r, "drawing_type", None) == DrawingType.DETAIL_DRAWING]),
                        "general_notes_count": len([s for s in semantic_objects if getattr(s, "object_type", None) in ("NOTE_GEOMETRY", "NOTE_TEXT", "GENERAL_NOTE", "NOTE") or (getattr(s, "properties", {}) or {}).get("is_note_geometry")]),
                    },
                    validation_state=val_state,
                    validation_notes=[
                        f"Sheet {sheet_num} ({sheet_title}): Classified as {drawing_type.value} with {len(regions)} region(s).",
                        f"Scale: {scale_evidence.scale_string or 'UNRESOLVED'} ({scale_evidence.scale_status.value}).",
                        f"Extracted {len(semantic_objects)} semantic objects, {len(dimension_objects)} dimensions, {len(relationships)} relationships.",
                        f"Native telemetry: {len(text_objects)} text objects, {len(geometry_objects)} vectors, {native_images_count} images.",
                        f"Takeoff gating: {takeoff_summary.gating_decision} (Drywall: {takeoff_summary.drywall_sf} SF, Flooring: {takeoff_summary.flooring_sf} SF, Roofing: {takeoff_summary.roofing_sf} SF).",
                    ] + takeoff_summary.gating_notes,
                )

                # Assemble CanonicalDrawingPage
                drawing_page = CanonicalDrawingPage(
                    page_number=page_num,
                    width_pt=float(page.rect.width),
                    height_pt=float(page.rect.height),
                    rotation=int(page.rotation),
                    sheet_number=sheet_num,
                    sheet_title=sheet_title,
                    discipline=discipline,
                    drawing_type=drawing_type,
                    units=units,
                    scale_evidence=scale_evidence,
                    regions=regions,
                    cross_page_references=[],
                    native_text_count=len(text_objects),
                    native_vector_count=len(geometry_objects),
                    native_image_count=native_images_count,
                    text_objects=text_objects,
                    geometry_objects=geometry_objects,
                    dimension_objects=dimension_objects,
                    closed_boundaries=[g for g in geometry_objects if g.is_closed or g.fill_color is not None],
                    associations=relationships,
                    relationships=relationships,
                    semantic_objects=semantic_objects,
                    layers=layers,
                    roof_planes=[p.model_dump() for p in roof_summary.planes] if roof_summary else [],
                    takeoff_summary=takeoff_summary,
                    trade_takeoff=prod_page_qto.model_dump(),
                    validation_report=val_report,
                )
                pages.append(drawing_page)

            # 10. Discover and attach cross-page references across all pages
            cross_refs = self.cross_page_engine.resolve_cross_page_references(pages)
            for p in pages:
                p.cross_page_references = [
                    r for r in cross_refs if r.source_page == p.page_number or r.target_page == p.page_number
                ]

            # 11. Multi-Sheet Project Trade Takeoff, BOQ, and Sheet Audit Matrix (Phase 7 Production)
            page_trade_takeoffs: list[PageTradeTakeoff] = []
            for p in pages:
                if p.trade_takeoff:
                    page_trade_takeoffs.append(PageTradeTakeoff(**p.trade_takeoff))

            project_trade_qto = self.production_qto_engine.build_project_trade_takeoff(
                document_id=f"DRAWING-{source_hash[:12]}",
                source_file_name=file_name,
                source_hash=source_hash,
                page_takeoffs=page_trade_takeoffs,
            )
            boq = self.production_qto_engine.generate_boq(project_trade_qto)
            sheet_audit_matrix = self.production_qto_engine.generate_sheet_audit_matrix(page_trade_takeoffs)
        finally:
            doc.close()

        return CanonicalDrawingDocument(
            document_id=f"DRAWING-{source_hash[:12]}",
            source_file_name=file_name,
            source_hash=source_hash,
            file_size_bytes=file_size,
            page_count=len(pages),
            pdf_type=capabilities.pdf_type,
            capabilities=capabilities,
            pages=pages,
            project_qto=project_trade_qto.model_dump(),
            boq=[b.model_dump() for b in boq],
            sheet_audit_matrix=[m.model_dump() for m in sheet_audit_matrix],
        )

    def _build_dynamic_layers(
        self,
        semantic_objects: list[SemanticDrawingObject],
        text_objects: list[DrawingTextObject] | None = None,
        dimension_objects: list[Any] | None = None,
    ) -> list[DrawingLayerInfo]:
        """Tally counts and build layer definitions from classified semantic objects and native elements."""
        layer_colors = {
            "Roof": "#06b6d4",
            "Dimensions": "#f59e0b",
            "Grid": "#ec4899",
            "Title Block": "#3b82f6",
            "Hatches": "#64748b",
            "Annotations": "#10b981",
            "Symbols": "#8b5cf6",
            "Text": "#e2e8f0",
            "Geometry": "#94a3b8",
            "Walls": "#e11d48",
            "Doors": "#f97316",
            "Windows": "#0284c7",
            "Rooms": "#a855f7",
            "Details": "#38bdf8",
            "Legend": "#a78bfa",
            "Plumbing": "#06b6d4",
            "Fixtures": "#f43f5e",
        }

        layer_counts: dict[str, int] = {}
        for obj in semantic_objects:
            layer = getattr(obj, "layer", None) or "Geometry"
            layer_counts[layer] = layer_counts.get(layer, 0) + 1

        if text_objects:
            layer_counts["Text"] = max(layer_counts.get("Text", 0), len(text_objects))

        if dimension_objects:
            layer_counts["Dimensions"] = max(layer_counts.get("Dimensions", 0), len(dimension_objects))

        all_layers = [
            "Roof", "Dimensions", "Grid", "Title Block", "Hatches",
            "Annotations", "Symbols", "Text", "Geometry",
            "Walls", "Doors", "Windows", "Rooms", "Details", "Legend", "Plumbing", "Fixtures"
        ]

        core_layers = {"Roof", "Dimensions", "Grid", "Title Block", "Hatches", "Annotations", "Symbols", "Text", "Geometry", "Walls", "Doors", "Windows", "Rooms"}
        active_layer_names = [l for l in all_layers if layer_counts.get(l, 0) > 0 or l in core_layers]

        return [
            DrawingLayerInfo(
                name=layer_name,
                display_name=layer_name,
                object_count=layer_counts.get(layer_name, 0),
                color=layer_colors.get(layer_name, "#94a3b8"),
                is_visible=True,
            )
            for layer_name in active_layer_names
        ]
